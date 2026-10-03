# Specification

This document specifies what the vault does. Decisions it relies on are cited as `D-nn` (`docs/DECISIONS.md`) and threats as `T-nn` (`docs/SECURITY.md`). Upstream sources are linked at a pinned tag or commit. Behaviour that this project establishes by its own tests cites the test; tests are in `test/vault-v1-test` unless stated otherwise. Names are working names (D-17).

## 1. Scope

**In v1**

- One vault holds one underlying CIP-0112 V2 instrument (D-01, D-02, D-03).
- Requests to deposit assets and to redeem shares, executed atomically through allocations (D-04).
- Permissioned and Permissionless modes (D-05).
- A share token that is a CIP-0112 V2 instrument administered by the vault operator (D-07).
- Recorded accounting, operator-only yield recognition, pause (D-06, D-08, D-14).
- Exact conversions and previews (D-09, D-10, `docs/MATH.md`).

**Outside v1, with extension points documented**

- Baskets of instruments; cross-synchronizer and cross-chain operation (D-02).
- Fees, loss recognition, strategies that move assets out of the vault account (D-08).
- Exact-output requests (`mint`, `withdraw`); they exist as previews (D-04).
- A V1 `Holding` instance on shares (D-07).

## 2. Actors

Each row cites the source or the test that establishes it.

| Actor | Role | Authority | Must be online |
|---|---|---|---|
| Operator | Creates and runs the vault; instrument admin of the share token; owner of `vaultAccount` at the underlying registry | Sole signatory of `VaultState` and of the share registry's contracts. Controller of each request's `Request_Allocate` (§4.2). Actor of the vault's own allocations and of every `SettlementFactory_SettleBatch`, because `settlement.executors = [operator]` and the default batch settlement requires `actors` to equal the executors ([Splice `Utils/Internal/Allocations.daml:377-379`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L377-L379); `test_interop_depositMintsShares`) | Its participant, for every execution, because it confirms as signatory: Canton requires confirmation from the participants hosting each signatory of a contract the transaction uses ([Canton documentation, confirmation policies](https://docs.canton.network/overview/reference/smart-contract-consensus); D-05). Its application only in Permissioned mode, where it submits |
| Requester | Asks to deposit or redeem | Sole signatory of its request. Authorizer of its input allocation, either at request time or through `Request_Allocate` at execution, and of its receipt allocation through `Request_Allocate` (§4.2) | Only to create the request, and to fund it at request time if it chooses that variant; not at execution in Permissioned mode (`test_interop_depositMintsShares`, `test_interop_fundedDeposit`, `test_interop_redemptionBurnsShares`) |
| Underlying registry admin | Administers the underlying instrument | As defined by its registry; outside this library. Signs its factory contracts and every holding and allocation of its instrument | Its participant, for every execution (signatory of the holdings and allocations settled) |
| Executor | Submits the execution | The operator in Permissioned mode. In Permissionless mode, the operator, or a requester when every request in the batch is its own (D-05; `test_vault_unauthorizedExecutor_permissioned`, `test_vault_unauthorizedExecutor_permissionless`, `test_order_permissionlessMixedBatch`) | As the submitter |

**Disclosure responsibilities.** A party can only disclose a contract it sees ([Canton documentation, ledger model](https://docs.canton.network/overview/reference/ledger-model-detailed)). The submitter of an execution must be handed every contract it does not see:

| Submitter | Contract | Handed over by | Shown by |
|---|---|---|---|
| Operator | The underlying registry's factory contract and choice context, and the holdings locked by requesters' funded allocations | The underlying registry, through its settlement-factory endpoint | Splice `allocation-v2.yaml`: [the endpoint](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/openapi/allocation-v2.yaml#L12-L17) returns a [choice context with the contracts to disclose](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/openapi/allocation-v2.yaml#L199-L223); `test_vault_depositRedeem_permissionedFunded` |
| Operator | The requester's input holdings, when the input is allocated at execution | The requester | `test_vault_depositRedeem_permissionedUnfunded`; `test_hazard_t21_executionTimeFunding_holdingsHanded` |
| Requester (Permissionless) | The current `VaultState` and the share registry's factory contract | The operator | `test_vault_depositRedeem_permissionlessUnfunded`, `test_vault_depositRedeem_permissionlessFunded` |
| Requester (Permissionless) | The underlying registry's factory contract | The underlying registry | The same tests |
| Requester (Permissionless, redemption) | The vault account's input holdings | The operator | `test_order_redemptionsChainChange_permissionless` |

A disclosure of a contract consumed since it was taken fails the submission; the executor retries with the successor (D-16).

The trust placed in the operator is stated in `docs/SECURITY.md` §2.

## 3. Packages

| Package | Contents | Depends on |
|---|---|---|
| `cvx-vault-math-v1` | `Rounding`, `mulDiv` (`docs/MATH.md`) | Nothing beyond the standard library |
| `cvx-api-vault-v1` | Interface `Vault` with `VaultView` (D-12); no choices | `splice-api-token-holding-v2` and `splice-api-token-metadata-v1`, for the `InstrumentId` and `Metadata` of the view |
| `cvx-vault-v1` | Templates below; conversion and preview functions | `cvx-vault-math-v1`, `cvx-api-vault-v1`, Splice V2 API packages (D-03). No Pausable package in v1 (D-14) |

`cvx-vault-v1` depends on no other implementation package, and the math package is a utility package that defines no templates, interfaces, exceptions or serializable public state, as the canton-contracts dependency policy asks ([`ARCHITECTURE.md:77-80`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L77-L80)).

## 4. State

### 4.1 `VaultState` (template in `cvx-vault-v1`)

| Field | Meaning | Constraint in `ensure` |
|---|---|---|
| `operator : Party` | Operator | none |
| `vaultId : Text` | Identifier, unique per operator by operator discipline (no keys, D-11) | Non-empty, at most 245 characters: every settlement identifier is built from it, the longest being `<vaultId>/add-assets`, and the share registry bounds settlement identifiers at 256 |
| `asset : InstrumentId` | Underlying instrument | none |
| `shareInstrument : InstrumentId` | Share instrument, admin is `operator` | `shareInstrument.admin == operator` |
| `vaultAccount : Account` | V2 account that holds the underlying | `vaultAccount.owner == Some operator` |
| `mode : Mode` | `Permissioned` or `Permissionless` | none |
| `assetRegistry`, `shareRegistry : RegistryRef` | The `AllocationFactory` and `SettlementFactory` contract IDs of the underlying and share registries. Every allocation and settlement of an execution uses these, never factories supplied by the executor, because a factory runs with the authority of the choice that exercises it (`docs/SECURITY.md` T-06; `test_hazard_t06_forgedVaultAndFactory`) | none |
| `decimalsOffset : Int` | `k` in `docs/MATH.md` §7 | `0 <= k <= KMAX`, with `KMAX = 10`; `0` by default (D-10) |
| `totalAssets : Decimal` | `A` | `>= 0.0` and the asset bound `A + VA <= AMAX(k)`, with `AMAX(k) = floor(DMAX / 10^k)` (`docs/MATH.md` §7) |
| `totalShares : Decimal` | `S` | `>= 0.0` and the share bound `S + VS <= 10^k * AMAX(k)` (`docs/MATH.md` §7) |
| `paused : Bool` | Pause flag (D-14) | none |
| `meta : Metadata` (Splice `splice-api-token-metadata-v1`) | Extension data (D-12) | Bounded |

- Signatory: `operator`. Observers: none by default; requesters read it by explicit disclosure (D-15).
- Implements `cvx-api-vault-v1` `Vault`. In v1, `paused` is a local flag with the semantics of D-14, and `VaultState` implements no `Pausable` interface; the interface instance can be added later under SCU (D-14).
- Every consuming choice recreates the successor with the same identity fields. Identity fields never change.

### 4.2 `DepositRequest` and `RedeemRequest`

The two templates have the same structure. Their choices are named per template: `DepositRequest_Allocate`, `DepositRequest_Cancel`, `RedeemRequest_Allocate` and `RedeemRequest_Cancel`; this section calls them `Request_Allocate` and `Request_Cancel`. Both templates are in `Cayvox.VaultV1`; `test_vault_delegationChecks` and `test_vault_delegationChecks_redeem` exercise the checks below for each.

| Field | Deposit | Redeem |
|---|---|---|
| `operator`, `vaultId` | Target vault | Target vault |
| `requester : Party` | Signatory | Signatory |
| `payAccount : Account` | Account that sends `amount` of underlying | Account that sends `amount` of shares |
| `receiver : Account` | Account that receives shares | Account that receives underlying |
| `amount : Decimal` | Assets offered, `> 0` | Shares offered, `> 0` |
| `minOut : Decimal` | Minimum shares, `>= 0` | Minimum assets, `>= 0` |
| `deadline : Time` | Last time of execution, exclusive | Same |
| `funded : Bool` | Whether the requester allocated the input at request time (§5.2) | Same |
| `meta` | Extension data, bounded | Same |

- Signatory `requester`; observer `operator`.
- **Binding**: every allocation for the request carries `settlement = SettlementInfo {executors = [operator], id = <vaultId> <> "/deposit" or "/redeem", cid = Some <the request's contract ID>, meta = empty}`. The contract ID makes `(id, cid, meta)` unique, as the executors MUST ensure ([Splice `AllocationV2.daml:36-37`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L36-L37)). The request carries no separate binding field (`test_vault_allocationMismatch_fundingFields`).
- **Legs.** The input leg `in` goes from `payAccount` to `vaultAccount` (deposit) or to `cip-112/burn` (redemption), for `amount`. The output leg `out` goes from `cip-112/mint` (deposit) or from `vaultAccount` (redemption) to `receiver`, for the amount the vault computes at execution.
- **Choice `Request_Allocate`**, consuming, controller `operator`. It is the requester's delegation of receipt: the settlement needs the receiver's authorization for the output leg, for its exact amount ([Splice `Utils/Internal/Allocations.daml:163-165`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L163-L165), [`:454-460`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L454-L460); [`AllocationV2.daml:81-96`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L81-L96)), and that amount is fixed only at execution. The requester's authority (signatory) and the operator's (controller) together authorize its consequences ([Canton documentation, ledger model](https://docs.canton.network/overview/reference/ledger-model-detailed)). Arguments: the executing `VaultState` contract ID, the output leg, the requester's input holdings (unfunded requests), and the registries' choice contexts. Before creating anything, it checks, in order:
  1. The vault, by a typed fetch of the contract ID, has `operator` and `vaultId` equal to the request's own fields: else `vault-wrong-vault`. A contract of another template fails the fetch (`test_hazard_t06_forgedVaultAndFactory`).
  2. `isLedgerTimeLT deadline`: else `vault-request-expired`.
  3. The output leg equals the leg built from the request and the vault, except for its amount: identifier, sender, receiver and instrument. Else `vault-allocation-mismatch`.
  4. `amount > 0` and `amount >= minOut`: else `vault-slippage`.

  It then creates, at the registries recorded in `VaultState`, with the settlement built from its own contract ID and `settlementDeadline = Some deadline`, `committed = False`:
  - exactly one allocation for the receiver side of the output leg;
  - exactly one allocation for the sender side of the input leg, for exactly `amount`, only when `funded` is false.

  It returns both: one allocation when funded, two otherwise (`test_interop_fundedDeposit`, `test_interop_depositMintsShares`, `test_vault_delegationOutsideAnExecution`). Being consuming, it runs at most once; a second call fails as a contract that is no longer active (`test_vault_duplicateRequest`). A party other than the operator, the requester included, cannot exercise it (`AuthorizationError`, `test_vault_onlyTheOperatorActs`).
- **Choice `Request_Cancel`**, controller `requester`: archives the request and, in the same transaction, withdraws the allocations passed to it, each of which must have this request's settlement; an allocation bound to another request fails the cancellation with `vault-allocation-mismatch` (`test_vault_cancel_uncommittedFundingInOneStep`, `test_vault_allocationMismatch_cancel`). A committed allocation cannot be withdrawn before its `settlementDeadline` and is withdrawn after it (`test_vault_cancel_committedFundingAfterDeadline`, `test_withdrawAllocation_committedAtDeadlineBoundary`).

### 4.3 Share registry (templates in `cvx-vault-v1`)

The share registry implements, for the share instrument, every V2 interface needed for holdings, transfer, allocation, settlement and events (D-07), and meets every MUST of the Splice 0.8.4 Token Standard V2 that applies to a registry. Mint and burn legs use `cip-112/mint` and `cip-112/burn` ([CIP-0112, section 4.3.2.1](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L622-L625)). `docs/REGISTRY-MUSTS.md` lists each requirement, where it is implemented and the test that proves it. The templates are in `Cayvox.VaultV1.Internal.ShareRegistry`; clients use them through the Splice V2 interfaces.

The share instrument is `InstrumentId {admin = operator, id = vaultId}`; the operator is the instrument admin.

| Template | Signatories | Observers | Implements | Role |
|---|---|---|---|---|
| `ShareRules` | `admin` | none; disclosed to its users | `AllocationFactory`, `SettlementFactory`, `TransferFactory` | The factories of one share instrument |
| `ShareHolding` | `admin`, the owner | the account's provider; while locked, the parties that act on the lock | `Holding` | Shares of one regular account |
| `ShareAllocation` | `admin`, the authorizer's owner (none for a special account) | the executors, the authorizer's provider | `Allocation` | One authorizer's approval of its leg sides in one settlement |
| `ShareTransferInstruction` | `admin`, the sender's owner | the receiver's owner and provider, the sender's provider | `TransferInstruction` | A pending transfer |
| `ShareEventLog` | `admin`, the account owner | the account's provider | `EventLog` | One holdings-change event, consumed by it |

- **Supply** (T-13). A `ShareHolding` needs the authority of the admin and of an owner who is not the admin. Shares are created and destroyed only by `Allocation_Settle`, which needs the admin's authority: it credits the allocation's net amount to its authorizer whatever the leg's other side is. In a settlement that settles both sides of every leg, supply grows only by legs from `cip-112/mint` and shrinks only by legs to `cip-112/burn`; the admin, as executor, can also settle one side of a leg alone, which changes the supply by that side (I-02 detects it, as for T-13; `test_hazard_t21_operatorSettlesInputAlone`). Every other choice moves, locks or unlocks existing shares. Only the admin allocates for the special accounts; a mint account only sends and a burn account only receives.
- **Allocations.** `AllocationFactory_Allocate` creates the allocation directly (`AllocationInstructionResult_Completed`). A net send locks the needed amount in one holding locked by the admin, observed by the executors; change is returned. Settlement is single-iteration: `nextIterationFunding` and extra leg sides are rejected (D-07). Allocations never expire, and a committed allocation must carry a `settlementDeadline`, so that its authorizer can withdraw it once the deadline has passed ([Splice `AllocationV2.daml:108-112`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L108-L112), [`:124-135`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L124-L135); `test_allocate_rejectsCommittedWithoutDeadline`). Settle: the admin with the executors, before `settlementDeadline`. Cancel: the executors. Withdraw: the authorizer's principal or provider; a committed allocation only after its deadline.
- **Batch settlement.** `SettlementFactory_SettleBatch` is controlled by the settlement's executors. It reads each allocation with a typed fetch of `ShareAllocation` of this instrument (T-06), requires at least one leg, legs of this instrument, the same settlement, and exactly the authorizations the legs need, and settles the allocations in the order given.
- **Transfers.** `TransferFactory_Transfer` is controlled by its actors: the sender's owner, optionally with the sender's provider and the receiver's parties. With the receiver's owner among the actors it completes at once; otherwise it locks the amount and creates a `ShareTransferInstruction`, which the receiver's owner accepts before `executeBefore`, the receiver's parties reject, or the sender's parties withdraw. Input holdings are read with a typed fetch of `ShareHolding` of the sender's account (T-06).
- **Events** (§8). Every create or archive of a `ShareHolding` is reported in exactly one `EventLog_HoldingsChange` of its account ([CIP-0112, line 1246](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L1246)), through a `ShareEventLog` created and consumed inside the same registry operation (T-12).
- **Bounds** (T-16). Every text is at most 256 characters; metadata at most 16 entries with values of at most 1,024 characters; at most 25 leg sides per allocation, 10 executors per settlement and 50 inputs per transfer; lock observers at most 12. Choice arguments that become contract fields are checked first, with `registry-field-too-large`.
- **Failures** (§7). Each check fails with a `registry-...` identifier, category `InvalidGivenCurrentSystemStateOther` (D-13).

## 5. Operations

Each operation lists preconditions in the order they are checked. The first failing check determines the error; the `test_order_*` tests in `VaultOrder.daml` pin the order. Error identifiers are in §7.

### 5.1 Create

- Operator creates `VaultState` with `A = 0`, `S = 0`, `paused = False`, a `decimalsOffset` from 0 to `KMAX = 10` (0 by default), and the share registry contracts.
- Fails on any `ensure` violation.

### 5.2 Request a deposit or a redemption

1. The requester creates the request (§4.2). One submission.
2. Optionally, in a second submission, the requester funds it: `AllocationFactory_Allocate` at the input registry, with `actors = [requester]`, `settlement` as in §4.2, the sender side of the input leg for exactly `amount`, `settlementDeadline = Some deadline`, and `committed = True`. The registry locks the input until the deadline. The request then has `funded = True` (`test_interop_fundedDeposit`, `test_vault_depositRedeem_permissionedFunded`). Without this step, the input is allocated at execution through `Request_Allocate` (`test_interop_depositMintsShares`), and in Permissioned mode the requester hands the operator the disclosures of its input holdings (`test_hazard_t21_executionTimeFunding_holdingsHanded`).

No vault state is touched. The price is not fixed at request time; `minOut` protects the requester.

The funding allocation must come from the registry's V2 `AllocationFactory`, the factory recorded in `VaultState`: the template identity check of §5.3 compares its template with the allocation the vault creates there, so an allocation of another template of the same registry, such as TestTokenV2's `TokenAllocationV1` or Amulet's `AmuletAllocation` from a V1 flow, fails with `vault-allocation-mismatch`.

### 5.3 Execute deposits: `Vault_ExecuteDeposits`

A consuming choice on `VaultState`, postconsuming so that `Request_Allocate` can fetch the executing vault (§4.2 check 1). Arguments: `executor : Party`; per request, the request's contract ID, its funding allocation (funded requests), its input holdings (unfunded requests); and the choice contexts of both registries. Controller: `executor`.

Checks for the batch, in order:

1. `executor == operator`, else, in Permissioned mode, `vault-unauthorized-executor` without reading the requests. In Permissionless mode, every request must have `requester == executor`, else `vault-unauthorized-executor`. A party that names the operator as executor fails with `AuthorizationError` (`test_vault_unauthorizedExecutor_permissioned`, `test_vault_unauthorizedExecutor_permissionless`). Without this check, a party given the disclosures could execute another requester's request with the operator's authority (T-17; `test_hazard_t17_bobExecutesAlicesRequest`).
2. `not paused`: else `vault-paused`.
3. The batch holds between 1 and 25 requests: else `vault-batch-size` (`test_vault_batch_25AndNot26`). The bound limits the size of one execution's transaction (D-16).
4. No request appears twice: else `vault-duplicate-request`.

Checks 2 to 4 need no request content. When the executor is the operator, check 1 cannot fail after the requests are read, so checks 2 to 4 run before any request is read: an archived or undisclosed request cannot hide them behind a contract error (`test_order_batchChecksBeforeRead`).

Checks for each request, in list order:

5. The request's `operator` and `vaultId` equal this vault's: else `vault-wrong-vault` (`test_hazard_t04_secondVaultOfTheOperator`).
6. `isLedgerTimeLT deadline`: else `vault-request-expired`. This is the predicate of the standard library's `assertWithinDeadline` ([`DA/Assert.daml:64-74`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/damlc/daml-stdlib-src/DA/Assert.daml#L64-L74), daml SDK 3.4.11), which Splice's TestTokenV2 uses for the settlement deadline ([`TestTokenV2/Allocation.daml:416-419`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/examples/splice-test-token-v2/daml/Splice/Testing/Tokens/TestTokenV2/Allocation.daml#L416-L419)), so both trip at the same instant and the vault's fires first (`test_vault_requestExpired_atTheDeadline`, `test_hazard_t19_theDeadlineInstant`).
7. For a funded request, its funding allocation, read through the V2 `Allocation` interface, must have: `settlement` equal to the request's (§4.2); `authorizer == payAccount`; `transferLegSides` equal to the sender side of the input leg; `settlementDeadline == Some deadline`; and `nextIterationFunding == None`. Else `vault-allocation-mismatch` (`test_vault_allocationMismatch_fundingPresence`, `test_vault_allocationMismatch_fundingFields`, `test_vault_allocationMismatch_registryAndIteration`). A funding allocation that is no longer active, for example withdrawn by the requester, fails at its `fetch` with the participant's contract error instead, as a request that is no longer active does (T-17).
8. New `A` within the asset bound, `A + amount + VA <= AMAX(k)`, evaluated as `amount <= AMAX(k) - VA - A` so that it cannot overflow (`docs/MATH.md` §7): else `vault-capacity-exceeded`. This check precedes the conversion: within the asset bound `previewDeposit` cannot overflow (`docs/MATH.md` §7, K-05), so a deposit beyond the vault's capacity fails with this identifier and never with `math-overflow`.
9. `shares = previewDeposit amount` against the current running state.
10. `shares > 0`: else `vault-zero-shares`.
11. `shares >= minOut`: else `vault-slippage` (also enforced by `Request_Allocate`, §4.2 check 4).
12. New `S` within the share bound, `S + shares + VS <= 10^k * AMAX(k)`, evaluated as `shares <= 10^k * AMAX(k) - VS - S`: else `vault-capacity-exceeded`. Step 8 implies it (`docs/MATH.md` §7, K-06), and the conversion's own bound check (step 9) fails first with the same identifier, so no input reaches this check and no test can fail it: it is kept as defence in depth, and a mutant that removes it is equivalent.

Effects for each request, in the same transaction. They run in three phases, so that every check of the vault, on every request and every allocation, completes before any settlement starts: first checks 5 to 12 for every request in list order; then, for every request in list order, `Request_Allocate`, the vault's own allocations and the template identity check below; then the two settlements of every request in list order (`test_order_checksBeforeAllocations`, `test_order_allocationsBeforeSettlements`).

- `Request_Allocate` on the request, with this vault and the output leg for `shares` (§4.2). It creates the requester's receipt allocation and, for an unfunded request, its funding allocation, and consumes the request.
- The vault creates its own allocations with `actors = [operator]` and the request's settlement: at the underlying registry, the receiver side of the input leg for `vaultAccount`; at the share registry, the `cip-112/mint` sender side of the output leg.
- **Template identity of a funded request's allocation** (T-06). The funding allocation was created by the requester, so the vault cannot know from its view alone that the registry created it. A contract of any template can implement `Allocation` and claim any view. The underlying registry's batch settlement may read allocations through the interface and exercise their `Allocation_Settle` with `actors = admin :: executors` (Splice [`Utils/Internal/Allocations.daml:384-394`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L384-L394), [`:429-432`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L429-L432)), which would run that contract's code with the admin's and the operator's authority. Before any settlement, the funding allocation's template must therefore equal the template of the allocation the vault has just created at the same registry, through the factory recorded in `VaultState`. The comparison uses `interfaceTypeRep`, whose result the Daml-LF specification states (`interface_typerep`, rule `EvExpInterfaceTypeRep`: [daml SDK 3.4.11 `daml-lf-2.rst:2499-2502`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L2499-L2502); the same rule in [Canton `v3.5.17` `daml-lf-2.rst:2489-2492`](https://github.com/digital-asset/canton/blob/v3.5.17/community/daml-lf/spec/daml-lf-2.rst#L2489-L2492)). Else `vault-allocation-mismatch` (`test_hazard_t06_forgedFundingAllocation`). A contract of the registry's own template can be created only with the registry's authority; whether it is bound to this request is check 7.
- One `SettlementFactory_SettleBatch` at the underlying registry and one at the share registry, each with `actors = [operator]` (`test_interop_depositMintsShares`).
- Running state: `A += amount`, `S += shares` (`test_order_batchRunningState`).

After the batch, the successor `VaultState` is created. The result lists the shares minted per request and returns the successor's contract ID.

**Batch behaviour.** Each request has its own settlement, so a batch of N requests performs 2N `SettleBatch` exercises of one leg and two allocations each, well inside the V2 per-settlement limits ([Splice `allocation-v2.yaml:21-29`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/openapi/allocation-v2.yaml#L21-L29); `test_interop_batchOfThree`). The whole batch is one transaction: a failure in any request rolls back every request and the vault state (`test_interop_atomicity`).

**Who submits and who discloses.** In Permissioned mode the operator submits, with the disclosures listed in §2. In Permissionless mode a requester submits its own requests, with the disclosures listed in §2; the operator's authority comes from its signature on `VaultState`, and its participant confirms (`test_vault_depositRedeem_permissionlessUnfunded`, `test_vault_depositRedeem_permissionlessFunded`).

### 5.4 Execute redemptions: `Vault_ExecuteRedeems`

Same structure as §5.3 (`test_interop_redemptionBurnsShares`), with these differences:

- Check 2 does not apply: redemptions run while paused (D-14).
- Step 8 does not apply: a redemption lowers `A` and `S`.
- Step 9 computes `assets = previewRedeem amount`.
- Step 10 fails with `vault-zero-assets` when `assets == 0`.
- Step 12 is replaced by `amount <= S` and `assets <= A`: else `vault-insufficient-assets`. `amount <= S` fails only when shares exist outside `S` (T-13; `test_hazard_r25_operatorMintsOutsideTheVault`); without it, an amount just above `S` with `k > 0` can pass `assets <= A` and leave a negative `S`, which the successor's `ensure` refuses with a precondition failure instead of a vault identifier (`test_vault_insufficientAssets_amountAboveSupply`). `previewRedeem` with `amount <= S` cannot exceed `A` (`docs/MATH.md` §7, K-02); the check guards the invariant and has a fixture test (`test_vault_insufficientAssets`).
- The requester's input goes to `cip-112/burn` at the share registry. The vault creates the `cip-112/burn` receiver side there, and at the underlying registry the sender side of the output leg for `vaultAccount`. That allocation is funded by the vault-account holdings the executor names for the request (`vaultInputs`), followed by the holdings of the vault's instrument that the underlying registry returned to the vault account from the batch's previous redemption allocation (`authorizerChangeCids`, keyed by `instrumentId.id`; the first redemption has none). A registry MUST return there the change and every input it did not use (Splice [`AllocationInstructionV2.daml:163-167`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-instruction-v2/daml/Splice/Api/Token/AllocationInstructionV2.daml#L163-L167), [`:199-203`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-instruction-v2/daml/Splice/Api/Token/AllocationInstructionV2.daml#L199-L203)); an allocation consumes its input holdings ([`TestTokenV2/Allocation.daml:300-302`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/examples/splice-test-token-v2/daml/Splice/Testing/Tokens/TestTokenV2/Allocation.daml#L300-L302), [`:331-334`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/examples/splice-test-token-v2/daml/Splice/Testing/Tokens/TestTokenV2/Allocation.daml#L331-L334)). So one holding that covers a batch pays every redemption of it when named once, by the first (`test_order_redemptionsChainChange`). A registry that archives every input, as TestTokenV2 does, fails the execution when a holding is named twice (`test_order_redemptionsNeedSeparateVaultHoldings`); one that returns an unused input unarchived would accept it, but then only as change, which the next redemption spends. In Permissionless mode the operator discloses the named holdings to the requester (`test_order_redemptionsChainChange_permissionless`); the change exists only inside the transaction and needs no disclosure.

Effects: `A -= assets`, `S -= amount`.

### 5.5 `Vault_AddAssets`

Controller `operator`. Arguments: `amount`; the account `source` that sends it; the allocation at the underlying registry that brings `amount` of underlying from `source` into `vaultAccount`, created beforehand by `source`'s owner; and the underlying registry's choice context. The allocation's settlement is `SettlementInfo {executors = [operator], id = <vaultId> <> "/add-assets", cid = Some <this VaultState's contract ID>, meta = empty}`: the contract ID makes it unique, because every vault choice consumes the vault state. Any vault choice in between, including a Permissionless execution, makes the allocation useless, so the source allocates uncommitted and in the same transaction as `Vault_AddAssets` or just before it; a committed allocation stays locked until its deadline.

Checks, in order: `not paused` (else `vault-paused`); `amount > 0` (else `vault-invalid-amount`); `S > 0` (else `vault-no-shares`, because assets added to a vault with no shares belong to no holder); the asset bound, `A + amount + VA <= AMAX(k)`, evaluated as `amount <= AMAX(k) - VA - A` (else `vault-capacity-exceeded`); `source != vaultAccount` (else `vault-allocation-mismatch`: a leg from the vault account to itself brings nothing into custody, and `A` would grow without underlying; `test_vault_addAssets_refusesVaultAccountSource`); the allocation, read through the V2 interface, has that settlement, `admin == asset.admin`, `authorizer == source`, `transferLegSides` equal to the sender side of the leg from `source` to `vaultAccount` for `amount`, and `nextIterationFunding == None` (else `vault-allocation-mismatch`). Adding assets leaves `S` unchanged, so the share bound keeps holding. The order is pinned by `test_order_addAssets`.

Effect: the vault creates the receiver side of that leg for `vaultAccount` with `actors = [operator]`; the allocation's template must equal it (the template identity check of §5.3, else `vault-allocation-mismatch`; `test_hazard_t06_forgedAddAssetsAllocation`); one `SettlementFactory_SettleBatch` at the underlying registry moves the underlying into `vaultAccount`; `A += amount`; no shares minted; the successor `VaultState` is created.

### 5.6 `Vault_Pause` and `Vault_Unpause`

Controller `operator`. Set `paused`. Pausing a paused vault and unpausing an active vault fail (`vault-already-paused`, `vault-not-paused`), following the Pausable model in canton-contracts, whose pausing choice requires the contract to be unpaused and whose unpausing choice requires it to be paused ([`PausableV1.daml:40-61`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/packages/security/pausable-v1/daml/OpenZeppelin/PausableV1.daml#L40-L61)).

### 5.7 Pure functions

Exported from `cvx-vault-v1`:

- `convertToShares`, `convertToAssets`
- `previewDeposit`, `previewMint`, `previewWithdraw`, `previewRedeem`

Each takes a `VaultView` (`cvx-api-vault-v1`) and an amount, and follows `docs/MATH.md` §7, including its failures: `vault-capacity-exceeded` for a view outside the bounds of that section or an amount that would take the vault past the asset bound, and the failures of `mulDiv`. They are exported by the module `Cayvox.VaultV1.Conversion`.

### 5.8 Cancel a request

The requester exercises `Request_Cancel` (§4.2). One transaction archives the request and withdraws its uncommitted allocations (`test_vault_cancel_uncommittedFundingInOneStep`). A request whose funding allocation is committed can be archived at any time; its allocation can be withdrawn only after `settlementDeadline` (`test_vault_cancel_committedFundingAfterDeadline`), and until then the operator, the settlement's executor, can still settle it (`docs/SECURITY.md` T-21). A request executed or cancelled cannot execute again (`test_vault_duplicateRequest`, `test_vault_requesterArchivesRequests`).

## 6. Invariants

Checked after every step of every test sequence (Q-08).

| ID | Invariant |
|---|---|
| I-01 | `totalAssets` equals the sum of underlying holdings in `vaultAccount` that entered through vault choices, minus those that left through them |
| I-02 | `totalShares` equals the sum of all share holdings |
| I-03 | Shares are minted only in the transaction that receives the corresponding assets, and burned only in the transaction that releases the corresponding assets |
| I-04 | Every withdrawal of value creates its outflow in the same transaction |
| I-05 | A request executes at most once, and only against the vault it names |
| I-06 | No deposit and no asset addition executes while paused |
| I-07 | Identity fields of `VaultState` never change across successors |
| I-08 | `0 <= A`, `0 <= S`, and the asset and share bounds of `docs/MATH.md` §7: `A + VA <= AMAX(k)` and `S + VS <= 10^k * AMAX(k)` |

## 7. Errors

All failures use `failWithStatus` through the internal constructor (D-13). The full identifier is `<domain>/<name>`.

| Name | Raised by |
|---|---|
| `vault-unauthorized-executor` | §5.3, §5.4 |
| `vault-paused` | §5.3, §5.5 |
| `vault-already-paused`, `vault-not-paused` | §5.6 |
| `vault-batch-size`, `vault-duplicate-request` | §5.3, §5.4 |
| `vault-wrong-vault` | §5.3, §5.4 |
| `vault-request-expired` | §5.3, §5.4 |
| `vault-allocation-mismatch` | §4.2 (`Request_Allocate`, `Request_Cancel`), §5.3, §5.4, §5.5 |
| `vault-zero-shares`, `vault-zero-assets` | §5.3, §5.4 |
| `vault-slippage` | §5.3, §5.4 |
| `vault-capacity-exceeded` | §5.3, §5.5, §5.7 |
| `vault-insufficient-assets` | §5.4 |
| `vault-no-shares` | §5.5 |
| `vault-invalid-amount` | §4.2 `ensure`, §5.5 |
| `math-negative-operand`, `math-non-positive-divisor`, `math-overflow` | `docs/MATH.md` §4 |
| `registry-wrong-admin`, `registry-wrong-instrument` | §4.3: an instrument, allocation or event of another admin or instrument |
| `registry-unauthorized-actors` | §4.3: actors outside the allowed groups; an event whose observers omit the account parties |
| `registry-invalid-account`, `registry-invalid-amount` | §4.3: an account that is not regular or an allowed special account; a non-positive amount |
| `registry-iterated-settlement` | §4.3: next-iteration funding or extra leg sides |
| `registry-not-yet-requested`, `registry-deadline-passed` | §4.3: `requestedAt` in the future; `executeBefore` or `settlementDeadline` reached |
| `registry-invalid-input-holding`, `registry-insufficient-funds` | §4.3: an input holding of another account or instrument, or locked; inputs below the amount |
| `registry-no-transfer-legs`, `registry-duplicate-leg` | §4.3: no leg or leg side; a leg or leg side repeated |
| `registry-settlement-mismatch`, `registry-missing-authorization`, `registry-superfluous-authorization` | §4.3, batch settlement |
| `registry-committed-allocation` | §4.3: withdrawal of a committed allocation before its deadline |
| `registry-committed-without-deadline` | §4.3: a committed allocation without a settlement deadline |
| `registry-field-too-large` | §4.3, bounds |

Authorization failures that Canton raises before any guard runs are asserted with their exact shape by the test helpers in `test/shared/Cayvox/Testing/Assert.daml` (`Authorization`, `ContractUnavailable`, `WrongTemplate`, `StaleDisclosure`).

## 8. Observability

- **Execution results.** An execution returns the successor's contract ID and, per request in batch order, its output: the shares minted for a deposit, the underlying paid for a redemption. The input each request moved is its `amount` (`ExecResult`).
- **Share registry events.** The share registry implements `EventLog` and, as instrument admin, exercises `EventLog_HoldingsChange` so that the events explain every change to the share holdings of every regular account and every incoming and outgoing transfer ([Splice `TransferEventsV2.daml:57-60`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-transfer-events-v2/daml/Splice/Api/Token/TransferEventsV2.daml#L57-L60)). For each change:
  - `admin` is the operator; `account` is the regular account.
  - `inputHoldingCids` were archived in the same transaction and belong to `account`; `outputHoldingCids` are the new holdings.
  - `transferLegSides` have net balance changes that match the change in holdings, with unique leg identifiers.
  - `observers` include at least the account parties.
  - The choice is controlled by the admin ([`TransferEventsV2.daml:54-106`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-transfer-events-v2/daml/Splice/Api/Token/TransferEventsV2.daml#L54-L106)).

  A settled allocation of a regular account produces one event with the allocation's leg sides, as Splice's `logAllocationSettlement` does ([`Utils/Internal/Events.daml:131-147`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Events.daml#L131-L147)). A mint appears as the receiver side of a leg whose other side is `cip-112/mint`; a burn as the sender side of a leg to `cip-112/burn`. The special accounts have no owner and receive no event, as in Splice ([`Events.daml:87`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Events.daml#L87); `holdingsChangeIsLogged`, compared with Splice by `test_diff_logHoldingsChange`). This is the shape Amulet's own mint and burn events use (`logMint`, `logBurn`, [`Events.daml:90-128`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Events.daml#L90-L128); called from [`splice-amulet/daml/Splice/Amulet.daml:704`](https://github.com/canton-network/splice/blob/0.8.4/daml/splice-amulet/daml/Splice/Amulet.daml#L704) and [`:710`](https://github.com/canton-network/splice/blob/0.8.4/daml/splice-amulet/daml/Splice/Amulet.daml#L710)). `test_events_explainEveryHoldingChange` checks that every registry operation reports each holding it creates or archives in exactly one event.
- **Reconstruction.** An auditor reconstructs each vault operation from:
  - the execution result;
  - the share registry's events (minted and burned shares per account);
  - the underlying registry's events for `vaultAccount` (underlying in and out).

  Together these reconcile I-01 and I-02. A movement of `vaultAccount` holdings outside vault choices appears in the underlying registry's events without a matching execution (`test_hazard_t10_operatorMovesCustody`).
- **Custody.** Custody, the vault account's underlying, is at least `totalAssets`; it exceeds it by exactly what entered the account outside vault choices (`test_hazard_v05_donationChangesNothing`). A shortfall against that is custody moved out of the vault account outside vault choices (T-10; `test_hazard_t10_operatorMovesCustody`).

## 9. Rationale for selected rules

The rules below follow from reasons that the sections stating them give only in part. Each is listed with its reason and the tests that show it; mutant identifiers refer to `scripts/mutate-registry.py`.

| # | Rule | Reason | Tests |
|---|---|---|---|
| 1 | §5.3, template identity of a funded request's allocation; §5.5, the same for an asset addition; `docs/SECURITY.md` T-06 | The vault reads a requester's allocation through the `Allocation` interface, and any template can implement it with any view. Splice's default batch settlement exercises allocations through the interface with `actors = admin :: executors` ([`Utils/Internal/Allocations.daml:384-394`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L384-L394)), so a forged allocation's code would run with the admin's and the operator's authority | `test_hazard_t06_forgedFundingAllocation`, `test_hazard_t06_forgedAddAssetsAllocation`; mutants V044, V045, V084 |
| 2 | §5.3, three phases: every request's checks, then every delegation, vault allocation and template check, then every settlement | Every vault check runs before any settlement, so that each fails with the vault's own identifier; the template check of rule 1 needs allocations that exist only after delegation | `test_order_checksBeforeAllocations`, `test_order_allocationsBeforeSettlements`; mutants V070, V071 |
| 3 | §5.5, `Vault_AddAssets`: its arguments, the settlement `<vaultId>/add-assets` bound by the `VaultState` contract ID, the check order, and the template check | The underlying reaches the vault account only through a settled allocation, and the contract ID makes the settlement unique per vault state | `test_vault_addAssets_raisesPriceAndRefusesEmptyVault`, `test_vault_invalidAmount_addAssets`, `test_vault_allocationMismatch_addAssets`, `test_vault_capacityExceeded_addAssets`, `test_order_addAssets`, `test_hazard_t06_forgedAddAssetsAllocation`; mutants V080 to V089 |
| 4 | §4.2, `Request_Cancel` refuses an allocation bound to another request with `vault-allocation-mismatch` | Without it, a cancellation could withdraw an allocation of another request of the same requester | `test_vault_allocationMismatch_cancel`; mutant V100 |
| 5 | §4.2, the request choices are named per template: `DepositRequest_Allocate`, `DepositRequest_Cancel`, `RedeemRequest_Allocate`, `RedeemRequest_Cancel` | A choice declares a record type of its name, so two templates of one module cannot both declare `Request_Allocate` | Every choice is exercised (Q-03); `test_vault_delegationChecks`, `test_vault_delegationChecks_redeem`, `test_vault_delegationOutsideAnExecution`, the cancellation tests of `VaultScenarios` |
| 6 | §5.4, a vault-account holding is named for at most one redemption of a batch | An allocation consumes its input holdings ([Splice `TestTokenV2/Allocation.daml:300-302`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/examples/splice-test-token-v2/daml/Splice/Testing/Tokens/TestTokenV2/Allocation.daml#L300-L302)), so a holding named by two redemptions is no longer active for the second, and the batch fails as a whole | `test_order_redemptionsNeedSeparateVaultHoldings`, `test_order_batchRunningState`, `test_order_allocationsBeforeSettlements`; the redemption batches of the Q-08 sequences |
| 7 | §5.4, a redemption's vault allocation is funded by its named holdings followed by the change the batch's previous redemption allocation returned for the vault's instrument | Rule 6 alone would make each redemption of a batch need its own vault holding, which an account of few, large holdings cannot give. The token standard returns change in `authorizerChangeCids` for this use: "Can be used by callers to batch creating or updating multiple allocation instructions in a single Daml transaction" ([Splice `AllocationInstructionV2.daml:199-203`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-instruction-v2/daml/Splice/Api/Token/AllocationInstructionV2.daml#L199-L203)). The legs, amounts, settlements and actors are unchanged, so no invariant of §6 changes, and the change holdings are the vault account's own, created by the vault's recorded registry inside the same vault choice and spent by the vault's own allocation with the operator as actor, as the named holdings are: no new authority path | `test_order_redemptionsChainChange`, `test_order_redemptionsChainChange_permissionless`, `test_order_redemptionsNeedSeparateVaultHoldings`; mutants V049, V123 |
| 8 | §5.5, `Vault_AddAssets` refuses `source == vaultAccount` with `vault-allocation-mismatch` | A leg from the vault account to itself settles to nothing, so `A` would grow by `amount` with no underlying entering custody, breaking I-01 and the custody relation of §8. An operator recognising underlying that reached the vault account outside vault choices would call the choice this way | `test_vault_addAssets_refusesVaultAccountSource`; mutant V124 |
| 9 | No on-ledger check that each recorded factory is signed by its instrument's admin. The factories are configuration the operator records; recording only its registries' own factories is an operator duty (`docs/SECURITY.md` T-20) | Such a check would fetch the factory, and "`fetch` is authorized if and only if the authorizing parties contain at least one stakeholder of the fetched contract ID" ([daml SDK 3.4.11 `daml-lf-2.rst:851-854`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L851-L854)); the operator is not a stakeholder of the underlying registry's factory, so the check would fail every execution. The token standard places the same safety on package vetting: exercising a factory "acquired from an untrusted source" is safe "*provided* all vetted Daml packages only contain interface implementations that check the expected admin party" ([Splice `AllocationInstructionV1.daml:106-110`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-instruction-v1/daml/Splice/Api/Token/AllocationInstructionV1.daml#L106-L110)) | `test_hazard_b07_forgedFactory`: a forged factory recorded by mistake mints shares with the operator's authority on the in-memory ledger, which vets every package, and reconciliation reports it (I-02) |
| 10 | §5.3, checks 2 to 4 run before the requests are read when the operator executes | Otherwise an archived or undisclosed request would hide `vault-paused`, `vault-batch-size` and `vault-duplicate-request` behind a contract error, against the check order of §5.3 | `test_order_batchChecksBeforeRead`; mutants V125, V006, V007, V010, V011, V020, V021, V023 to V027 |
| 11 | §4.1, `vaultId` of at most 245 characters | Every settlement identifier is built from `vaultId`, the longest being `<vaultId>/add-assets`, and the share registry bounds settlement identifiers at 256: a vault with a longer identifier could never execute | `test_vaultState_identityAndTexts`, `test_vaultState_longestIdentifierExecutes`; mutants V116, V117 |
| 12 | §5.4, a redemption also needs `amount <= S`, else `vault-insufficient-assets` | With shares outside `S` and `k > 0`, an amount just above `S` would pass `assets <= A` and fail at the successor's `ensure` with a precondition failure instead of a vault identifier | `test_vault_insufficientAssets_amountAboveSupply`, `test_vault_insufficientAssets`; mutants V126, V065, V067; V064 is equivalent |
