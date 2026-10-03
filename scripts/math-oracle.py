#!/usr/bin/env python3
"""Differential oracle for `cvx-vault-math-v1` (gate Q-06, docs/TESTING.md).

The oracle is Python `decimal` at 200 significant digits: for vectors
(a, b, c) it computes floor and ceil of the exact a * b / c, or the failure of
docs/MATH.md section 4 in the order of its table. The Daml side is
`Cayvox.VaultMathV1Test.Vectors:runVectors` in the test package, run with
`dpm script --ide-ledger` on JSON input.

Vectors:
  - edge vectors, each with a label: zeros, one unit, DMAX, results on and
    one unit off each rounding boundary, exact divisibility, c = u,
    c = DMAX, limb boundaries, results that just fit and just overflow,
    every failure condition and their order, and vectors that drive every
    path of Algorithm D (single-limb divisor, dividend below divisor, the
    qhat >= base correction, one and two D3 corrections, the D3 early exit
    and the D6 add-back), found with an instrumented mirror of the Daml
    algorithm;
  - seeded random vectors with mixed digit lengths, some of them failures.

It also checks the six conversion functions of `cvx-vault-v1`
(`Cayvox.VaultV1.Conversion`, docs/MATH.md section 7) against an exact model
of that section: the view checks, the asset-bound checks of a deposit and a
mint, and the failures of `mulDiv`, in that order. The Daml side is
`Cayvox.VaultV1Test.ConversionVectors:runConversionVectors` in
`test/vault-v1-test`. A conversion vector is a view (k, A, S) and an amount x:
  - edge vectors, each with a label, at k = 0, 1, 5 and 10: the empty vault,
    the largest A and S the bounds allow and one unit above, negative totals,
    the offsets -1 and 11, and amounts of zero, one unit, a negative unit,
    the deposit room and the mint room and one unit above each, DMAX, and
    amounts at exact divisibility and one unit on each side, in both
    directions;
  - seeded random vectors over k from 0 to 10, most of them within the
    bounds, some outside each.

Usage:
  scripts/math-oracle.py check --dar DAR --sdk SDK [--seed N] [--random N]
  scripts/math-oracle.py check-conversion --dar DAR --sdk SDK [--seed N] [--random N] [--jobs N]
  scripts/math-oracle.py paths                     # Algorithm D path coverage
  scripts/math-oracle.py emit-daml FILE            # the edge vectors as a Daml test module

Exit status: 0 when every vector matches, 1 on a mismatch, 2 on a run error.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D, getcontext

getcontext().prec = 200

U = D("0.0000000001")
N = 10**38 - 1  # int(DMAX)
BASE = 10**9
ERR_NEG = "cayvox.com/math-negative-operand"
ERR_DIV = "cayvox.com/math-non-positive-divisor"
ERR_OVF = "cayvox.com/math-overflow"


def dec(i):
    """The Decimal text whose int() is i."""
    sign = "-" if i < 0 else ""
    s = str(abs(i)).rjust(11, "0")
    return sign + s[:-10] + "." + s[-10:]


def to_int(text):
    return int(D(text) / U)


# Oracle
# ------

def oracle(a, b, c):
    """'floor|ceil' for Decimal texts a, b, c; each part a Decimal text or an error id."""
    ia, ib, ic = to_int(a), to_int(b), to_int(c)
    if ia < 0 or ib < 0:
        return ERR_NEG + "|" + ERR_NEG
    if ic <= 0:
        return ERR_DIV + "|" + ERR_DIV
    q, r = divmod(ia * ib, ic)
    parts = []
    for v in (q, q + (1 if r else 0)):
        parts.append(ERR_OVF if v > N else dec(v))
    return "|".join(parts)


def same(got, want):
    """Exact comparison of two 'floor|ceil' results."""
    g, w = got.split("|"), want.split("|")
    if len(g) != 2:
        return False
    for x, y in zip(g, w):
        if y.startswith("cayvox.com/") or x.startswith("cayvox.com/"):
            if x != y:
                return False
        elif D(x) != D(y):
            return False
    return True


# Instrumented mirror of the Daml algorithm (Internal.daml), for path coverage
# ----------------------------------------------------------------------------

def limbs(i):
    out = []
    while i:
        out.append(i % BASE)
        i //= BASE
    return out


def divmod_limbs_paths(u_int, v_int):
    """The set of Algorithm D paths that dividing u_int by v_int takes."""
    paths = set()
    u, v = limbs(u_int), limbs(v_int)
    if len(v) == 1:
        paths.add("single-limb divisor")
        return paths
    if u_int < v_int:
        paths.add("dividend below divisor")
        return paths
    paths.add("algorithm D")
    n, m = len(v), len(u) - len(v)
    d = BASE // (v[-1] + 1)
    if d == 1:
        paths.add("D1 d = 1")
    un = limbs(u_int * d)
    un += [0] * (m + n + 1 - len(un))
    vn = limbs(v_int * d)
    vtop, vnext = vn[n - 1], vn[n - 2]
    for j in range(m, -1, -1):
        num = un[j + n] * BASE + un[j + n - 1]
        q, r = num // vtop, num % vtop
        if q >= BASE:
            paths.add("D3 qhat >= base")
        steps = 0
        while True:
            if q >= BASE or q * vnext > r * BASE + un[j + n - 2]:
                q, r, steps = q - 1, r + vtop, steps + 1
                if r >= BASE:
                    paths.add("D3 early exit")
                    break
                continue
            break
        if steps == 1:
            paths.add("D3 one correction")
        if steps >= 2:
            paths.add("D3 two corrections")
        window = sum(x * BASE**i for i, x in enumerate(un[j:j + n + 1]))
        diff = window - q * v_int * d
        if diff < 0:
            paths.add("D6 add-back")
            q -= 1
            diff += v_int * d
        for i in range(n + 1):
            un[j + i] = (diff // BASE**i) % BASE
    return paths


ALL_PATHS = [
    "single-limb divisor",
    "dividend below divisor",
    "algorithm D",
    "D1 d = 1",
    "D3 qhat >= base",
    "D3 one correction",
    "D3 two corrections",
    "D3 early exit",
    "D6 add-back",
]


# Edge vectors
# ------------

def rounding_boundary(ib, ic, q, r):
    """(ia, ib, ic) with ia * ib = q * ic + r, when ib is invertible mod ic, else None."""
    p = q * ic + r
    if p % ib == 0 and p // ib <= N:
        return (p // ib, ib, ic)
    return None


def knuth_candidates():
    """Dividends and divisors built to reach the rare paths of Algorithm D.

    For a divisor V whose top limb is at least base / 2 (so D1 uses d = 1)
    and U = t * V - s with 0 < s <= t * v0, the D3 test sees only the top two
    limbs of V and accepts qhat = t, while the true quotient is t - 1: D6
    adds back. U just below V * base makes the top limb of U equal to that of
    V, so D3 starts with qhat >= base and exits early. Unnormalized divisors
    (top limb below base / 2) go through D1 with d > 1.
    """
    h = BASE // 2
    for v2 in [h, h + 1, BASE - 1, 3, 99]:
        for v1 in [0, 1, BASE - 2, BASE - 1]:
            for v0 in [0, 1, BASE - 1]:
                for extra in [[], [BASE - 1]]:
                    v = sum(x * BASE**i for i, x in enumerate(extra + [v0, v1, v2]))
                    for t in [1, 2, h, BASE - 2, BASE - 1]:
                        for s in [1, 2, t * v0 // 2, t * v0, t * v0 + 1, v - 1]:
                            for u in [t * v - s, t * v + s, v * BASE - s]:
                                if 0 < u:
                                    yield u, v


def knuth_vectors(wanted, per_path=3):
    """(label, ia, ib, ic) with ia * ib = U and ic = V, for each Algorithm D path.

    U is split as ia * ib with both at most DMAX: ib = 1 (b = u) when U fits,
    else the largest power of 10^9 that leaves ia within DMAX and divides U.
    """
    found = {}
    for u, v in knuth_candidates():
        if v > N:
            continue
        ib = 1
        while u // ib > N and ib < 10**36:
            ib *= BASE
        if u % ib != 0:
            u -= u % ib  # keep the split exact; the path is re-checked below
        ia = u // ib
        if not (0 < ia <= N and 0 < ib <= N):
            continue
        for path in divmod_limbs_paths(ia * ib, v):
            if path in wanted and len(found.setdefault(path, [])) < per_path:
                if (ia, ib, v) not in found[path]:
                    found[path].append((ia, ib, v))
        if all(len(found.get(p, [])) >= per_path for p in wanted):
            break
    out = []
    for path in wanted:
        for k, (ia, ib, ic) in enumerate(found.get(path, [])):
            out.append((f"knuth: {path} #{k + 1}", ia, ib, ic))
    return out


def edge_vectors():
    """Labelled edge vectors as (label, a, b, c) Decimal texts."""
    v = []

    def add(label, ia, ib, ic):
        v.append((label, dec(ia), dec(ib), dec(ic)))

    one = 10**10  # int(1.0)
    # Zeros.
    add("zero: 0 * 0 / u", 0, 0, 1)
    add("zero: 0 * DMAX / u", 0, N, 1)
    add("zero: DMAX * 0 / DMAX", N, 0, N)
    add("zero: 0 * 0 / DMAX", 0, 0, N)
    # One unit.
    add("unit: u * u / u", 1, 1, 1)
    add("unit: u * u / 1", 1, 1, one)
    add("unit: u * 1 / u", 1, one, 1)
    add("unit: u * u / DMAX", 1, 1, N)
    add("unit: 1 * 1 / 1", one, one, one)
    add("unit: u * DMAX / DMAX", 1, N, N)
    # DMAX.
    add("dmax: DMAX * 1 / 1", N, one, one)
    add("dmax: DMAX * DMAX / DMAX", N, N, N)
    add("dmax: DMAX * u / u", N, 1, 1)
    add("dmax: DMAX * DMAX / u (overflow)", N, N, 1)
    add("dmax: DMAX * DMAX / 1 (overflow)", N, N, one)
    add("dmax: DMAX * (1 + u) / 1 (overflow)", N, one + 1, one)
    add("dmax: DMAX * 1 / (1 + u)", N, one, one + 1)
    add("dmax: DMAX * DMAX / (DMAX - u)", N, N, N - 1)
    add("dmax: (DMAX - u) * DMAX / DMAX", N - 1, N, N)
    add("dmax: DMAX * (DMAX - u) / DMAX", N, N - 1, N)
    # Rounding boundaries: remainder 0, 1 and c - 1, at small, mid and top results.
    for ib, ic in [(1, 7), (1, 3 * one), (10**9 + 7, 10**18 + 9), (97, N), (1, 10**20 + 1)]:
        for q in [0, 1, 12345678901, 10**27, N - 1, N, N + 1]:
            for r_name, r in [("0", 0), ("1", 1), ("c - 1", ic - 1)]:
                t = rounding_boundary(ib, ic, q, r)
                if t is not None:
                    add(f"boundary: q = {q}, r = {r_name}, c = {ic}", *t)
    for ib, ic in [(3, 7), (10**18 + 3, 10**27 + 7), (999999937, N - 2)]:
        inv = pow(ib, -1, ic)
        for q_hint in [0, 10**20, N - 1, N]:
            for r_name, r in [("1", 1), ("c - 1", ic - 1)]:
                ia = (r * inv) % ic
                p = ia * ib
                target = q_hint * ic
                # Lift ia by multiples of ic toward the target quotient, within DMAX.
                t = max(0, (target - p) // (ib * ic))
                ia2 = ia + t * ic
                if ia2 > N:
                    ia2 -= ((ia2 - N + ic - 1) // ic) * ic
                if 0 <= ia2 <= N:
                    add(f"boundary: r = {r_name}, q ~ {q_hint}, b = {ib}, c = {ic}", ia2, ib, ic)
    # Just fit and just overflow, for both directions.
    for ib, ic in [(1, 1), (3, 1), (7, 3), (10**10, 10**10 - 1), (N, N - 1)]:
        for q, r in [(N, 0), (N, 1), (N - 1, ic - 1), (N + 1, 0)]:
            p = q * ic + r
            if p % ib == 0 and p // ib <= N:
                add(f"fit: q = {'DMAX' if q == N else q}, r = {r}, b = {ib}, c = {ic}", p // ib, ib, ic)
    # Floor quotient q with a non-zero remainder: ceil is q + 1. The smallest
    # ia with ia * ib >= q * ic leaves r = ia * ib - q * ic below ib, so ib is
    # scanned upward from ic until 0 < r < ic.
    for q, name in [(N - 1, "floor = DMAX - u, ceil = DMAX"), (N, "floor = DMAX, ceil overflows"),
                    (N + 1, "floor overflows by one unit")]:
        for ic in [10**10, 10**20 + 7, N - 5]:
            for ib in range(ic, ic + 5000):
                ia = -(-q * ic // ib)
                r = ia * ib - q * ic
                if ia <= N and 0 < r < ic:
                    add(f"fit: {name}, c = {ic}", ia, ib, ic)
                    break
    # Exact divisibility (M-04), c = u and c = DMAX.
    add("exact: 6 * 7 / 3", 6 * one, 7 * one, 3 * one)
    add("exact: a * c / c", 123456789 * 10**12 + 5, 10**20 + 3, 10**20 + 3)
    add("exact: DMAX * 3 / 3", N, 3, 3)
    add("exact: 10^28 * 10^9 / 10^18", 10**28, 10**9, 10**18)
    add("c = u: small", 12345, 678, 1)
    add("c = u: 10^19 * 10^18 (fits)", 10**19, 10**18, 1)
    add("c = u: 10^19 * 10^19 (overflow)", 10**19, 10**19, 1)
    add("c = DMAX: DMAX * u", N, 1, N)
    add("c = DMAX: 10^37 * 10^37", 10**37, 10**37, N)
    # Limb boundaries.
    for x in [BASE - 1, BASE, BASE + 1, BASE**2 - 1, BASE**2, BASE**2 + 1,
              BASE**3 - 1, BASE**3, BASE**3 + 1, BASE**4 - 1, BASE**4, BASE**4 + 1, 10**37, 10**38 - 10**36]:
        add(f"limb: x * 1 / 1, x = {x}", x, one, one)
        add(f"limb: x * x / x, x = {x}", x, x, x)
        add(f"limb: x * u / (x - 1)", x, 1, x - 1)
        add(f"limb: DMAX * (x - 1) / x", N, x - 1, x)
        add(f"limb: (x + 1) * (x - 1) / x", x + 1, x - 1, x)
    # Failures and their order.
    add("fail: a = -u", -1, one, one)
    add("fail: b = -u", one, -1, one)
    add("fail: a = -DMAX", -N, N, N)
    add("fail: c = 0", one, one, 0)
    add("fail: c = -u", one, one, -1)
    add("fail: c = -DMAX", N, N, -N)
    add("fail order: a < 0 and c = 0", -1, one, 0)
    add("fail order: b < 0 and c < 0", one, -one, -one)
    add("fail order: a < 0 and overflow", -N, N, 1)
    add("fail order: c = 0 and a = 0", 0, 0, 0)
    add("fail order: c = 0 and huge product", N, N, 0)
    add("fail: overflow, floor", N, 2, 1)
    # Commutativity (M-06).
    add("swap: a, b", 987654321987654321, 123456789123, 55555555555)
    add("swap: b, a", 123456789123, 987654321987654321, 55555555555)
    # Algorithm D paths.
    for label, ia, ib, ic in knuth_vectors(ALL_PATHS):
        add(label, ia, ib, ic)
    return v


def random_vectors(seed, count):
    rng = random.Random(seed)
    lengths = [1, 2, 5, 9, 10, 11, 18, 19, 20, 27, 28, 29, 30, 36, 37, 38]
    out = []

    def rnd():
        return rng.randrange(0, 10**rng.choice(lengths))

    for i in range(count):
        ia, ib, ic = rnd(), rnd(), rnd() or 1
        roll = rng.random()
        if roll < 0.01:
            ia = -ia - 1
        elif roll < 0.02:
            ib = -ib - 1
        elif roll < 0.03:
            ic = -rnd()
        out.append((f"random {i}", dec(ia), dec(ib), dec(ic)))
    return out


# Commands
# --------

CHUNK = 2000  # vectors per `dpm script` run; one run of 20,000 overflows the runner's stack


def run_daml(dar, sdk, vectors):
    """The Daml results for the vectors, in runs of at most CHUNK vectors."""
    out = []
    for i in range(0, len(vectors), CHUNK):
        got = run_daml_once(dar, sdk, vectors[i:i + CHUNK])
        if got is None:
            return None
        out.extend(got)
    return out


def run_daml_once(dar, sdk, vectors):
    with tempfile.TemporaryDirectory() as work:
        inp = os.path.join(work, "in.json")
        outp = os.path.join(work, "out.json")
        with open(inp, "w") as f:
            json.dump([{"a": a, "b": b, "c": c} for (_, a, b, c) in vectors], f)
        cmd = ["dpm", "script", "--dar", dar, "--script-name", "Cayvox.VaultMathV1Test.Vectors:runVectors",
               "--ide-ledger", "--static-time", "--input-file", inp, "--output-file", outp]
        r = subprocess.run(cmd, env=dict(os.environ, DPM_SDK_VERSION=sdk), capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
            return None
        with open(outp) as f:
            return json.load(f)


def cmd_check(args):
    edges = edge_vectors()
    rand = random_vectors(args.seed, args.random)
    status = 0
    for name, vectors in [("edge", edges), ("random", rand)]:
        got = run_daml(args.dar, args.sdk, vectors)
        if got is None or len(got) != len(vectors):
            print(f"oracle: SDK {args.sdk}: {name} run failed")
            return 2
        bad = 0
        failures = 0
        for (label, a, b, c), g in zip(vectors, got):
            want = oracle(a, b, c)
            failures += want.count("cayvox.com/")
            if not same(g, want):
                bad += 1
                if bad <= 10:
                    print(f"MISMATCH {label}: a={a} b={b} c={c} got {g} want {want}")
        print(f"oracle: SDK {args.sdk}: {name} vectors {len(vectors)}, "
              f"failure results {failures}, mismatches {bad}"
              + (f" (seed {args.seed})" if name == "random" else ""))
        if bad:
            status = 1
    return status


def cmd_paths(_args):
    hit = {}
    for label, a, b, c in edge_vectors():
        ia, ib, ic = to_int(a), to_int(b), to_int(c)
        if ia < 0 or ib < 0 or ic <= 0:
            continue
        for p in divmod_limbs_paths(ia * ib, ic):
            hit.setdefault(p, []).append(label)
    status = 0
    for p in ALL_PATHS:
        n = len(hit.get(p, []))
        print(f"paths: {p:<24} {n:>4} edge vectors" + ("" if n else "  MISSING"))
        if not n:
            status = 1
    return status


def cmd_emit(args):
    lines = [
        "-- | Edge vectors of `docs/MATH.md` with the results of the Python `decimal`",
        "-- oracle at 200 digits. Produced by `scripts/math-oracle.py emit-daml`;",
        "-- do not edit by hand.",
        "module Cayvox.VaultMathV1Test.EdgeVectors (EdgeVector (..), edgeVectors) where",
        "",
        "-- | A labelled vector and its expected \"floor|ceil\" result.",
        "data EdgeVector = EdgeVector with",
        "    label : Text",
        "    a : Text",
        "    b : Text",
        "    c : Text",
        "    expected : Text",
        "  deriving (Eq, Show)",
        "",
        "-- | Every edge vector.",
        "edgeVectors : [EdgeVector]",
        "edgeVectors =",
    ]
    for k, (label, a, b, c) in enumerate(edge_vectors()):
        want = oracle(a, b, c)
        sep = "[" if k == 0 else ","
        lines.append(f"  {sep} EdgeVector with label = {json.dumps(label)}; a = \"{a}\"; b = \"{b}\"; "
                     f"c = \"{c}\"; expected = \"{want}\"")
    lines.append("  ]")
    with open(args.file, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"oracle: wrote {len(edge_vectors())} edge vectors to {args.file}")
    return 0


# Conversion functions (docs/MATH.md, section 7)
# ----------------------------------------------

ERR_CAP = "cayvox.com/vault-capacity-exceeded"
CONV_CHUNK = 500  # vectors per `dpm script` run; six results each, and 2000 overflow the runner's stack
KMAX = 10
FUNCTIONS = ["convertToShares", "convertToAssets", "previewDeposit", "previewMint", "previewWithdraw", "previewRedeem"]


def mul_div(a, b, c, ceil):
    """mulDiv on ints in units: a result text or a failure id (docs/MATH.md, section 4)."""
    if a < 0 or b < 0:
        return ERR_NEG
    if c <= 0:
        return ERR_DIV
    q, r = divmod(a * b, c)
    v = q + (1 if ceil and r else 0)
    return ERR_OVF if v > N else dec(v)


def conv_oracle(k, a, s, x):
    """The six results for the view (k, A, S) and amount x, all ints in units."""
    if k < 0 or k > KMAX or a < 0 or s < 0:
        return [ERR_CAP] * 6
    p = 10**k
    amax = N // p
    if a + 1 > amax or s > p * (a + 1) - p:
        return [ERR_CAP] * 6
    m, n = a + 1, s + p
    room = amax - 1 - a
    to_shares = ERR_CAP if x > room else mul_div(x, n, m, False)
    to_assets = mul_div(x, m, n, False)
    mint = ERR_CAP if x > (room * n) // m else mul_div(x, m, n, True)
    withdraw = mul_div(x, n, m, True)
    return [to_shares, to_assets, to_shares, mint, withdraw, to_assets]


def conv_same(got, want):
    g = got.split("|")
    if len(g) != len(want):
        return False
    for x, y in zip(g, want):
        if y.startswith("cayvox.com/") or x.startswith("cayvox.com/"):
            if x != y:
                return False
        elif D(x) != D(y):
            return False
    return True


def conv_edge_vectors():
    out = []

    def add(label, k, a, s, x):
        if all(abs(v) <= N for v in (a, s, x)):
            out.append((label, k, a, s, x))

    from math import gcd
    for k in (0, 1, 5, 10):
        p = 10**k
        amax = N // p
        mid = min(123456789012345678, amax // 3)
        states = [
            ("empty", 0, 0), ("one unit, shares at the invariant", 1, p), ("one unit, no shares", 1, 0),
            ("largest A", amax - 1, 0), ("largest A and S", amax - 1, p * (amax - 1)),
            ("A one unit above its bound", amax, 0), ("S at the invariant", 5, 5 * p),
            ("S one unit above the invariant", 5, 5 * p + 1), ("negative A", -1, 0), ("negative S", 0, -1),
            ("small, price one", 2, 2 * p), ("rounding state", 2, min(10, 2 * p)),
            ("middle", mid, (p * mid) // 7),
        ]
        for sl, a, s in states:
            amounts = [("zero", 0), ("one unit", 1), ("minus one unit", -1), ("DMAX", N)]
            if a >= 0 and s >= 0 and a + 1 <= amax and s <= p * a:
                m, n = a + 1, s + p
                room = amax - 1 - a
                qmint = (room * n) // m
                amounts += [("deposit room", room), ("deposit room + u", room + 1),
                            ("mint room", qmint), ("mint room + u", qmint + 1)]
                x0 = m // gcd(n, m)  # x0 * n divisible by m
                x1 = n // gcd(n, m)  # x1 * m divisible by n
                amounts += [("exact to shares", x0), ("exact to shares - u", x0 - 1), ("exact to shares + u", x0 + 1),
                            ("exact to assets", x1), ("exact to assets - u", x1 - 1), ("exact to assets + u", x1 + 1),
                            ("half the room", room // 2)]
            for al, x in amounts:
                add(f"k={k} {sl}, {al}", k, a, s, x)
    for k in (-1, 11):
        for x in (0, 1):
            add(f"k={k} empty, amount {x}", k, 0, 0, x)
    return out


def conv_random_vectors(seed, count):
    rng = random.Random(seed)
    out = []
    for i in range(count):
        k = rng.randrange(0, KMAX + 1)
        p = 10**k
        amax = N // p
        a = rng.randrange(0, 10**rng.randrange(1, len(str(amax)) + 1)) % amax
        s = rng.randrange(0, p * a + 1)
        x = rng.randrange(0, 10**rng.randrange(1, 39))
        roll = rng.random()
        if roll < 0.01:
            s = min(N, p * a + 1 + rng.randrange(0, 10**rng.randrange(1, 20)))
        elif roll < 0.02:
            a = rng.randrange(amax, N + 1)
        elif roll < 0.03:
            x = -x - 1
        elif roll < 0.035:
            a = -rng.randrange(1, 10**10)
        out.append((f"random {i}", k, a, s, x))
    return out


def run_daml_conversion_once(dar, sdk, vectors):
    with tempfile.TemporaryDirectory() as work:
        inp = os.path.join(work, "in.json")
        outp = os.path.join(work, "out.json")
        with open(inp, "w") as f:
            json.dump([{"k": k, "a": dec(a), "s": dec(s), "x": dec(x)} for (_, k, a, s, x) in vectors], f)
        cmd = ["dpm", "script", "--dar", dar, "--script-name",
               "Cayvox.VaultV1Test.ConversionVectors:runConversionVectors",
               "--ide-ledger", "--static-time", "--input-file", inp, "--output-file", outp]
        r = subprocess.run(cmd, env=dict(os.environ, DPM_SDK_VERSION=sdk), capture_output=True, text=True)
        if r.returncode != 0:
            sys.stderr.write(r.stdout[-3000:] + r.stderr[-3000:])
            return None
        with open(outp) as f:
            return json.load(f)


def cmd_check_conversion(args):
    status = 0
    for name, vectors in [("edge", conv_edge_vectors()), ("random", conv_random_vectors(args.seed, args.random))]:
        chunks = [vectors[i:i + CONV_CHUNK] for i in range(0, len(vectors), CONV_CHUNK)]
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            parts = list(pool.map(lambda chunk: run_daml_conversion_once(args.dar, args.sdk, chunk), chunks))
        if any(part is None for part in parts):
            print(f"conversion oracle: SDK {args.sdk}: {name} run failed")
            return 2
        got = [r for part in parts for r in part]
        if len(got) != len(vectors):
            print(f"conversion oracle: SDK {args.sdk}: {name} run returned {len(got)} of {len(vectors)}")
            return 2
        bad = 0
        failures = 0
        for (label, k, a, s, x), g in zip(vectors, got):
            want = conv_oracle(k, a, s, x)
            failures += sum(1 for w in want if w.startswith("cayvox.com/"))
            if not conv_same(g, want):
                bad += 1
                if bad <= 10:
                    print(f"MISMATCH {label}: k={k} A={dec(a)} S={dec(s)} x={dec(x)} got {g} want {'|'.join(want)}")
        print(f"conversion oracle: SDK {args.sdk}: {name} vectors {len(vectors)} ({len(vectors) * 6} results), "
              f"failure results {failures}, mismatches {bad}"
              + (f" (seed {args.seed})" if name == "random" else ""))
        if bad:
            status = 1
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("--dar", required=True)
    c.add_argument("--sdk", required=True)
    c.add_argument("--seed", type=int, default=20260930)
    c.add_argument("--random", type=int, default=20000)
    cc = sub.add_parser("check-conversion")
    cc.add_argument("--dar", required=True)
    cc.add_argument("--sdk", required=True)
    cc.add_argument("--seed", type=int, default=20260930)
    cc.add_argument("--random", type=int, default=20000)
    cc.add_argument("--jobs", type=int, default=4)
    sub.add_parser("paths")
    e = sub.add_parser("emit-daml")
    e.add_argument("file")
    args = p.parse_args()
    return {"check": cmd_check, "check-conversion": cmd_check_conversion, "paths": cmd_paths,
            "emit-daml": cmd_emit}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
