# Vault Math V1

Exact multiply-then-divide for Daml `Decimal`, with the rounding direction chosen by the caller. It is the arithmetic of share and asset conversions in a vault.

| Field | Value |
|---|---|
| Package | `cvx-vault-math-v1` |
| Public module | `Cayvox.VaultMathV1` |
| Version | `0.1.0` |
| Status | Pre-release; unaudited |

## What it provides

| Name | Type | Meaning |
|---|---|---|
| `Rounding` | `data Rounding = Floor \| Ceil` | Direction of rounding. Results are non-negative, so `Floor` rounds toward zero and `Ceil` away from zero |
| `mulDiv` | `Rounding -> Decimal -> Decimal -> Decimal -> Decimal` | `mulDiv r a b c` is the exact `a * b / c`, rounded in direction `r` to a `Decimal` |

`mulDiv` computes on the exact integers behind its operands, so the product `a * b` is never rounded and never overflows on its own. Only the final result must fit in a `Decimal`. A plain `a * b / c` in `Decimal` rounds twice, half-even, and fails when `a * b` exceeds 28 integer digits.

```daml
mulDiv Floor 2.0 1.0 3.0   -- 0.6666666666
mulDiv Ceil  2.0 1.0 3.0   -- 0.6666666667
mulDiv Floor 9999999999999999999999999999.9999999999 9999999999999999999999999999.9999999999 9999999999999999999999999999.9999999999
                           -- 9999999999999999999999999999.9999999999
```

The package is a utility package: it has no templates, interfaces, exceptions or serializable public state. Modules under `Cayvox.VaultMathV1.Internal` are not public API.

## Failures

`mulDiv` fails with `failWithStatusPure` (`DA.Fail`). Each failure has category `InvalidGivenCurrentSystemStateOther` and empty `meta`. The first condition that holds, in this order, determines the failure:

| Condition | `errorId` |
|---|---|
| `a < 0` or `b < 0` | `cayvox.com/math-negative-operand` |
| `c <= 0` | `cayvox.com/math-non-positive-divisor` |
| The rounded result exceeds `9999999999999999999999999999.9999999999` | `cayvox.com/math-overflow` |

Match failures on `errorId`, never on the message text.

Daml evaluates strictly. A failing `mulDiv` bound by `let` fails the transaction even when its value is never used; a call in a branch that is not taken is not evaluated. A caller that must not fail checks the conditions above before the call. In Daml Script, `tryFailureStatus` catches the failure of a pure call.

## Authority and lifecycle

The package holds pure functions only. It creates, archives and authorizes nothing, and reads no ledger state.

## Scope and security caveats

- The package is pre-release and unaudited.
- One call costs many times a `Decimal` division, most at the largest operands ([`ARCHITECTURE.md`](ARCHITECTURE.md) of this package, section 4). Callers keep the number of calls per transaction bounded.
- Correctness evidence: a differential suite against an exact oracle, proofs of the specification with Z3, and mutation testing ([`ARCHITECTURE.md`](ARCHITECTURE.md) of this package, section 5). The proofs cover the specification, not the Daml code; the differential suite ties the code to it.

## Compatibility

Daml-LF `2.1`, built with the SDK that [`multi-package.yaml`](../../../multi-package.yaml) declares. Tested in memory on SDK 3.4.11, 3.5.8 and 3.5.10, and on Canton sandboxes of SDK 3.4.11 (protocol version 34) and SDK 3.5.10 (protocol version 35), with identical results and failures.

## Build

From the repository root:

```sh
DAML_PACKAGE=packages/utils/vault-math-v1 dpm build
```

## Consume a local build

```yaml
data-dependencies:
  - ../canton-vault/packages/utils/vault-math-v1/.daml/dist/cvx-vault-math-v1-0.1.0.dar
```

```daml
import Cayvox.VaultMathV1 (Rounding (..), mulDiv)

-- amount * numerator / denominator, rounded down.
proportional : Decimal -> Decimal -> Decimal -> Decimal
proportional amount numerator denominator = mulDiv Floor amount numerator denominator
```
