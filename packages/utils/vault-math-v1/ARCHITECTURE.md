# Vault Math V1: architecture

This file records how `cvx-vault-math-v1` implements `docs/MATH.md`, why, and what must hold for it to be correct. Paths into the Daml SDK are at SDK 3.4.11, digital-asset/daml commit `de513339189206e5bcae77b2cfc68afda9b05ef5`. The Daml-LF specification, [`sdk/daml-lf/spec/daml-lf-2.rst`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst), is cited below as `[LF]` with its line numbers.

## 1. Modules

| Module | Contents |
|---|---|
| `Cayvox.VaultMathV1` | The public API: `Rounding` and `mulDiv`, with an explicit export list (`docs/CONVENTIONS.md`, section 5) |
| `Cayvox.VaultMathV1.Internal` | Everything else: the failure constructor and the three failures (D-13), the checked computation `mulDivChecked`, and the limb arithmetic. Not public API (`docs/CONVENTIONS.md`, section 5) |

`Rounding` is defined in the public module, so the type's identity never depends on an internal module. `mulDiv` is a one-line wrapper that raises the `Left` of `mulDivChecked` with `failWithStatusPure`, which the standard library defines as "Fail with a failure status in a pure context" (daml-stdlib [`DA/Internal/Fail.daml:20-22`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-stdlib-src/DA/Internal/Fail.daml#L20-L22)).

## 2. Representation

`int(x) = x / u` is an integer of up to 38 digits, and `int(a) * int(b)` has up to 76. Daml `Int` is 64-bit: "a standard signed 64-bit integer (integer between −2⁶³ to 2⁶³−1)" (`[LF]:543-544`). `ADD_INT64`, `SUB_INT64` and `MUL_INT64` throw `ArithmeticError` on overflow (`[LF]:3948-3962`). `DIV_INT64` "rounds toward 0" and `MOD_INT64` returns the remainder (`[LF]:3963-3974`).

A non-negative integer is a list of limbs in base `B = 10^9`, least significant first, with no zero limb at the top; zero is the empty list. `int(DMAX) = 10^38 - 1` is five limbs, the top one `99`.

Every intermediate value stays below `2^63 - 1`, about `9.22 * 10^18`:

| Operation | Largest value |
|---|---|
| Addition with carry (`addCarry`, `addBack`) | `(B - 1) + (B - 1) + 1 < 2B` |
| Limb times limb plus carry (`mulCarry`, `mulSub`) | `(B + 1)(B - 1) + B < B^2 + B` |
| Short division step (`divStep`) | `(v - 1)B + (B - 1) < B^2`, since `v < B` |
| Algorithm D, D3 numerator | `u[j+n] B + u[j+n-1] < B^2` |
| Algorithm D, D3 test | `qhat * v[n-2] < (B + 2)B` and `rhat * B + u[j+n-2] < B^2`, since the test runs only while `rhat < B` |

`B^2 + B` and `(B + 2)B` are about `10^18`, under the `Int` bound by a factor of nine. The `qhat <= B + 1` used in the table holds because the running remainder is below the divisor, so `u[j+n] <= v[n-1]`, and `v[n-1] >= B/2` after normalization: `qhat <= (v[n-1] B + B - 1) / v[n-1] < B + 2`. Every division and remainder has a non-negative dividend and a positive divisor, where rounding toward 0 is floor. Were a bound wrong, `MUL_INT64` or `ADD_INT64` would throw rather than wrap, so the failure mode is a failed transaction, never a wrong result.

## 3. Algorithm

1. **Checks**, in the order of `docs/MATH.md`, section 4: a negative operand, then a non-positive divisor.
2. **Exact conversion in** (`toLimbs`), by arithmetic whose semantics the specification states. `SHIFT_NUMERIC` "converts a decimal of scale `α₁` to a decimal scale `α₂` ... by shifting the decimal point. Thus the output will be equal to the input multiplied by `1E(α₁-α₂)`" (`[LF]:4061-4065`), and `NUMERIC_TO_INT64` "returns the integral part of the given numeric -- in other words, rounds towards 0" (`[LF]:4647-4651`). So `truncate (shift @36 x)` is the top limb `floor(int(x) / B^4)`, below 100. `limbValue 4` rebuilds that limb's value exactly, and `SUB_NUMERIC`, which is exact and throws only on overflow (`[LF]:4028-4032`), removes it. `shift @27`, `@18`, `@9` and `@0` then expose limbs 3 to 0 in turn. `limbValue i l` builds `l` as a `Numeric 0` with `natToNumeric0`: binary Horner steps from the literal `1.0` with `ADD_NUMERIC` only (literals: `[LF]:511`, `:553-555`; `ADD_NUMERIC`: `:4022-4026`). It then casts `l` to scale `9 i`, which `CAST_NUMERIC` does "while keeping the value the same" or throws (`[LF]:4055-4059`), and shifts it to scale 10, multiplying by `10^(9 i - 10)`. Every intermediate is a valid `Numeric`: `shift @s` keeps the unscaled integer of at most 38 digits, and a limb below `10^9` cast to scale `9 i <= 36` has at most `9 + 36` digits, or `2 + 36` for limb 4, which is below 100. The conversion reads no text and uses no `INT64_TO_NUMERIC`, which the specification does not describe. A conversion through text would depend on the output format of `NUMERIC_TO_TEXT`, which the specification defines only as "the numeric string representation of the numeric" (`[LF]:4067-4070`).
3. **Product** (`mulLimbs`): schoolbook multiplication, row by row with `mulSmall` and `addLimbs`.
4. **Quotient and remainder** (`divModLimbs`): a single-limb divisor uses short division; a dividend below the divisor gives `(0, dividend)`; otherwise Knuth's Algorithm D (TAOCP vol. 2, section 4.3.1). D1 multiplies both operands by `d = B / (v[n-1] + 1)` so that the top divisor limb is at least `B/2`. D3 estimates each quotient limb from the top two limbs and corrects it at most twice with the next divisor limb. D4 multiplies and subtracts. D6 adds the divisor back once when the estimate was still one too large. D8 divides the remainder by `d`. Knuth's Theorem B bounds the estimate after normalization by `q <= qhat <= q + 2`. The D3 test removes every case of `q + 2` (TAOCP vol. 2, section 4.3.1, the discussion of step D3), so one add-back suffices.
5. **Rounding.** `Floor` is the quotient. `Ceil` adds one unit when the remainder is non-zero (`docs/MATH.md`, section 6, item 3).
6. **Overflow check** against the limbs of `int(DMAX)`, then **exact conversion out** (`fromLimbs`): the sum of `limbValue i l_i` over the five limb positions, with `ADD_NUMERIC`. The overflow check comes first, so the sum is at most `DMAX` and no addition overflows; `fromLimbs` also returns `None` above `DMAX`.

No `Numeric` arithmetic occurs inside the algorithm except the exact conversions of steps 2 and 6 (`docs/MATH.md`, section 6, item 4).

**Why this algorithm.** `docs/MATH.md`, section 1, rules out every single builtin at LF 2.1. Limbs of `10^9` are the largest power of ten whose products and carries fit `Int` with margin (section 2). A power of ten also makes both conversions digit regrouping, with no multi-limb base conversion. Algorithm D is the standard exact long division with remainder; the remainder is what `Ceil` needs. A bounded domain (for example, operands limited so that `a * b` fits 38 digits) would avoid multi-limb division, but it fails the requirement that the product never fails on its own (`docs/MATH.md`, section 4).

## 4. Cost

One call converts both operands to limbs, multiplies them (at most five limbs each, ten in the product), divides with Algorithm D and converts the result back, all in `Int` arithmetic. A call therefore costs many times a single `Decimal` division, and the cost grows with the number of limbs of the operands.

The vault calls `mulDiv` once per request in an execution (`docs/MATH.md`, section 7; `docs/SPEC.md`, section 5.3, step 9), so a batch of 25 requests adds 25 calls to the transaction.

## 5. Proof obligations and evidence

| Obligation | Evidence |
|---|---|
| M-01 to M-07 hold for the specification | `scripts/prove-math.py` (Q-09), Z3 on an integer model with no `Real` |
| The Daml code computes the specification | `scripts/math-oracle.py` (Q-06): the edge vectors and at least 20,000 seeded random vectors against Python `decimal` at 200 digits, on SDK 3.4.11, 3.5.8 and 3.5.10. The edge vectors drive every path of Algorithm D, which the oracle's instrumented mirror of the algorithm confirms (`scripts/math-oracle.py paths`) |
| M-08: each failure exactly when its condition holds, in order | The unit tests at each boundary, through a choice and the failure helper (Q-04); the oracle's failure vectors |
| M-09: identical on every SDK | Q-06 and the unit tests run on every SDK of the matrix |
| Every guard and rounding decision is observed | `scripts/mutate-math.py` (Q-07): zero surviving mutants |
| Intermediate values fit `Int` | Section 2; an overflow throws (`[LF]:3948-3962`), so the failure mode is a failed transaction |
| Bounds and KMAX | Section 6 |

## 6. Bounds and KMAX

`docs/MATH.md`, section 7, sets `VA = u`, `VS = 10^k * u`, `0 <= k <= KMAX = 10`, and the bounds

- asset bound: `A + VA <= AMAX(k)`, with `AMAX(k) = floor(DMAX / 10^k)`;
- share bound: `S + VS <= 10^k * AMAX(k)`.

The derivation works in units of `u`: `A`, `S`, `a` and `s` below are `int` of the values, `N = 10^38 - 1`, `P = 10^k`, and `AMAX = floor(N / P)`. The operations are those of `docs/SPEC.md`, section 5: create with `A = S = 0`; deposit `a`, which mints `m = floor(a (S + P) / (A + 1))`; redeem `s <= S`, which pays `x = floor(s (A + 1) / (S + P))`; add assets `a` with no shares minted.

**K-01, K-02 (invariant).** Every reachable state has `S <= P * A`, equivalently `S + VS <= 10^k (A + VA)`.
- Create: `0 <= 0`.
- Deposit: `m <= a (S + P) / (A + 1) <= a P (A + 1) / (A + 1) = a P`, using `S + P <= P (A + 1)`. So `S + m <= P A + P a`.
- Redemption: `x (S + P) <= s (A + 1)`. So `P x <= s P (A + 1) / (S + P)`, and `S - s <= P (A - x)` reduces to `s (P A - S) / (S + P) <= P A - S`, which holds because `0 <= s < S + P` and `P A - S >= 0`. Also `x <= s (A + 1) / (S + P) < A + 1`, so a redemption pays at most `A`.
- Adding assets raises `A` only.

**K-06 (the share bound follows).** With the invariant and the asset bound, `S + P <= P (A + 1) <= P * AMAX <= N`. The share bound therefore holds in every state that satisfies the asset bound, and it never exceeds `DMAX`.

**K-05 (no conversion overflows).** A deposit whose new total satisfies the asset bound, `A + a + 1 <= AMAX`, mints `m <= a P <= P * AMAX - P - S`, so `m <= N` and the new state keeps the share bound. `docs/SPEC.md`, section 5.3, checks the asset bound (step 8) before it converts (step 9), so a deposit beyond the vault's capacity fails with `vault-capacity-exceeded` and never with `math-overflow`.

**K-07 (the capacity is reachable).** At `k = 0`, `10` and `11`, the first deposit of `AMAX - 1` units (the largest the asset bound allows) mints exactly `(AMAX - 1) P` and fits both bounds.

**Why `KMAX = 10`.** K-05 and K-06 hold for every `k` up to 37. `KMAX = 10` is set by D-10, the same bound that the OpenZeppelin Stellar vault suggests as the upper bound of its decimals offset ([`packages/tokens/src/vault/mod.rs:415-416`](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/mod.rs#L415-L416)); at `k = 10` the asset capacity is still about `10^18` whole units. At `k = 11` the arithmetic still fits (`test_bounds_offsetKmaxPlusOne`); the vault rejects that offset in its `ensure`.

**A bound that does not depend on `k` (K-03, K-04).** With the asset bound `A <= N - 1` for every `k`, the first deposit of `N - 1` mints `(N - 1) P`, above `N` for every `P >= 10`: that bound allows only `k = 0`, which is why the asset bound depends on the offset.

**Checking the bounds in `Decimal` without overflow.** At `k = 0`, `A + amount + VA` can exceed `DMAX`, and `ADD_NUMERIC` then throws `ArithmeticError` (`[LF]:4022-4026`). Each check is evaluated in a form whose every term is non-negative and at most `DMAX`:

| Check | Form |
|---|---|
| Asset bound for a deposit or an asset addition of `amount` | `amount <= AMAX(k) - VA - A` |
| Share bound for `shares` minted | `shares <= 10^k * AMAX(k) - VS - S` |

The right sides are non-negative whenever the current state satisfies its bounds. `AMAX(k)` is `mulDiv Floor DMAX u (10^k * u)`, and `10^k * AMAX(k)` is `mulDiv Floor AMAX(k) (10^k * u) u`.

**Capacity per offset** (`AMAX(k)`, the largest `A` and the largest `S` the bounds allow):

| `k` | `AMAX(k)` | Largest `A` | Largest `S` | Integer digits of `AMAX(k)` |
|---|---|---|---|---|
| 0 (default) | `9999999999999999999999999999.9999999999` | `9999999999999999999999999999.9999999998` | `9999999999999999999999999999.9999999998` | 28 |
| 1 | `999999999999999999999999999.9999999999` | `999999999999999999999999999.9999999998` | `9999999999999999999999999999.9999999980` | 27 |
| 2 | `99999999999999999999999999.9999999999` | `99999999999999999999999999.9999999998` | `9999999999999999999999999999.9999999800` | 26 |
| 3 | `9999999999999999999999999.9999999999` | `9999999999999999999999999.9999999998` | `9999999999999999999999999999.9999998000` | 25 |
| 4 | `999999999999999999999999.9999999999` | `999999999999999999999999.9999999998` | `9999999999999999999999999999.9999980000` | 24 |
| 5 | `99999999999999999999999.9999999999` | `99999999999999999999999.9999999998` | `9999999999999999999999999999.9999800000` | 23 |
| 6 | `9999999999999999999999.9999999999` | `9999999999999999999999.9999999998` | `9999999999999999999999999999.9998000000` | 22 |
| 7 | `999999999999999999999.9999999999` | `999999999999999999999.9999999998` | `9999999999999999999999999999.9980000000` | 21 |
| 8 | `99999999999999999999.9999999999` | `99999999999999999999.9999999998` | `9999999999999999999999999999.9800000000` | 20 |
| 9 | `9999999999999999999.9999999999` | `9999999999999999999.9999999998` | `9999999999999999999999999999.8000000000` | 19 |
| 10 (KMAX) | `999999999999999999.9999999999` | `999999999999999999.9999999998` | `9999999999999999999999999998.0000000000` | 18 |
| 11 (KMAX + 1, rejected by the vault) | `99999999999999999.9999999999` | `99999999999999999.9999999998` | `9999999999999999999999999980.0000000000` | 17 |

Evidence: `scripts/prove-math.py` proves K-01, K-02, K-03, K-05, K-06 and K-07 and finds the K-04 counterexample. `test/vault-math-v1-test` tests the first deposit at the capacity, and each bound one unit below, at, and one unit above, at `k = 0`, `k = 10` and `k = 11` (`test_bounds_offsetZero`, `test_bounds_offsetKmax`, `test_bounds_offsetKmaxPlusOne`), and V-04 for `k` from 0 to 10.
