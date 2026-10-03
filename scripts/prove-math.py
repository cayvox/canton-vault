#!/usr/bin/env python3
"""Z3 proofs for `cvx-vault-math-v1` (gate Q-09, docs/TESTING.md).

What this proves: the specification of docs/MATH.md, on an integer model with
Int sorts only (no Real). Operands are the exact integers int(x) = x / u, in
[0, N] with N = 10^38 - 1 = int(DMAX). The model of `mulDiv` is the one the
package implements: floor is the integer quotient of a * b by c; ceil adds
one when the remainder is non-zero; a result above N is a failure, so each
property is stated for results that do not fail.

What it does not prove: that the Daml code computes this model. The
differential suite (Q-06, scripts/math-oracle.py) ties the Daml code to it.

Obligations:
  M-01 to M-07   docs/MATH.md, section 5.
  K-01 to K-07   the bounds and KMAX, packages/utils/vault-math-v1/ARCHITECTURE.md,
                 section 6, with P = 10^k the virtual shares in units of u.
  K-08           the asset-bound check of previewMint, docs/MATH.md section 7.
  V-01 to V-04   the vault-level properties of docs/MATH.md section 8, on the
                 conversion functions of section 7, over states that pass
                 their view checks (A + 1 <= AMAX, S <= P * A).
  T-01           without donations, the price never exceeds one unit of
                 asset per unit of share, so a deposit of at least u mints
                 at least u (docs/SECURITY.md, T-01).

Each obligation is proved when Z3 reports its negation unsatisfiable, and
K-04 (a counterexample under the previous bound) when Z3 reports it
satisfiable. Every hypothesis set is first checked to be satisfiable, so
that no proof is vacuous, and a control property that is false must yield a
counterexample.
Exit status 0 when every obligation has the expected result.
"""

import sys

import z3

N = 10**38 - 1
TIMEOUT_MS = 120000


def in_range(*xs):
    return z3.And([z3.And(x >= 0, x <= N) for x in xs])


def floor_spec(q, p, c):
    """q = floor(p / c), for c > 0, by its defining inequalities."""
    return z3.And(q >= 0, q * c <= p, p < (q + 1) * c)


def ceil_of(q, p, c):
    """ceil from floor q, as the package computes it: q + 1 when c does not divide p."""
    return z3.If(p - q * c == 0, q, q + 1)


results = []


def check(name, statement, hypotheses, expect="proved"):
    # Vacuity: the hypotheses alone must be satisfiable, or "proved" means
    # nothing. A separate solver keeps the proof below non-incremental.
    v = z3.Solver()
    v.set("timeout", TIMEOUT_MS)
    v.add(hypotheses)
    if v.check() != z3.sat:
        results.append(False)
        print(f"{name}: VACUOUS (hypotheses not satisfiable: {v.check()})")
        return
    s = z3.Solver()
    s.set("timeout", TIMEOUT_MS)
    s.add(hypotheses)
    if expect == "proved":
        s.add(z3.Not(statement))
        r = s.check()
        ok = r == z3.unsat
        outcome = "proved" if ok else f"NOT PROVED ({r})"
        if r == z3.sat:
            outcome += f": counterexample {s.model()}"
    else:
        s.add(statement)
        r = s.check()
        ok = r == z3.sat
        outcome = f"counterexample found: {s.model()}" if ok else f"NO COUNTEREXAMPLE ({r})"
    results.append(ok)
    print(f"{name}: {outcome}")


a, b, c, a1, a2, b1, b2, c1, c2 = z3.Ints("a b c a1 a2 b1 b2 c1 c2")
p, p1, p2, q, q1, q2 = z3.Ints("p p1 p2 q q1 q2")

base = [in_range(a, b, c), c > 0, p == a * b]

# M-01: int(mulDiv Floor a b c) * int(c) <= int(a) * int(b) < (int(mulDiv Floor a b c) + 1) * int(c).
check("M-01 floor bounds the exact quotient",
      z3.And(q * c <= a * b, a * b < (q + 1) * c),
      base + [floor_spec(q, p, c), q <= N])

# M-02: (int(mulDiv Ceil a b c) - 1) * int(c) < int(a) * int(b) <= int(mulDiv Ceil a b c) * int(c).
qc = ceil_of(q, p, c)
check("M-02 ceil bounds the exact quotient",
      z3.And((qc - 1) * c < a * b, a * b <= qc * c),
      base + [floor_spec(q, p, c), qc <= N])

# M-03: mulDiv Floor <= mulDiv Ceil <= mulDiv Floor + u.
check("M-03 floor <= ceil <= floor + u",
      z3.And(q <= qc, qc <= q + 1),
      base + [floor_spec(q, p, c), qc <= N])

# M-04: ceil == floor exactly when int(c) divides int(a) * int(b).
k = z3.Int("k")
check("M-04 ceil == floor iff c divides a * b (only if)",
      z3.Exists([k], z3.And(k >= 0, k * c == p)),
      base + [floor_spec(q, p, c), qc == q])
check("M-04 ceil == floor iff c divides a * b (if)",
      qc == q,
      base + [floor_spec(q, p, c), k >= 0, k * c == p])

# M-05: non-decreasing in a and in b, non-increasing in c; for floor and ceil.
qc1, qc2 = ceil_of(q1, p1, c), ceil_of(q2, p2, c)
check("M-05 monotonic in a (floor)", q1 <= q2,
      [in_range(a1, a2, b, c), c > 0, a1 <= a2, p1 == a1 * b, p2 == a2 * b,
       floor_spec(q1, p1, c), floor_spec(q2, p2, c)])
check("M-05 monotonic in a (ceil)", qc1 <= qc2,
      [in_range(a1, a2, b, c), c > 0, a1 <= a2, p1 == a1 * b, p2 == a2 * b,
       floor_spec(q1, p1, c), floor_spec(q2, p2, c)])
check("M-05 monotonic in b (floor)", q1 <= q2,
      [in_range(a, b1, b2, c), c > 0, b1 <= b2, p1 == a * b1, p2 == a * b2,
       floor_spec(q1, p1, c), floor_spec(q2, p2, c)])
check("M-05 monotonic in b (ceil)", qc1 <= qc2,
      [in_range(a, b1, b2, c), c > 0, b1 <= b2, p1 == a * b1, p2 == a * b2,
       floor_spec(q1, p1, c), floor_spec(q2, p2, c)])
qd1, qd2 = ceil_of(q1, p, c1), ceil_of(q2, p, c2)
check("M-05 non-increasing in c (floor)", q1 >= q2,
      [in_range(a, b, c1, c2), c1 > 0, c1 <= c2, p == a * b,
       floor_spec(q1, p, c1), floor_spec(q2, p, c2)])
check("M-05 non-increasing in c (ceil)", qd1 >= qd2,
      [in_range(a, b, c1, c2), c1 > 0, c1 <= c2, p == a * b,
       floor_spec(q1, p, c1), floor_spec(q2, p, c2)])

# M-06: mulDiv r a b c == mulDiv r b a c.
check("M-06 symmetric in a and b (floor and ceil)",
      z3.And(q1 == q2, ceil_of(q1, p1, c) == ceil_of(q2, p2, c)),
      [in_range(a, b, c), c > 0, p1 == a * b, p2 == b * a,
       floor_spec(q1, p1, c), floor_spec(q2, p2, c)])

# M-07: mulDiv r a c c == a for c > 0.
check("M-07 a * c / c == a (floor and ceil)",
      z3.And(q == a, ceil_of(q, p, c) == a),
      [in_range(a, c), c > 0, p == a * c, floor_spec(q, p, c)])

# KMAX. Units of u: A, S the totals; VA = 1, VS = P = 10^k; operations of
# docs/SPEC.md, section 5, with previewDeposit and previewRedeem of
# docs/MATH.md, section 7.
A, S, P, dep, m, s_, x = z3.Ints("A S P dep m s x")
state = [A >= 0, S >= 0, P >= 1, dep >= 0, s_ >= 0]

# K-01: a deposit keeps S <= P * A; the shares minted are at most dep * P.
check("K-01 a deposit keeps S <= P * A and mints at most dep * P",
      z3.And(S + m <= P * (A + dep), m <= dep * P),
      state + [S <= P * A, floor_spec(m, dep * (S + P), A + 1)])

# K-02: a redemption of s <= S keeps S <= P * A and pays at most A.
check("K-02 a redemption keeps S <= P * A and pays at most A",
      z3.And(S - s_ <= P * (A - x), x <= A),
      state + [S <= P * A, s_ <= S, floor_spec(x, s_ * (A + 1), S + P)])

# An earlier, weaker bound, A <= N - 1 for every k, for the record:
# K-03: at k = 0 every deposit it allows mints at most N, and the new state
# keeps S + VS <= N and A + VA <= N.
check("K-03 previous bound: at k = 0 every allowed deposit fits",
      z3.And(m <= N, S + m + 1 <= N, A + dep + 1 <= N),
      state + [P == 1, S <= P * A, A + dep <= N - 1, floor_spec(m, dep * (S + P), A + 1)])

# K-04: at k = 1 the first deposit of the largest amount it allows overflows.
check("K-04 previous bound: at k = 1 the first deposit of N - 1 overflows",
      m > N,
      state + [P == 10, A == 0, S == 0, dep == N - 1, floor_spec(m, dep * (S + P), A + 1)],
      expect="counterexample")

# The bounds of docs/MATH.md, section 7: AMAX = floor(N / P), the asset bound
# A + VA <= AMAX, and the share bound S + VS <= P * AMAX.
Amax = z3.Int("Amax")
amax_def = [Amax >= 0, Amax * P <= N, N < (Amax + 1) * P]

# K-05: a deposit whose new A satisfies the asset bound mints at most N and
# keeps the share bound.
check("K-05 a deposit within the asset bound mints at most N and keeps the share bound",
      z3.And(m <= N, S + m + P <= P * Amax),
      state + amax_def + [P <= N, S <= P * A, A + dep + 1 <= Amax, floor_spec(m, dep * (S + P), A + 1)])

# K-06: in every reachable state (S <= P * A, K-01 and K-02), the asset bound
# implies the share bound, and the share bound never exceeds N.
check("K-06 the asset bound implies the share bound, which is at most N",
      z3.And(S + P <= P * Amax, P * Amax <= N),
      state + amax_def + [P <= N, S <= P * A, A + 1 <= Amax])

# K-07: at k = 0, KMAX = 10 and 11, the first deposit of the largest amount
# the asset bound allows mints exactly dep * 10^k and fits both bounds.
for k in (0, 10, 11):
    pk = 10**k
    amax = N // pk
    check(f"K-07 at k = {k} the largest first deposit, {amax - 1} units, fits both bounds",
          z3.And(m == dep * P, S + m + P <= P * Amax, P * Amax <= N),
          state + amax_def + [P == pk, A == 0, S == 0, Amax == amax, dep == amax - 1,
                              floor_spec(m, dep * (S + P), A + 1)])

# The conversion functions of docs/MATH.md, section 7, in units of u: with
# M = A + VA = A + 1 and Nn = S + VS = S + P, a view passes step 1 when
# A + 1 <= Amax and S <= P * A (S + P <= P * M).
M, Nn, R, x_, y, c_, bb, sp, Dv = z3.Ints("M Nn R x y c b sp D")
view = amax_def + [A >= 0, S >= 0, P >= 1, P <= N, A + 1 <= Amax, S <= P * A, M == A + 1, Nn == S + P]

# K-08: previewMint checks x <= floor(R * Nn / M) with R = Amax - 1 - A, the
# room of the asset bound. That quotient is at most N, so the check cannot
# overflow; it holds exactly when the assets charged, ceil(x * M / Nn), fit
# the room; and the mint then keeps both bounds.
q_room = z3.Int("q_room")
mint_hyp = view + [x_ >= 0, R == Amax - 1 - A, floor_spec(q_room, R * Nn, M)]
check("K-08 the previewMint check cannot overflow",
      q_room <= N, mint_hyp)
cm = z3.Int("cm")
check("K-08 the previewMint check holds exactly when the assets charged fit the room",
      (x_ <= q_room) == (cm <= R),
      mint_hyp + [cm == ceil_of(z3.Int("cq"), x_ * M, Nn), floor_spec(z3.Int("cq"), x_ * M, Nn)])
check("K-08 a mint that passes the check keeps both bounds",
      z3.And(A + cm + 1 <= Amax, S + x_ <= P * (A + cm)),
      mint_hyp + [x_ <= q_room, cm == ceil_of(z3.Int("cq"), x_ * M, Nn), floor_spec(z3.Int("cq"), x_ * M, Nn)])

# V-01: previewRedeem (previewDeposit a) <= a, in the same state and in the
# state after the deposit; the deposit is within the asset bound.
dep_hyp = view + [dep >= 0, A + dep + 1 <= Amax, floor_spec(m, dep * Nn, M)]
check("V-01 previewRedeem (previewDeposit a) <= a in the same state",
      y <= dep, dep_hyp + [floor_spec(y, m * M, Nn)])
check("V-01 previewRedeem (previewDeposit a) <= a after the deposit",
      y <= dep, dep_hyp + [floor_spec(y, m * (M + dep), Nn + m)])

# V-02: previewMint s >= convertToAssets s and previewWithdraw a >= convertToShares a.
qf = z3.Int("qf")
check("V-02 previewMint s >= convertToAssets s",
      ceil_of(qf, x_ * M, Nn) >= qf, view + [x_ >= 0, floor_spec(qf, x_ * M, Nn)])
check("V-02 previewWithdraw a >= convertToShares a",
      ceil_of(qf, x_ * Nn, M) >= qf, view + [x_ >= 0, floor_spec(qf, x_ * Nn, M)])

# V-03: one party's deposits and redemptions, with no yield. With D the
# party's assets in minus out and sp its shares, D * Nn >= sp * M holds
# initially (D = 0, sp = 0) and after every step, so a party that ends with
# no shares has D >= 0: it never takes out more than it put in.
party = [sp >= 0, sp <= S, Dv * Nn >= sp * M]
check("V-03 a deposit keeps D * (S + VS) >= shares * (A + VA)",
      (Dv + dep) * (Nn + m) >= (sp + m) * (M + dep),
      view + party + [dep >= 0, A + dep + 1 <= Amax, floor_spec(m, dep * Nn, M)])
check("V-03 a redemption keeps D * (S + VS) >= shares * (A + VA)",
      (Dv - y) * (Nn - x_) >= (sp - x_) * (M - y),
      view + party + [x_ >= 0, x_ <= sp, floor_spec(y, x_ * M, Nn)])
check("V-03 with no shares left the party took out at most what it put in",
      Dv >= 0, view + [sp == 0, Dv * Nn >= sp * M])

# V-04: with A = 0 and S = 0 the first deposit of a mints a * 10^k.
check("V-04 the first deposit mints a * 10^k",
      m == dep * P, view + [A == 0, S == 0, dep >= 0, dep + 1 <= Amax, floor_spec(m, dep * Nn, M)])

# T-01: without donations the price stays at most one: A + VA <= S + VS is
# kept by deposits, redemptions (x <= S), mints and withdrawals (a <= A),
# and under it a deposit of a >= 1 mints at least a.
price = [M <= Nn]
check("T-01 a deposit keeps A + VA <= S + VS",
      M + dep <= Nn + m, view + price + [dep >= 0, floor_spec(m, dep * Nn, M)])
check("T-01 a redemption keeps A + VA <= S + VS",
      M - y <= Nn - x_, view + price + [x_ >= 0, x_ <= S, floor_spec(y, x_ * M, Nn)])
check("T-01 a mint keeps A + VA <= S + VS",
      M + ceil_of(qf, x_ * M, Nn) <= Nn + x_, view + price + [x_ >= 0, floor_spec(qf, x_ * M, Nn)])
check("T-01 a withdrawal keeps A + VA <= S + VS",
      M - dep <= Nn - ceil_of(qf, dep * Nn, M), view + price + [dep >= 0, dep <= A, floor_spec(qf, dep * Nn, M)])
check("T-01 under it a deposit of a >= u mints at least a",
      m >= dep, view + price + [dep >= 1, floor_spec(m, dep * Nn, M)])

# Controls for V-01 and T-01: with the deposit rounded up, the round trip
# can return more than the deposit; a donation (assets without shares) can
# raise the price above one.
mc = z3.Int("mc")
check("control: V-01 with the deposit rounded up can gain (false)",
      y > dep, view + [dep >= 0, A + dep + 1 <= Amax, floor_spec(m, dep * Nn, M), mc == ceil_of(m, dep * Nn, M),
                       floor_spec(y, mc * M, Nn)], expect="counterexample")
check("control: T-01 a donation can raise the price above one (false)",
      M + dep > Nn, view + price + [dep >= 1], expect="counterexample")

# Control: a false property must yield a counterexample, so that "proved"
# above is not an artefact of the model.
check("control: floor == ceil for every operand (false)",
      qc != q,
      base + [floor_spec(q, p, c)],
      expect="counterexample")

print(f"z3 {z3.get_version_string()}: {sum(results)} of {len(results)} obligations as expected")
sys.exit(0 if all(results) else 1)
