# Math

This document specifies `cvx-vault-math-v1` and the share conversion formulas of the vault. It states what must hold. The algorithm and its proof obligations are recorded in `packages/utils/vault-math-v1/ARCHITECTURE.md`.

## 1. Why a dedicated math package

The Daml-LF facts below are from the Daml-LF 2 specification of daml SDK 3.4.11 (`sdk/daml-lf/spec/daml-lf-2.rst` at commit `de51333918`).

- Daml `Numeric` multiply and divide round half-even ("banker's rounding convention", [`daml-lf-2.rst` L4034-L4053](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4034-L4053)). No `Numeric` builtin takes a rounding direction ([L4022-L4070](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4022-L4070)).
- A `Numeric` has a precision of at most 38 digits at every scale ([L553-L555](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L553-L555)), and `MUL_NUMERIC` throws an `ArithmeticError` on overflow ([L4034-L4042](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4034-L4042)). For operands with up to 28 integer digits, `a * b` has up to 56 integer digits, so it overflows before any division happens.
- Composing operations rounds at each `MUL_NUMERIC` and `DIV_NUMERIC` step, so the result is not the exact quotient rounded once in a chosen direction.
- `roundNumeric` with Floor or Ceiling rounds a value that is already a `Numeric` ([`DA/Numeric.daml` L216-L222](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-stdlib-src/DA/Numeric.daml#L216-L222)), so it cannot round the exact quotient.
- BigNumeric computes the exact result, but every BigNumeric builtin is marked "Available in version ≥ 2.dev" (for example [`daml-lf-2.rst` L4098-L4103](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4098-L4103); [`LanguageVersion.scala` L103](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/language/src/main/scala/com/digitalasset/daml/lf/language/LanguageVersion.scala#L103), while the stable versions are 2.1 to 2.2, [L171](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/language/src/main/scala/com/digitalasset/daml/lf/language/LanguageVersion.scala#L171)).

No single builtin at LF 2.1 therefore computes `floor(a*b/c)` or `ceil(a*b/c)` exactly over the vault's domain. The package supplies it. It is the Daml counterpart of `Math.mulDiv` with `Rounding` in OpenZeppelin Contracts ([`Math.sol` L199-L206](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/utils/math/Math.sol#L199-L206), [L279-L284](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/utils/math/Math.sol#L279-L284)).

## 2. Notation

- `u` is one unit in the last place of `Decimal`: `0.0000000001` (`Decimal` is `Numeric 10`, [`GHC/Types.daml` L201](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-prim-src/GHC/Types.daml#L201)).
- `DMAX` is the largest `Decimal`: 28 integer digits and 10 fractional digits, all nines.
- For a `Decimal` value `x`, `int(x) = x / u` is the exact integer it represents.
- `floor` and `ceil` are the mathematical functions on exact rationals.

## 3. Public API

The public module exports exactly the following. Everything else lives in an `.Internal` module, the convention canton-contracts follows ([`ARCHITECTURE.md` L119-L121](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L119-L121)). The API is final.

| Name | Type | Meaning |
|---|---|---|
| `Rounding` | `data Rounding = Floor \| Ceil` | Direction of rounding for non-negative results |
| `mulDiv` | `Rounding -> Decimal -> Decimal -> Decimal -> Decimal` | `mulDiv r a b c` is `floor` or `ceil` of the exact `a * b / c`, as a `Decimal` |

**Why only two directions.** The domain is non-negative (§4), where truncation equals `Floor` and rounding away from zero equals `Ceil`. The Solidity enum has four members because it also serves signed callers. Two members keep the frozen surface minimal.

## 4. Domain and failures

| Condition | Result |
|---|---|
| `a >= 0`, `b >= 0`, `c > 0`, and the exact result rounded in direction `r` is at most `DMAX` | The exact rounded result |
| `a < 0` or `b < 0` | Failure `math-negative-operand` |
| `c <= 0` | Failure `math-non-positive-divisor` |
| The rounded result exceeds `DMAX` | Failure `math-overflow` |

- The intermediate product never causes a failure by itself. Only the final result is checked against `DMAX`.
- Identifiers and category follow D-13: `cayvox.com/math-negative-operand`, `cayvox.com/math-non-positive-divisor` and `cayvox.com/math-overflow`, each with category `InvalidGivenCurrentSystemStateOther` and empty `meta`, built by one constructor in the `.Internal` module.
- **How the pure function fails.** `mulDiv` raises its failure with `failWithStatusPure : FailureStatus -> a`, which the standard library defines as "Fail with a failure status in a pure context" over the `EFailWithStatus` primitive, and exports through `DA.Fail` (daml SDK 3.4.11 [`DA/Internal/Fail.daml` L20-L22](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-stdlib-src/DA/Internal/Fail.daml#L20-L22); [`DA/Fail.daml` L5](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-stdlib-src/DA/Fail.daml#L5)). Called in a choice, it fails the transaction with the exact `errorId`, category, message and `meta`: the tests in `test/vault-math-v1-test/daml/Cayvox/VaultMathV1Test.daml` call `mulDiv` inside the choice of the `MathHarness` fixture and match each failure with the failure helper (`test_mulDiv_failsWhenFirstOperandNegative`, `test_mulDiv_failsWhenDivisorNotPositive`, `test_mulDiv_failsWhenResultExceedsDmax`), in memory on every SDK of the matrix and on both sandboxes (Q-05).
- **Evaluation is strict.** A call is evaluated where it is bound: a failing `mulDiv` bound by `let` and never used still fails (`test_mulDiv_unusedFailingCallStillFails`). A caller that must not fail checks the conditions of this section before the call. In Daml Script, a test catches the failure of a pure call with `tryFailureStatus`, as that test does.

## 5. Correctness properties

Each property is tested by the differential suite (Q-06) and, where marked, proved on an integer model with Z3 (Q-09). Z3 proves the specification; the differential suite ties the Daml code to it.

| ID | Property | Z3 |
|---|---|---|
| M-01 | `int(mulDiv Floor a b c) * int(c) <= int(a) * int(b) < (int(mulDiv Floor a b c) + 1) * int(c)` | yes |
| M-02 | `(int(mulDiv Ceil a b c) - 1) * int(c) < int(a) * int(b) <= int(mulDiv Ceil a b c) * int(c)` | yes |
| M-03 | `mulDiv Floor <= mulDiv Ceil <= mulDiv Floor + u` | yes |
| M-04 | `mulDiv Ceil a b c == mulDiv Floor a b c` exactly when `int(c)` divides `int(a) * int(b)` | yes |
| M-05 | Monotonic: non-decreasing in `a` and in `b`, non-increasing in `c` | yes |
| M-06 | `mulDiv r a b c == mulDiv r b a c` | yes |
| M-07 | `mulDiv r a c c == a` for `c > 0` | yes |
| M-08 | Every failure in §4 occurs exactly when its condition holds, and never otherwise | no (tested) |
| M-09 | Identical results and failures on every SDK of the matrix: 3.4.11, 3.5.8 and 3.5.10 | no (tested) |

## 6. Implementation requirements

The algorithm that meets them, and why, is recorded in `packages/utils/vault-math-v1/ARCHITECTURE.md`.

1. **Exact representation.** Convert each operand to its exact integer `int(x)` with no rounding step. Convert back with no rounding step other than the one requested. Both conversions use only operations whose semantics the Daml-LF specification states: Numeric literals ([`daml-lf-2.rst` L553-L555](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L553-L555)), `ADD_NUMERIC` and `SUB_NUMERIC` ([L4022-L4032](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4022-L4032)), `CAST_NUMERIC` ([L4055-L4059](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4055-L4059)), `SHIFT_NUMERIC` ([L4061-L4065](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4061-L4065)) and `NUMERIC_TO_INT64` ([L4647-L4651](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4647-L4651)). They use neither `NUMERIC_TO_TEXT`, whose output format the specification leaves open ("Returns the numeric string representation of the numeric", [L4067-L4070](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4067-L4070)), nor `INT64_TO_NUMERIC`, which the specification does not describe.
2. **Integer width.** `int(x)` needs up to 38 decimal digits, and the product up to 76. Daml `Int` is 64-bit. The representation (for example limbs in base `10^9`, so that a limb product and a carry fit `Int`) must be justified from the `Int` range and overflow semantics cited from the LF specification; `packages/utils/vault-math-v1/ARCHITECTURE.md`, section 2, gives the justification.
3. **Division.** Exact multi-limb division with remainder. `Ceil` adds one unit when the remainder is non-zero.
4. **No `Numeric` arithmetic** inside the algorithm except exact conversions.
5. **Cost.** The execution cost relative to one `Decimal` division is stated in `packages/utils/vault-math-v1/ARCHITECTURE.md`, section 4. The vault calls `mulDiv` a bounded number of times per operation (§7).

## 7. Share conversion formulas

These are the formulas shared by the OpenZeppelin vaults for Solidity ([`ERC4626.sol` L237-L246](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L237-L246)), Stellar ([`storage.rs` L605-L646](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/storage.rs#L605-L646)) and Cairo ([`erc4626.cairo` L866-L887](https://github.com/OpenZeppelin/cairo-contracts/blob/9df148099ac2f21891add25e335b8472b88c5a3f/packages/token/src/erc20/extensions/erc4626/erc4626.cairo#L866-L887)), with `1` of the smallest token unit mapped to `u`.

Let `A = totalAssets`, `S = totalShares`, `k` the decimals offset, `VA = u`, `VS = 10^k * u`.

| Function | Definition | Rounding |
|---|---|---|
| `convertToShares assets` | `mulDiv Floor assets (S + VS) (A + VA)` | Floor |
| `convertToAssets shares` | `mulDiv Floor shares (A + VA) (S + VS)` | Floor |
| `previewDeposit assets` | `mulDiv Floor assets (S + VS) (A + VA)` | Floor |
| `previewMint shares` | `mulDiv Ceil shares (A + VA) (S + VS)` | Ceil |
| `previewWithdraw assets` | `mulDiv Ceil assets (S + VS) (A + VA)` | Ceil |
| `previewRedeem shares` | `mulDiv Floor shares (A + VA) (S + VS)` | Floor |

Rounding directions match Solidity ([`ERC4626.sol` L134-L179](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L134-L179)), Stellar ([`storage.rs` L163-L300](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/storage.rs#L163-L300)) and Cairo ([`erc4626.cairo` L424-L771](https://github.com/OpenZeppelin/cairo-contracts/blob/9df148099ac2f21891add25e335b8472b88c5a3f/packages/token/src/erc20/extensions/erc4626/erc4626.cairo#L424-L771)).

**Offset and bounds.** `k` is fixed at vault creation, `0 <= k <= KMAX` with `KMAX = 10` and default `0` (D-10). The Stellar vault suggests 10 as the upper bound of its offset as well ([`mod.rs` L415-L416](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/mod.rs#L415-L416)). With

- `AMAX(k) = floor(DMAX / 10^k)`, exact (in units of `u`, `int(AMAX(k)) = floor(int(DMAX) / 10^k)`),

every reachable state satisfies:

| Bound | Condition |
|---|---|
| Asset bound | `A + VA <= AMAX(k)` |
| Share bound | `S + VS <= 10^k * AMAX(k)` |

The share bound never exceeds `DMAX`, because `10^k * AMAX(k) <= DMAX`. It follows from the asset bound: every operation keeps `S + VS <= 10^k (A + VA)` (K-01, K-02), so `S + VS <= 10^k * AMAX(k)` whenever the asset bound holds (K-06). A deposit whose new `A` satisfies the asset bound mints at most `DMAX` shares, so `previewDeposit` cannot fail with `math-overflow` once the asset bound is checked (K-05). The asset bound is therefore checked before the conversion (SPEC §5.3 step 8), and a deposit beyond it fails with `vault-capacity-exceeded`, never with `math-overflow`. At `k = 0` both bounds are `A + VA <= DMAX` and `S + VS <= DMAX`.

**Evaluating the bounds.** In `Decimal`, `A + amount + VA` can exceed `DMAX` at `k = 0`, and the addition then throws `ArithmeticError`. The checks are evaluated as `amount <= AMAX(k) - VA - A` and `shares <= 10^k * AMAX(k) - VS - S`, whose terms are all non-negative and at most `DMAX` (`packages/utils/vault-math-v1/ARCHITECTURE.md`, section 6).

The derivation, the proofs and the capacity per `k` are in `packages/utils/vault-math-v1/ARCHITECTURE.md`, section 6, and `scripts/prove-math.py` (K-01 to K-07). The simpler bound `A <= DMAX - VA` allows only `k = 0`: the first deposit of `DMAX - u` mints `(DMAX - u) * 10^k`, above `DMAX` for every `k >= 1` (K-04).

**Reachable-state bound.** Any operation whose resulting `A` or `S` would break the asset bound or the share bound fails with `vault-capacity-exceeded` (SPEC §7).

**The pure functions** (SPEC §5.7). Each function of the table above takes a vault view, which gives `A`, `S` and `k`, and an amount `x`, and returns its definition. It fails, in this order:

1. `vault-capacity-exceeded` when the view is not a state this section allows: `k` outside `0 <= k <= KMAX`; `A < 0` or `S < 0`; `A + VA > AMAX(k)`; or `S + VS > 10^k (A + VA)`. The last condition is the invariant that every operation keeps (K-01, K-02); with the asset bound it implies the share bound (K-06), and it is what keeps every conversion below within `DMAX`. The checks are evaluated as `A <= AMAX(k) - VA` and `S <= 10^k (A + VA) - VS`, where `10^k (A + VA)` is `mulDiv Floor (A + VA) VS VA`, exact and at most `DMAX`.
2. `vault-capacity-exceeded` when `x` would take the vault past the asset bound, for the two operations that raise `A`:
   - `convertToShares x` and `previewDeposit x` preview a deposit of `x`: `x <= AMAX(k) - VA - A`, as in SPEC §5.3 step 8. Within it the result is at most `DMAX` and the new state keeps both bounds (K-05, K-06).
   - `previewMint x` previews a mint of `x` shares, which charges `previewMint x` assets: `x <= mulDiv Floor (AMAX(k) - VA - A) (S + VS) (A + VA)`. This is exactly `previewMint x <= AMAX(k) - VA - A`, is evaluated before the conversion, and cannot overflow once step 1 holds (K-08). The new state then keeps both bounds (K-08).
3. The failures of `mulDiv` (§4): `math-negative-operand` when `x < 0`, and `math-overflow` when the result exceeds `DMAX`. After steps 1 and 2 an overflow is possible only in `convertToAssets`, `previewRedeem` and `previewWithdraw`, and only for an amount beyond the vault's supply or assets. Their operations lower `A` and `S`, so no bound of this section applies to them; the vault refuses such amounts itself (SPEC §5.4).

A view of a vault state reached through vault choices always passes step 1 (I-08; K-01, K-02). `VaultState`'s `ensure` enforces only the asset and share bounds (SPEC §4.1), so a state the operator creates directly with `S + VS > 10^k (A + VA)` fails every conversion with `vault-capacity-exceeded`.

No function clamps, saturates or otherwise adjusts a value: every view or amount outside these bounds fails with the error stated above, and every other input returns its definition exactly.

## 8. Vault-level properties that depend on this math

| ID | Property | Source |
|---|---|---|
| V-01 | `previewRedeem (previewDeposit a) <= a` for every state and `a` | Rounding against the caller; [`erc4626.adoc` L32](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/docs/modules/ROOT/pages/erc4626.adoc#L32) |
| V-02 | `previewMint s >= convertToAssets s` and `previewWithdraw a >= convertToShares a` | Rounding against the caller (§7) |
| V-03 | No sequence of deposits and redemptions by one party, with no yield added, ends with more underlying than it put in | Rounding against the caller; [daml-props `PUBLIC_AUDITS.md` L210-L214](https://github.com/OpenZeppelin/daml-props/blob/901571e509e899f3b2870fe9baaa6fc4ad8ff21b/PUBLIC_AUDITS.md#L210-L214) |
| V-04 | With `A = 0` and `S = 0`, the first deposit of `a` mints `mulDiv Floor a VS VA`, which equals `a * 10^k` | Formula above |
| V-05 | A donation to the vault's account leaves every conversion unchanged | D-06 |

V-01 to V-05 are tested at `Decimal` precision with values down to `u`.
