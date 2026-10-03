# Vault V1

A Daml vault that holds an underlying CIP-0112 asset and issues shares against it.

| Field | Value |
|---|---|
| Package | `cvx-vault-v1` |
| Public modules | `Cayvox.VaultV1`, `Cayvox.VaultV1.Conversion` |
| Version | `0.1.0` |
| Status | Pre-release; unaudited |

## What it provides

`Cayvox.VaultV1` holds the vault, and exports `ShareRules`, the share registry's rules contract, which the operator creates beside the vault state. The package is an implementation package: it defines no interfaces and no exceptions. Modules under `Cayvox.VaultV1.Internal` are not public API.

| Template | Signatory | Choices | Use |
|---|---|---|---|
| `VaultState` | operator | `Vault_ExecuteDeposits`, `Vault_ExecuteRedeems`, `Vault_AddAssets`, `Vault_Pause`, `Vault_Unpause` | One vault: its identity, its registries, `A`, `S`, the offset `k`, the mode and the pause flag. Implements `Vault` of `cvx-api-vault-v1` |
| `DepositRequest` | requester | `DepositRequest_Allocate`, `DepositRequest_Cancel` | An offer to deposit `amount` of underlying for at least `minOut` shares before `deadline` |
| `RedeemRequest` | requester | `RedeemRequest_Allocate`, `RedeemRequest_Cancel` | An offer to redeem `amount` shares for at least `minOut` underlying before `deadline` |

A requester creates a request, and may fund it at once with a committed allocation of its input that names the request's settlement. A committed allocation cannot be withdrawn before its deadline, so funding trades the requester's freedom to withdraw for a request no one can fail by withdrawing; until the deadline the operator can settle it (caveats below). [`docs/SPEC.md`](../../../docs/SPEC.md) §2 and §5.2 give the requester's steps and what each submitter must be handed. An execution then settles each request in one transaction: the requester's input moves to the vault account (deposit) or to `cip-112/burn` (redemption), and the output moves to the requester's `receiver` account, minted from `cip-112/mint` (deposit) or paid from the vault account (redemption). The amounts come from `Cayvox.VaultV1.Conversion` on the vault's running state, and `A` and `S` change in the same transaction.

```daml
import Splice.Api.Token.HoldingV2 (Holding)
import Splice.Api.Token.MetadataV1 (ExtraArgs)
import Cayvox.VaultV1

deposit : ContractId VaultState -> Party -> ContractId DepositRequest -> [ContractId Holding] -> ExtraArgs -> ExtraArgs -> Update ExecResult
deposit vault operator request inputs assetContext shareContext =
  exercise vault Vault_ExecuteDeposits with
    executor = operator
    items = [DepositItem with request; fundingAllocation = None; fundingInputs = inputs]
    assetContext; shareContext
```

An execution fails, and changes nothing, with category `InvalidGivenCurrentSystemStateOther` and one of these identifiers, checked in the order of [`docs/SPEC.md`](../../../docs/SPEC.md) §5 and listed in §7:

| `errorId` | Condition |
|---|---|
| `cayvox.com/vault-unauthorized-executor` | Permissioned: the executor is not the operator. Permissionless: a request is not the executor's own |
| `cayvox.com/vault-paused` | A deposit or an asset addition while paused |
| `cayvox.com/vault-batch-size`, `cayvox.com/vault-duplicate-request` | A batch outside 1 to 25 requests, or a request listed twice |
| `cayvox.com/vault-wrong-vault`, `cayvox.com/vault-request-expired` | A request of another vault, or at or after its deadline |
| `cayvox.com/vault-allocation-mismatch` | An allocation not bound to its request, or not of the registry's own template; an asset addition whose source is the vault account |
| `cayvox.com/vault-capacity-exceeded` | `A` or `S` would leave the vault's bounds |
| `cayvox.com/vault-zero-shares`, `cayvox.com/vault-zero-assets` | The output rounds to zero |
| `cayvox.com/vault-slippage` | The output is below `minOut` |
| `cayvox.com/vault-insufficient-assets` | A redemption would pay more than `A` |
| `cayvox.com/vault-no-shares` | An asset addition to a vault with no shares |
| `cayvox.com/vault-invalid-amount` | A request or an asset addition with a non-positive amount or a negative `minOut` |
| `cayvox.com/vault-already-paused`, `cayvox.com/vault-not-paused` | Pausing a paused vault, or unpausing an active one |

`Cayvox.VaultV1.Conversion` holds the vault's conversion and preview functions. Each takes a `VaultView` of `cvx-api-vault-v1`, whose `totalAssets`, `totalShares` and `decimalsOffset` are `A`, `S` and `k`, and an amount. With `VA = 0.0000000001` and `VS = 10^k * 0.0000000001`, every product and quotient is exact and rounded once (`mulDiv` of `cvx-vault-math-v1`):

| Function | Result | Rounding |
|---|---|---|
| `convertToShares`, `previewDeposit` | `assets * (S + VS) / (A + VA)`: the shares a deposit of `assets` mints | down |
| `convertToAssets`, `previewRedeem` | `shares * (A + VA) / (S + VS)`: the assets a redemption of `shares` pays | down |
| `previewMint` | `shares * (A + VA) / (S + VS)`: the assets a mint of `shares` charges | up |
| `previewWithdraw` | `assets * (S + VS) / (A + VA)`: the shares a withdrawal of `assets` burns | up |

```daml
import Cayvox.Api.VaultV1 (VaultView)
import Cayvox.VaultV1.Conversion (previewDeposit)

sharesFor : VaultView -> Decimal -> Decimal
sharesFor vaultView assets = previewDeposit vaultView assets
```

The functions fail, in this order, with category `InvalidGivenCurrentSystemStateOther`:

| Condition | `errorId` |
|---|---|
| The view is outside the vault's bounds: `k` outside 0 to 10, `A` or `S` negative, `A + VA` above `floor(DMAX / 10^k)`, or `S + VS` above `10^k (A + VA)` | `cayvox.com/vault-capacity-exceeded` |
| A deposit (`convertToShares`, `previewDeposit`) or a mint (`previewMint`) would take `A + VA` above `floor(DMAX / 10^k)` | `cayvox.com/vault-capacity-exceeded` |
| The amount is negative | `cayvox.com/math-negative-operand` |
| The result exceeds `DMAX`: for `convertToAssets`, `previewRedeem` and `previewWithdraw`, only with an amount beyond the vault's supply or assets | `cayvox.com/math-overflow` |

A view of a vault state reached through vault choices never fails the first check; a state the operator creates directly with `S + VS` above `10^k (A + VA)` fails every conversion with `vault-capacity-exceeded`. The functions are pure: a call bound by `let` fails even when its value is unused.

The package contains the share registry: the operator's registry for the vault's share instrument, `InstrumentId {admin = operator, id = <vault identifier>}`. Clients use it through the Canton Token Standard V2 interfaces of Splice 0.8.4:

| Interface | Template | Use |
|---|---|---|
| `AllocationFactory`, `SettlementFactory`, `TransferFactory` | `ShareRules` | Allocate shares to a settlement, settle a batch of allocations, transfer shares |
| `Holding` | `ShareHolding` | Shares held by one account |
| `Allocation` | `ShareAllocation` | An account's approval of its leg sides in one settlement |
| `TransferInstruction` | `ShareTransferInstruction` | A pending transfer |
| `EventLog` | `ShareEventLog` | The holdings-change events that explain every change to share holdings |

Shares are minted by settling an allocation from the special account `cip-112/mint` and burned by settling one to `cip-112/burn` (CIP-0112). [`docs/REGISTRY-MUSTS.md`](../../../docs/REGISTRY-MUSTS.md) lists every requirement of the standard the registry meets and the test that proves it.

## Authority and lifecycle

- The operator creates `VaultState` with `A = 0` and `S = 0`, and the share registry's `ShareRules`. Every vault choice consumes the state and creates its successor with the same identity fields.
- In Permissioned mode the operator executes every request. In Permissionless mode a requester executes its own requests, with the vault state, the share registry's rules and, for a redemption, the vault-account holdings that pay it, all disclosed by the operator. The operator's participant confirms every execution.
- A batch holds 1 to 25 requests of one kind. Each redemption in a batch pays from the vault-account holdings the executor names for it, then from the change the batch's previous redemption returned to the vault account, so one holding that covers the batch can be named once, by the first redemption. A holding named twice is spent the first time, and the execution fails.
- A request executes at most once, before its deadline. Its requester cancels it at any time with `DepositRequest_Cancel` or `RedeemRequest_Cancel`, which also withdraws the request's allocations it is given; a committed allocation is withdrawn only after its deadline.
- Only the operator adds assets (`Vault_AddAssets`, while not paused and with `S > 0`), pauses and unpauses. Pausing stops deposits and asset additions; redemptions and cancellations continue.
- Underlying sent to the vault account outside `Vault_ExecuteDeposits` and `Vault_AddAssets` is not counted in `A` and changes no conversion.
- The accounting assumes an underlying without transfer or holding fees: `A` moves by exactly each leg's amount, so a fee on vault payouts or a decaying holding leaves custody below `A`.

### Share registry

- The operator is the instrument admin and signs every registry contract. A share holding is signed by the operator and its owner, and its owner is never the operator, so shares exist only through a settlement both have authorized.
- `ShareRules` is signed by the operator and disclosed to the parties that use it. Archiving it ends new allocations, batch settlements and transfers; existing allocations and pending transfers keep their choices.
- An allocation that sends shares locks them in one holding until the allocation is settled, cancelled or withdrawn. Settle: the operator with the settlement's executors, before the settlement deadline. Cancel: the executors. Withdraw: the account's owner or provider; a committed allocation, which always has a deadline, only after it.
- A transfer completes at once when the receiver's owner is among its actors. Otherwise the shares are locked until the receiver's owner accepts before `executeBefore`, the receiver's parties reject, or the sender's parties withdraw.
- An account's provider observes the account's holdings, allocations, transfers and events. It withdraws allocations and rejects or withdraws transfers alone; allocating, instructing and accepting need the owner.
- Every failure has an identifier `cayvox.com/registry-...` and category `InvalidGivenCurrentSystemStateOther`. Match failures on the identifier, never on the message text:

| `errorId` | Condition |
|---|---|
| `registry-wrong-admin`, `registry-wrong-instrument` | The allocation or instrument is administered by another party, or is not this registry's share instrument |
| `registry-unauthorized-actors` | The actors are not a group allowed to take the action |
| `registry-invalid-account`, `registry-invalid-amount` | An account the registry does not support for the action, or an amount that is not positive |
| `registry-iterated-settlement` | Next-iteration funding was requested |
| `registry-deadline-passed`, `registry-not-yet-requested` | A settlement deadline or `executeBefore` has been reached, or `requestedAt` is later than the ledger time |
| `registry-invalid-input-holding`, `registry-insufficient-funds` | An input is not an unlocked share holding of the account, or the inputs do not cover the amount |
| `registry-no-transfer-legs`, `registry-duplicate-leg` | A settlement without legs, or a leg or authorization that appears twice |
| `registry-settlement-mismatch`, `registry-missing-authorization`, `registry-superfluous-authorization` | An allocation of another settlement, a leg side no allocation authorizes, or an allocation for a side not settled |
| `registry-committed-allocation`, `registry-committed-without-deadline` | Withdrawing a committed allocation before its deadline, or creating one without a deadline |
| `registry-field-too-large` | A text, list or metadata field above its bound |

## Scope and security caveats

- The package is pre-release and unaudited.
- Depositors trust the operator with custody: the operator owns the vault account and can move the underlying outside every vault choice. The operator, as sole signatory of `VaultState`, can also archive it and create one with other totals, and can mint shares through the share registry outside any execution. None of these can be prevented; each is detectable by reconciling `A` with the underlying that vault choices moved into and out of the vault account (I-01), and `S` with the sum of share holdings (I-02).
- Reconciliation needs the operator's view: the vault state has no observers, and only the operator sees every share holding and the vault account. The operator runs it (`tools/vault-reconcile`), or gives an auditor read rights for the operator party on its participant; a depositor without either relies on its trust in the operator.
- Every request settlement names the operator as its only executor, so the operator can settle a request's input alone, outside every vault choice, and pay nothing: a live request is a standing authorization of its `amount` to the operator until it executes, is cancelled with all its allocations withdrawn, or reaches its deadline; a committed funding allocation can be withdrawn only after its deadline, so a funded request stays settleable by the operator until then even after cancellation. Reconciliation detects it ([`docs/SECURITY.md`](../../../docs/SECURITY.md) T-21). Request-time funding gives the operator certainty of funds, and leaves the input settleable by the operator until the deadline. Execution-time funding leaves no allocation before the execution; the operator can still take the input once the requester has handed it its holdings, as a Permissioned execution needs, until the request is cancelled. In Permissionless mode the requester never hands its holdings over, and the operator cannot take its input alone. A requester that does not want to rely on the operator for this step uses execution-time funding in Permissionless mode. Keep deadlines short and cancel requests that do not execute.
- In Permissionless mode every execution consumes the vault state: a requester that keeps executing small requests makes others retry. The operator can still batch requests itself.
- In Permissioned mode a request executes only when the operator submits it. In Permissionless mode the operator can still execute anyone's requests, and must disclose the vault state and confirm every execution; the underlying registry's factory is disclosed by that registry. A pause never blocks a redemption, but exit always depends on the operator acting.
- In a batch, the executor chooses the order, and the order affects each request's price; `minOut` and `deadline` bound the effect for each requester.
- A batch is one transaction, so one request can fail it: its requester archives it, withdraws an uncommitted funding allocation, spends the holdings named for it, or lets its deadline pass. An executor that retries drops the failing request; committed funding removes all but the requester archiving its request and the deadline.
- The deadline applies to the ledger time the submitting participant assigns, which comes after the submission is sent. Submit an execution at least one second before the earliest deadline of its batch: a batch with an expired request fails as a whole with `vault-request-expired`. Keep the synchronizer's ledger time record time tolerance at its default of one minute, or well above a batch's submission time.
- `Vault_AddAssets` raises the price in one step, so a requester can deposit just before a predictable addition and redeem just after; add yield in small, frequent steps, and only once `S` is well above the smallest unit.
- After `Vault_AddAssets` the share price can exceed one, and a deposit below the price mints zero shares and fails with `vault-zero-shares`; `minOut` protects the requester.
- CIP-0112 is Approved, not Final, and the V2 API package IDs are pinned to Splice 0.8.4.
- The registry implements the V2 interfaces only. Wallets and parsers that read only V1 interfaces and events see no share holdings or movements.
- Settlement is single-iteration: allocations with next-iteration funding or extra leg sides are rejected.
- A funded request's allocation must come from the registry's V2 allocation factory; an allocation from a V1 flow is of another template and fails with `vault-allocation-mismatch`.
- Allocations and locks do not expire. Locked shares return to their owner when the allocation is cancelled or withdrawn, or the transfer is rejected or withdrawn. A committed allocation always carries a settlement deadline; its authorizer can withdraw it once the deadline has passed.
- The instrument identifier is unique per operator by the operator's discipline: the ledger does not enforce one `ShareRules` per instrument. Never reuse the identifier of a retired vault: its shares and live requests would act on the new one.
- `VaultState` records the registries' factories by contract ID, and v1 has no choice that changes them. When a registry replaces its factory, the operator either re-creates the vault state with the new factory and every other field unchanged, which reconciliation accepts because the totals do not change ([`docs/SECURITY.md`](../../../docs/SECURITY.md) §2, "Registry migration"), or creates a new vault. A migration choice can be added in a later version through Smart Contract Upgrade, which allows adding a choice.
- Give each vault its own vault account: the custody check compares one vault's `A` with the account's holdings, and a shared account lets one vault's redemptions spend another's underlying.
- The vault exercises the factories recorded in `VaultState` with the operator's authority. The operator records only the registries' own factories, read from its own participant, and vets only the registries' packages: a factory of another package would run with the operator's authority ([`docs/SECURITY.md`](../../../docs/SECURITY.md) T-20). The vault cannot check this itself: a `fetch` needs the authority of a stakeholder of the fetched contract, and the operator is not one of the underlying registry's factory.
- The registry refuses a committed allocation without a settlement deadline (`cayvox.com/registry-committed-without-deadline`). An application that requests one from a share holder gets this failure.
- The token standard allows such an allocation, ended only by settlement, cancellation or registry-specific expiry, and Splice's TestTokenV2 and Amulet accept it; no application flow in Splice 0.8.4 requests one, but an application that does must give share allocations a settlement deadline or leave them uncommitted.
- Fields are bounded: the vault identifier to 245 characters, so that every settlement identifier built from it fits; other texts to 256 characters, metadata of 16 entries with values of 1,024 characters, 25 leg sides per allocation, 10 executors per settlement, 50 inputs per transfer.

## Deployment notes

- Before production deployment, read the target synchronizer's ledger time record time tolerance and confirmation response timeout, from a participant connected to it (the `synchronizer_parameters` console commands) or from the configuration its operators publish. The deadline rule above, and the time after which an execution fails when the operator's participant does not confirm, follow from these two parameters.
- Run the operator's participant on a host that stays available: a participant that sleeps or is starved of CPU while a request is in flight makes the request time out, and nothing moves.

## Upgrades

- Templates add fields only as `Optional`, under Smart Contract Upgrade; `scripts/check-upgrade.sh` checks a patch candidate with `dpm upgrade-check`.
- An exercise runs the package version its submitter selects among those vetted. In Permissionless mode the requester submits, so it can pin an older vetted version and run that version's guards. After a security fix, the operator unvets the old version on its participant; until then the fix reaches only exercises that select the new version, as [`docs/SECURITY.md`](../../../docs/SECURITY.md) T-09 states.
- The vault keeps depending on `cvx-api-vault-v1` at `0.1.0`, which cannot be upgraded.

## Compatibility

Daml-LF `2.1`, built with the SDK that [`multi-package.yaml`](../../../multi-package.yaml) declares. Tested in memory on SDK 3.4.11, 3.5.8 and 3.5.10, and on Canton sandboxes of SDK 3.4.11 (protocol version 34) and SDK 3.5.10 (protocol version 35).

## Build

From the repository root:

```sh
DAML_PACKAGE=packages/token/vault-v1 dpm build
```

## Consume a local build

A consumer data-depends on the three packages and on the Splice V2 API DARs its code uses, as [`examples/vault-admission-v1`](../../../examples/vault-admission-v1/daml.yaml) does:

```yaml
data-dependencies:
  - ../canton-vault/packages/utils/vault-math-v1/.daml/dist/cvx-vault-math-v1-0.1.0.dar
  - ../canton-vault/packages/token/api-vault-v1/.daml/dist/cvx-api-vault-v1-0.1.0.dar
  - ../canton-vault/packages/token/vault-v1/.daml/dist/cvx-vault-v1-0.1.0.dar
  - ../canton-vault/dars/vendor/splice-api-token-metadata-v1-1.0.0.dar
  - ../canton-vault/dars/vendor/splice-api-token-holding-v2-1.0.0.dar
  - ../canton-vault/dars/vendor/splice-api-token-allocation-v2-1.0.0.dar
  - ../canton-vault/dars/vendor/splice-api-token-allocation-instruction-v2-1.0.0.dar
```

```daml
import Splice.Api.Token.HoldingV2 (Holding)
import Splice.Api.Token.MetadataV1 (ExtraArgs)
import Cayvox.Api.VaultV1 (Vault, VaultView)
import Cayvox.VaultV1
import Cayvox.VaultV1.Conversion
```

Build `cvx-api-vault-v1` with SDK 3.4.11 only: its package ID is recorded (`dars/api-packages.yaml`), and another SDK produces another ID.
