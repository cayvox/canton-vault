#!/usr/bin/env python3
"""Mutation testing of `cvx-vault-math-v1` (gate Q-07, docs/TESTING.md).

Each mutant is one exact source replacement in the package. For each, the
script copies the package and its test package into a scratch workspace,
applies the mutant, builds the package, runs `dpm test` on the test package
and records the tests that fail. A mutant is killed when the build of the
tests or at least one test fails, or when the run exceeds its time limit; it
survives when every test passes. The unmutated tree is run first and must
pass.

The repository tree is never modified.

Usage: scripts/mutate-math.py [--sdk 3.4.11] [--only M01,M02] [--timeout 600]
Exit status: 0 when no mutant survives and the baseline passes; 1 otherwise.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "packages/utils/vault-math-v1"
TEST = "test/vault-math-v1-test"
PUBLIC = f"{PKG}/daml/Cayvox/VaultMathV1.daml"
INTERNAL = f"{PKG}/daml/Cayvox/VaultMathV1/Internal.daml"

# (id, area, description, file, old, new). `old` must occur exactly once.
MUTANTS = [
    # Rounding direction.
    ("M01", "rounding", "Floor and Ceil swapped", PUBLIC,
     "mulDivChecked (r == Ceil) a b c", "mulDivChecked (r == Floor) a b c"),
    ("M02", "rounding", "always Ceil", PUBLIC,
     "mulDivChecked (r == Ceil) a b c", "mulDivChecked True a b c"),
    ("M03", "rounding", "always Floor", PUBLIC,
     "mulDivChecked (r == Ceil) a b c", "mulDivChecked False a b c"),
    ("M04", "rounding", "Ceil remainder test inverted", INTERNAL,
     "if roundUp && not (null r) then", "if roundUp && null r then"),
    ("M05", "rounding", "Ceil adds one unit without testing the remainder", INTERNAL,
     "if roundUp && not (null r) then", "if roundUp then"),
    ("M06", "rounding", "Ceil adds two units", INTERNAL,
     "addLimbs q [1] else q", "addLimbs q [2] else q"),
    # Failure conditions, identifiers and category.
    ("M07", "failure", "negative b not checked", INTERNAL,
     "| a < 0.0 || b < 0.0 = Left errNegativeOperand", "| a < 0.0 = Left errNegativeOperand"),
    ("M08", "failure", "negative a not checked", INTERNAL,
     "| a < 0.0 || b < 0.0 = Left errNegativeOperand", "| b < 0.0 = Left errNegativeOperand"),
    ("M09", "failure", "zero a rejected as negative", INTERNAL,
     "| a < 0.0 || b < 0.0 = Left errNegativeOperand", "| a <= 0.0 || b < 0.0 = Left errNegativeOperand"),
    ("M10", "failure", "zero b rejected as negative", INTERNAL,
     "| a < 0.0 || b < 0.0 = Left errNegativeOperand", "| a < 0.0 || b <= 0.0 = Left errNegativeOperand"),
    ("M11", "failure", "zero divisor accepted", INTERNAL,
     "| c <= 0.0 = Left errNonPositiveDivisor", "| c < 0.0 = Left errNonPositiveDivisor"),
    ("M12", "failure", "divisor of one unit rejected", INTERNAL,
     "| c <= 0.0 = Left errNonPositiveDivisor", "| c <= 0.0000000001 = Left errNonPositiveDivisor"),
    ("M13", "failure", "divisor checked before the operands", INTERNAL,
     "  | a < 0.0 || b < 0.0 = Left errNegativeOperand\n  | c <= 0.0 = Left errNonPositiveDivisor\n",
     "  | c <= 0.0 = Left errNonPositiveDivisor\n  | a < 0.0 || b < 0.0 = Left errNegativeOperand\n"),
    ("M14", "failure", "result equal to DMAX rejected", INTERNAL,
     "if compareLimbs rounded dmaxLimbs == GT", "if compareLimbs rounded dmaxLimbs /= LT"),
    ("M15", "failure", "DMAX limbs one unit short at the top", INTERNAL,
     "dmaxLimbs = [999999999, 999999999, 999999999, 999999999, 99]",
     "dmaxLimbs = [999999999, 999999999, 999999999, 999999999, 98]"),
    ("M16", "failure", "overflow identifier changed", INTERNAL,
     'failure "math-overflow"', 'failure "math-overflows"'),
    ("M17", "failure", "negative-operand identifier changed", INTERNAL,
     'failure "math-negative-operand"', 'failure "math-negative"'),
    ("M18", "failure", "non-positive-divisor identifier changed", INTERNAL,
     'failure "math-non-positive-divisor"', 'failure "math-zero-divisor"'),
    ("M19", "failure", "failure category changed", INTERNAL,
     "  category = InvalidGivenCurrentSystemStateOther\n", "  category = InvalidIndependentOfSystemState\n"),
    ("M20", "failure", "failures swallowed as zero", PUBLIC,
     "either failWithStatusPure identity", "either (const 0.0) identity"),
    # Conversion scaling.
    ("M21", "conversion", "natToNumeric0 drops the odd bit", INTERNAL,
     "in if n % 2 == 1 then twice + 1.0 else twice", "in twice"),
    ("M22", "conversion", "limb 3 exposed at scale 26 instead of 27", INTERNAL,
     "l3 = truncate (shift @27 r4)", "l3 = truncate (shift @26 r4)"),
    ("M23", "conversion", "limb 3 not removed before limb 2 is read", INTERNAL,
     "r3 = r4 - limbValue 3 l3", "r3 = r4"),
    ("M24", "conversion", "the top limb left out on the way out", INTERNAL,
     "zipWith limbValue [0 .. 4] (padTo 5 (normalize limbs))",
     "zipWith limbValue [0 .. 3] (padTo 5 (normalize limbs))"),
    ("M25", "conversion", "limb 1 placed at scale 8 instead of 9", INTERNAL,
     "limbValue 1 l = shift @10 (cast @9 (natToNumeric0 l))",
     "limbValue 1 l = shift @10 (cast @8 (natToNumeric0 l))"),
    # Normalization and comparison.
    ("M26", "normalization", "zero top limbs kept", INTERNAL,
     "normalize = dropWhileEnd (== 0)", "normalize = identity"),
    ("M27", "comparison", "limbs compared least significant first", INTERNAL,
     "EQ -> compare (reverse a') (reverse b')", "EQ -> compare a' b'"),
    ("M28", "comparison", "longer limb list compares smaller", INTERNAL,
     "in case compare (length a') (length b') of", "in case compare (length b') (length a') of"),
    # Carries.
    ("M29", "carry", "addition drops the carry between limbs", INTERNAL,
     "addCarry (x :: xs) (y :: ys) c = let s = x + y + c in (s % base) :: addCarry xs ys (s / base)",
     "addCarry (x :: xs) (y :: ys) c = let s = x + y + c in (s % base) :: addCarry xs ys 0"),
    ("M30", "carry", "addition drops the final carry", INTERNAL,
     "addCarry [] [] c = if c == 0 then [] else [c]", "addCarry [] [] c = []"),
    ("M31", "carry", "limb product drops the carry between limbs", INTERNAL,
     "(p % base) :: mulCarry m xs (p / base)", "(p % base) :: mulCarry m xs 0"),
    ("M32", "carry", "limb product drops the final carry", INTERNAL,
     "mulCarry _ [] c = if c == 0 then [] else [c]", "mulCarry _ [] c = []"),
    ("M33", "carry", "product rows shifted one limb too far", INTERNAL,
     "replicate i 0 ++ mulSmall b ai", "replicate (i + 1) 0 ++ mulSmall b ai"),
    ("M34", "carry", "add-back drops its carry", INTERNAL,
     "in (s % base) :: addBackGo ws vs' (s / base)", "in (s % base) :: addBackGo ws vs' 0"),
    ("M35", "carry", "multiply-subtract drops its borrow", INTERNAL,
     "if diff < 0 then (diff + base, 1) else (diff, 0)", "if diff < 0 then (diff + base, 0) else (diff, 0)"),
    # Division.
    ("M36", "division", "short division ignores the running remainder", INTERNAL,
     "let cur = r * base + x in", "let cur = x in"),
    ("M37", "division", "single-limb divisor drops the remainder", INTERNAL,
     "in (q, normalize [r])", "in (q, [])"),
    ("M38", "division", "dividend below divisor drops the remainder", INTERNAL,
     "== LT -> ([], u)", "== LT -> ([], [])"),
    ("M39", "division", "D1 normalization skipped", INTERNAL,
     "d = base / (last v + 1)", "d = 1"),
    ("M40", "division", "D3 numerator without its second limb", INTERNAL,
     "let num = (un !! (j + n)) * base + (un !! (j + n - 1))", "let num = (un !! (j + n)) * base"),
    ("M41", "division", "D3 test with the wrong dividend limb", INTERNAL,
     "(un !! (j + n - 2))", "(un !! (j + n - 1))"),
    ("M42", "division", "D3 test with the top divisor limb as the next", INTERNAL,
     "vNext = vn !! (n - 2)", "vNext = vn !! (n - 1)"),
    ("M43", "division", "D3 test strict inequality weakened", INTERNAL,
     "q * vNext > r * base + uNext", "q * vNext >= r * base + uNext"),
    ("M44", "division", "D4 negative result never detected", INTERNAL,
     "in (res, carry + borrow > 0)", "in (res, carry + borrow > 1)"),
    ("M45", "division", "D6 adds back without lowering the quotient limb", INTERNAL,
     "then (addBack window vn, qhat - 1)", "then (addBack window vn, qhat)"),
    ("M46", "division", "D6 lowers the quotient limb without adding back", INTERNAL,
     "then (addBack window vn, qhat - 1)", "then (window, qhat - 1)"),
    ("M47", "division", "D8 remainder not unnormalized", INTERNAL,
     "remainder = fst (divSmall (take n uFinal) d)", "remainder = take n uFinal"),
]


def run(cmd, cwd, sdk, timeout):
    env = dict(os.environ, DPM_SDK_VERSION=sdk)
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout + r.stderr, False
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return None, out, True


def evaluate(work, sdk, timeout):
    """(outcome, failing tests) for the workspace as it is."""
    code, out, _ = run(["dpm", "build", "--enable-multi-package=no"], os.path.join(work, PKG), sdk, timeout)
    if code != 0:
        return "package build failed", []
    code, out, timed_out = run(["dpm", "test"], os.path.join(work, TEST), sdk, timeout)
    if timed_out:
        return "test run exceeded the time limit", []
    failed = sorted(set(re.findall(r"daml/[^\s:]+\.daml:(test_\w+): failed", out)))
    passed = re.findall(r"daml/[^\s:]+\.daml:(test_\w+): ok", out)
    if failed:
        return "tests failed", failed
    if code != 0:
        return "test build failed", []
    if not passed:
        return "no test ran", []
    return "all tests passed", []


def fresh_workspace():
    work = tempfile.mkdtemp(prefix="mutate-math-")
    for rel in (PKG, TEST):
        shutil.copytree(os.path.join(ROOT, rel), os.path.join(work, rel),
                        ignore=shutil.ignore_patterns(".daml"))
    return work


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sdk", default="3.4.11")
    p.add_argument("--only", default="")
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    only = set(filter(None, args.only.split(",")))
    mutants = [m for m in MUTANTS if not only or m[0] in only]

    # Every mutant must apply exactly once to the current sources.
    for mid, _, _, path, old, _ in mutants:
        count = open(os.path.join(ROOT, path)).read().count(old)
        if count != 1:
            print(f"mutate: {mid} matches {count} times in {path}; fix the mutant")
            return 1

    work = fresh_workspace()
    try:
        start = time.time()
        outcome, failed = evaluate(work, args.sdk, args.timeout)
        print(f"baseline (SDK {args.sdk}): {outcome} ({time.time() - start:.0f} s)")
        if outcome != "all tests passed":
            return 1
        survivors = 0
        print("| Mutant | Area | Mutation | Location | Result | Killed by |")
        print("|---|---|---|---|---|---|")
        for mid, area, desc, path, old, new in mutants:
            shutil.rmtree(work)
            work = fresh_workspace()
            target = os.path.join(work, path)
            src = open(target).read()
            line = src[:src.index(old)].count("\n") + 1
            open(target, "w").write(src.replace(old, new, 1))
            outcome, failed = evaluate(work, args.sdk, args.timeout)
            killed = outcome != "all tests passed"
            survivors += 0 if killed else 1
            by = ", ".join(f"`{t}`" for t in failed) if failed else outcome
            print(f"| {mid} | {area} | {desc} | `{os.path.basename(path)}:{line}` | "
                  f"{'killed' if killed else 'SURVIVED'} | {by if killed else ''} |", flush=True)
        print(f"mutate: SDK {args.sdk}: {len(mutants)} mutants, {len(mutants) - survivors} killed, "
              f"{survivors} surviving")
        return 0 if survivors == 0 else 1
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
