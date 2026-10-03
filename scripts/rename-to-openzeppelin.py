#!/usr/bin/env python3
"""The D-17 rename (docs/DECISIONS.md): from the working names to the
canton-contracts form, into a copy outside the repository.

  package names   cvx-<name>          ->  openzeppelin-<name>
  modules         Cayvox.<Module>     ->  OpenZeppelin.<Module>, with the
                                          daml/Cayvox directories moved
  error domain    cayvox.com/<name>   ->  openzeppelin.com/<name>, the form
                                          openzeppelin.com/<component>-<failure>
                                          of canton-contracts at aeca01d
                                          (packages/security/pausable-v1/
                                          daml/OpenZeppelin/PausableV1/
                                          Internal.daml:11; packages/access/
                                          scoped-authorization-grant-v1/daml/
                                          OpenZeppelin/ScopedAuthorizationGrantV1/
                                          Internal.daml:84-96)
  other names     Cayvox              ->  OpenZeppelin, in code, scripts and
                                          package READMEs
                  cvx, cayvox (words) ->  openzeppelin: the package prefix
                                          of scripts/check.sh

Test packages already sit at test/<component>-vN-test and the example at
examples/<example>-vN with com-example-* names and Example.* modules, the
layout of canton-contracts at aeca01d (CONTRIBUTING.md:59-61, 92-93), so
those paths and names are not renamed.

It copies the files git tracks (no build outputs), renames paths and
contents under packages/, test/, scripts/, examples/ and tools/, in
dars/api-packages.yaml, multi-package.yaml, CHANGELOG.md, the package
READMEs and docs/INTERFACE-CHOICES.md, the one document a gate reads (Q-03,
by package name), and leaves the rest of docs/ as it is. API package IDs depend on the package name, so it builds each API package with SDK 3.4.11 in the copy and
records the new main package ID in the copy's dars/api-packages.yaml (D-11).
Finally it fails if a working name is left in a renamed file.

The repository is never modified, and the renamed tree is never committed.

Usage: scripts/rename-to-openzeppelin.py DEST     (DEST must not exist and must lie outside the repository)
"""

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RENAMED_PREFIXES = ("packages/", "test/", "scripts/", "examples/", "tools/")
RENAMED_FILES = {"dars/api-packages.yaml", "multi-package.yaml", "CHANGELOG.md", "docs/INTERFACE-CHOICES.md"}
TEXT = (".daml", ".yaml", ".sh", ".py", ".md", ".tsv", ".txt")
RULES = [
    (re.compile(r"cayvox\.com/"), "openzeppelin.com/"),
    (re.compile(r"\bcvx-"), "openzeppelin-"),
    (re.compile(r"\bcvx\b"), "openzeppelin"),
    (re.compile(r"\bCayvox\b"), "OpenZeppelin"),
    (re.compile(r"\bcayvox\b"), "openzeppelin"),
]
LEFT = re.compile(r"cayvox|\bcvx\b", re.IGNORECASE)


# The rename's own rules name the working names; it is copied unchanged.
UNCHANGED = {"scripts/rename-to-openzeppelin.py"}


def renamed(rel):
    return (rel.startswith(RENAMED_PREFIXES) or rel in RENAMED_FILES) and rel not in UNCHANGED


def rename_path(rel):
    if not renamed(rel):
        return rel
    return "/".join("OpenZeppelin" if part == "Cayvox" else part for part in rel.split("/"))


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    dest = os.path.abspath(sys.argv[1])
    if os.path.exists(dest):
        sys.exit(f"rename: {dest} exists")
    if dest == ROOT or dest.startswith(ROOT + os.sep):
        sys.exit("rename: the destination must lie outside the repository")
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.decode().split("\0")
    files = [f for f in files if f]
    changed = 0
    for rel in files:
        src = os.path.join(ROOT, rel)
        out = os.path.join(dest, rename_path(rel))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        if renamed(rel) and rel.endswith(TEXT) and not rel.startswith("dars/vendor/"):
            text = open(src, encoding="utf-8").read()
            new = text
            for pattern, replacement in RULES:
                new = pattern.sub(replacement, new)
            changed += new != text
            open(out, "w", encoding="utf-8").write(new)
            shutil.copymode(src, out)
        else:
            shutil.copy2(src, out)
    print(f"rename: {len(files)} files copied, {changed} renamed in content")

    # D-11: record the renamed API packages' IDs, built once by SDK 3.4.11.
    record = os.path.join(dest, "dars/api-packages.yaml")
    text = open(record).read()
    for path in re.findall(r"^    path: (\S+)$", text, flags=re.M):
        pkg = os.path.join(dest, path)
        subprocess.run(["dpm", "build", "--enable-multi-package=no"], cwd=pkg, check=True,
                       capture_output=True, env=dict(os.environ, DPM_SDK_VERSION="3.4.11"))
        dar = next(os.path.join(pkg, ".daml/dist", f) for f in os.listdir(os.path.join(pkg, ".daml/dist")))
        inspect = subprocess.run(["dpm", "damlc", "inspect-dar", dar], capture_output=True, text=True, check=True,
                                 env=dict(os.environ, DPM_SDK_VERSION="3.4.11")).stdout
        name = os.path.basename(dar)[:-len(".dar")]
        new_id = re.search(rf"{re.escape(name)}-([0-9a-f]{{64}})", inspect).group(1)
        block = re.search(rf"(  - package: [^\n]+\n(?:    [^\n]*\n)*?    path: {re.escape(path)}\n(?:    [^\n]*\n)*)", text).group(1)
        text = text.replace(block, re.sub(r"(    main-package-id: )[0-9a-f]{64}", rf"\g<1>{new_id}", block))
        print(f"rename: {path}: main package ID {new_id[:16]}")
    open(record, "w").write(text)

    left = []
    for rel in files:
        if renamed(rel) and rel.endswith(TEXT) and not rel.startswith("dars/vendor/"):
            for n, line in enumerate(open(os.path.join(dest, rename_path(rel)), encoding="utf-8"), 1):
                if LEFT.search(line):
                    left.append(f"{rename_path(rel)}:{n}: {line.strip()[:100]}")
    if left:
        print("\n".join(left[:20]))
        sys.exit(f"rename: {len(left)} working names left in renamed files")
    print(f"rename: OK, no working name left in renamed files ({dest})")


if __name__ == "__main__":
    main()
