#!/usr/bin/env python3
"""Interface-choice coverage for gate Q-03 (docs/TESTING.md).

DPM's coverage report does not count the choices of interfaces a production
template implements ("External interface choices: 0 defined"). This check
derives them from the DARs and compares them with what the test run
exercised:

  1. Expected. `damlc inspect` of the production DAR lists its interface
     instances ("interface instance <package>:<Module>:<Interface> for
     <Module>:<Template>"). For each interface, `damlc inspect` of the DAR
     whose main package is <package> lists the interface's choices
     ("consuming choice <Name> ..." or "non-consuming choice <Name> ...").
     The expected set is every (choice, template) pair, `Archive` excluded:
     archival is counted by the template coverage.
  2. Exercised. `dpm test --save-coverage FILE` writes a `TestResults`
     protobuf (daml SDK 3.4.11 `sdk/compiler/script-service/protos/
     test_results.proto`): field 5, `exercised`, lists each choice with the
     templates, by package, it was exercised on. The pairs on the production
     package's own templates form the exercised set.
  3. Every expected pair must be exercised. The maintained list
     docs/INTERFACE-CHOICES.md is compared with the expected set as a
     cross-check: a pair in one and not the other fails.

Usage: scripts/check-interface-coverage.py --dar PRODUCTION.dar --coverage FILE
           --interface-dars DAR [DAR ...] [--manual docs/INTERFACE-CHOICES.md]
           [--manual-section cvx-vault-v1] [--sdk 3.4.11]
Exit status: 0 when every pair is exercised and the list matches; 1 otherwise.
"""

import argparse
import os
import re
import subprocess
import sys

INSTANCE = re.compile(r"^\s*interface instance ([0-9a-f]{64}):([\w.]+):(\w+) for ([\w.]+):(\w+)\s*$")
INTERFACE = re.compile(r"^interface (\w+) this where\s*$")
CHOICE = re.compile(r"^\s+(?:non-)?consuming choice (\w+) ")
MODULE = re.compile(r"^module ([\w.]+) where\s*$")


def inspect(dar, sdk):
    r = subprocess.run(["dpm", "damlc", "inspect", dar], capture_output=True, text=True,
                       env=dict(os.environ, DPM_SDK_VERSION=sdk))
    if r.returncode != 0:
        sys.exit(f"interface-coverage: damlc inspect {dar} failed: {r.stderr[-500:]}")
    lines = r.stdout.splitlines()
    package = lines[0].split()[1] if lines and lines[0].startswith("package ") else None
    return package, lines


def interface_choices(lines):
    """{(module, interface): [choice, ...]} for every interface of a package."""
    result, module, current = {}, None, None
    for line in lines:
        m = MODULE.match(line)
        if m:
            module, current = m.group(1), None
            continue
        m = INTERFACE.match(line)
        if m:
            current = (module, m.group(1))
            result[current] = []
            continue
        if line and not line[0].isspace():
            current = None
            continue
        m = CHOICE.match(line)
        if m and current is not None and m.group(1) != "Archive":
            result[current].append(m.group(1))
    return result


def varint(b, i):
    r = s = 0
    while True:
        c = b[i]
        i += 1
        r |= (c & 0x7F) << s
        s += 7
        if c < 0x80:
            return r, i


def fields(b):
    """(field number, wire type, value) of one protobuf message."""
    i, out = 0, []
    while i < len(b):
        key, i = varint(b, i)
        f, w = key >> 3, key & 7
        if w == 0:
            v, i = varint(b, i)
        elif w == 2:
            n, i = varint(b, i)
            v, i = b[i:i + n], i + n
        elif w == 1:
            v, i = b[i:i + 8], i + 8
        elif w == 5:
            v, i = b[i:i + 4], i + 4
        else:
            raise ValueError(f"unsupported wire type {w}")
        out.append((f, w, v))
    return out


def exercised(coverage):
    """{(choice, qualified template name, package id or 'local')} from TestResults.exercised."""
    pairs = set()
    for f, _, exercise in fields(open(coverage, "rb").read()):
        if f != 5:
            continue
        sub = fields(exercise)
        choice = next(v.decode() for g, _, v in sub if g == 1)
        for g, _, on in sub:
            if g != 2:
                continue
            for h, _, template in fields(on):
                if h != 1:
                    continue
                name, package = None, "local"
                for k, _, v in fields(template):
                    if k == 1:
                        name = v.decode()
                    elif k == 2:
                        for kind, _, pv in fields(v):
                            if kind == 2:
                                package = next(x.decode() for n2, _, x in fields(pv) if n2 == 1)
                pairs.add((choice, name, package))
    return pairs


def manual_pairs(path, section):
    """(choice, template) rows of one package section of the maintained list."""
    pairs, inside = set(), False
    for line in open(path):
        if line.startswith("## "):
            inside = line.strip() == f"## `{section}`"
            continue
        m = re.match(r"^\| `(\w+)` \| `(\w+)` \|", line)
        if inside and m:
            pairs.add((m.group(1), m.group(2)))
    return pairs


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dar", required=True)
    p.add_argument("--coverage", required=True)
    p.add_argument("--interface-dars", nargs="+", required=True)
    p.add_argument("--manual")
    p.add_argument("--manual-section")
    p.add_argument("--sdk", default="3.4.11")
    a = p.parse_args()

    package, lines = inspect(a.dar, a.sdk)
    instances = [INSTANCE.match(line).groups() for line in lines if INSTANCE.match(line)]
    catalogue = {}
    for dar in a.interface_dars:
        pkg, ilines = inspect(dar, a.sdk)
        catalogue[pkg] = interface_choices(ilines)
    expected = set()
    for ipkg, imod, iname, tmod, tname in instances:
        if ipkg not in catalogue:
            sys.exit(f"interface-coverage: no DAR given for package {ipkg} ({imod}:{iname})")
        choices = catalogue[ipkg].get((imod, iname))
        if choices is None:
            sys.exit(f"interface-coverage: {imod}:{iname} not found in package {ipkg}")
        for c in choices:
            expected.add((c, f"{tmod}:{tname}"))

    done = {(c, t) for c, t, pkg in exercised(a.coverage) if pkg == package}
    missing = sorted(expected - done)
    print(f"interface-coverage: {os.path.basename(a.dar)} (package {package[:16]}): "
          f"{len(instances)} interface instances, {len(expected)} interface choices")
    for c, t in sorted(expected):
        print(f"interface-coverage:   {'exercised' if (c, t) in done else 'NOT EXERCISED'}  {c} on {t}")
    status = 0
    if missing:
        status = 1
    if a.manual:
        listed = manual_pairs(a.manual, a.manual_section)
        short = {(c, t.split(":")[-1]) for c, t in expected}
        only_listed, only_derived = sorted(listed - short), sorted(short - listed)
        for c, t in only_listed:
            print(f"interface-coverage: listed in {a.manual} but not derived: {c} on {t}")
        for c, t in only_derived:
            print(f"interface-coverage: derived but not listed in {a.manual}: {c} on {t}")
        print(f"interface-coverage: cross-check with {a.manual}: {len(listed)} listed, "
              f"{len(short)} derived, {len(only_listed) + len(only_derived)} differences")
        if only_listed or only_derived:
            status = 1
    print(f"interface-coverage: {'OK' if status == 0 else 'FAIL'}: "
          f"{len(expected) - len(missing)} of {len(expected)} exercised")
    return status


if __name__ == "__main__":
    sys.exit(main())
