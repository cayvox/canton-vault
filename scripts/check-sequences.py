#!/usr/bin/env python3
"""Gate Q-08: seeded operation sequences on the vault (docs/TESTING.md).

Runs `Cayvox.VaultV1Test.Sequences:runSequences` of the vault test package
with `dpm script --ide-ledger` on JSON input, in runs of CHUNK sequences on
parallel workers. Each sequence derives its mode, offset (0 or 10), number
of requesters and length (10 to 50 operations) from its seed, mixes
deposits, redemptions, cancellations, pauses, asset additions, batches and
donations, predicts every outcome from the vault's view, and checks I-01 to
I-08, K-01 and V-01 to V-05 after every step. The Daml module states each
check.

Each run's JVM gets a heap of at most 512 MB and the serial collector,
through the JDK's JAVA_TOOL_OPTIONS variable, unless the caller sets that
variable. With the JVM's defaults a run of 10 sequences peaks at about 1.1 GB
of memory, and six parallel runs push a 16 GB machine into swap; with the
bound a run peaks at about 430 MB at the same speed, so more runs fit in
parallel. The bound changes no sequence and no check: a run that exceeds it
fails, and the gate with it.

Usage:
  scripts/check-sequences.py --dar DAR --sdk SDK [--first N] [--count N] [--steps N] [--jobs N]
                             [--lines-out FILE]

Exit status: 0 when every sequence holds, 1 on a violation, 2 on a run error.
"""

import argparse
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

CHUNK = 10  # sequences per `dpm script` run
JVM_OPTIONS = "-Xmx512m -XX:+UseSerialGC"  # per run; see the module comment
SCRIPT = "Cayvox.VaultV1Test.Sequences:runSequences"
LINE = re.compile(r"^seed=(\d+) (\w+) k=(\d+) requesters=(\d+) operations=(\d+) checks=(\d+) \[(.*)\] (ok|VIOLATION .*)$")


def run_chunk(dar, sdk, first, count, steps):
    with tempfile.TemporaryDirectory() as work:
        inp = os.path.join(work, "in.json")
        outp = os.path.join(work, "out.json")
        with open(inp, "w") as f:
            json.dump({"first": first, "count": count, "steps": steps}, f)
        cmd = ["dpm", "script", "--dar", dar, "--script-name", SCRIPT,
               "--ide-ledger", "--static-time", "--input-file", inp, "--output-file", outp]
        env = dict(os.environ, DPM_SDK_VERSION=sdk)
        env.setdefault("JAVA_TOOL_OPTIONS", JVM_OPTIONS)
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            return first, None, r.stdout[-3000:] + r.stderr[-3000:]
        with open(outp) as f:
            return first, json.load(f), ""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dar", required=True)
    p.add_argument("--sdk", required=True)
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--steps", type=int, default=50)
    p.add_argument("--jobs", type=int, default=8)
    p.add_argument("--lines-out", help="file to write every sequence's result line to, in seed order")
    args = p.parse_args()

    starts = range(args.first, args.first + args.count, CHUNK)
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(
            lambda s: run_chunk(args.dar, args.sdk, s, min(CHUNK, args.first + args.count - s), args.steps), starts))

    lines = []
    for first, got, err in results:
        if got is None:
            sys.stderr.write(err)
            print(f"sequences: SDK {args.sdk}: the run from seed {first} failed")
            return 2
        lines.extend(got)
    if args.lines_out:
        with open(args.lines_out, "w") as f:
            f.write("\n".join(lines) + "\n")
    if len(lines) != args.count:
        print(f"sequences: SDK {args.sdk}: {len(lines)} results for {args.count} sequences")
        return 2

    by_config = collections.Counter()
    ops = collections.Counter()
    steps = checks = longest = 0
    violations = []
    for line in lines:
        m = LINE.match(line)
        if not m:
            print(f"sequences: unreadable result: {line[:300]}")
            return 2
        _, mode, k, n, nops, nchecks, oplist, verdict = m.groups()
        by_config[(mode, int(k), int(n))] += 1
        steps += int(nops)
        checks += int(nchecks)
        longest = max(longest, int(nops))
        for op in oplist.split(","):
            ops[re.sub(r"\d+", "", op)] += 1
        if verdict != "ok":
            violations.append(line)

    print(f"sequences: SDK {args.sdk}: seeds {args.first} to {args.first + args.count - 1}, "
          f"{len(lines)} sequences, {steps} operations (longest {longest}), {checks} invariant checks")
    for (mode, k, n), c in sorted(by_config.items()):
        print(f"sequences:   {mode} k={k} requesters={n}: {c} sequences")
    print("sequences:   operations: " + ", ".join(f"{op} {c}" for op, c in sorted(ops.items())))
    for v in violations[:10]:
        print(v[-3000:])
    print(f"sequences: SDK {args.sdk}: violations {len(violations)}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
