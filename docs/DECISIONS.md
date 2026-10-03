# Decisions

Each decision records the question it answers, the choice, the evidence, the alternatives considered, how costly it is to reverse, and whether it raises an open question for the library maintainers. A decision marked with an open question is a proposed default; the question is collected in the last section, with the evidence given here.

Reversal cost: **Low** means a local change; **Medium** means several modules change; **High** means a frozen API or a package lineage changes.

Upstream sources are cited at pinned revisions: OpenZeppelin/canton-contracts at `aeca01d043311d8ccc8ab7cda4d7c16e682429fa`, OpenZeppelin/canton-specs at `fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c`, canton-network/splice at tag `0.8.4`, canton-foundation/cips at `ef039e9a6901aeda7755d430c13d4b1ace311f60`, the funding proposal in canton-foundation/canton-dev-fund at `71c06c8b5f190d9b7542174ef52b901510730f92`, and the Daml SDK 3.4.11 sources at digital-asset/daml `de513339189206e5bcae77b2cfc68afda9b05ef5`.

---

## D-01 · The Vault is an ERC-4626 share vault over one underlying instrument

- **Question:** What is the library Vault: a tokenized share vault, a per-borrower collateral position, or a component that serves both? Issue [#28](https://github.com/OpenZeppelin/canton-contracts/issues/28) describes it as a "Core lending primitive: permissioned and permissionless, multi-asset, multi-chain vaults."
- **Decision:** The library Vault holds a single underlying Token Standard instrument and issues shares that represent a pro-rata claim on it, with ERC-4626 conversion and rounding semantics.
- **Evidence:**
  - The funding proposal describes the lending protocol as "built around vaults as the core primitive" and points to "ERC-4626 on Ethereum, SEP-56 on Stellar, and equivalent implementations on Starknet" ([proposal, line 121](https://github.com/canton-foundation/canton-dev-fund/blob/71c06c8b5f190d9b7542174ef52b901510730f92/proposals/2026-04-OpenZeppelin-canton-ecosystem-stack.md#L121)). The OpenZeppelin vaults on those chains are ERC-4626 share vaults; the Stellar one "implements the ERC-4626 tokenized vault standard" ([`packages/tokens/src/vault/mod.rs:13`](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/mod.rs#L13)).
  - In the lending reference architecture, the borrower position (CDP) is the venue's own `Position` contract ([`lending.md:11-13`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L11-L13), [`:107`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L107)).
  - The pooled-share structure that lending anticipates is a treasury opened "to multiple independent depositors" ([`lending.md:699`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L699)), which is a share vault.
- **Alternatives:** a CDP library component; a component that serves both.
- **Reversal cost:** Medium. `cvx-vault-math-v1` and the share token registry are reusable under any answer.
- **Open question for maintainers:** yes: is a share vault the intended component?

## D-02 · Multi-asset means one vault per instrument; multi-chain is outside v1

- **Question:** What do "multi-asset" and "multi-chain" mean for the Vault: one vault holding a basket, or one vault per instrument; cross-synchronizer operation on Canton, or external chains?
- **Decision:** A vault holds exactly one underlying instrument. Support for many instruments comes from many vault instances sharing one codebase. Cross-synchronizer and cross-chain operation is outside v1, with the extension point documented.
- **Evidence:**
  - "the input contracts (i.e., UTXOs) referenced by a Daml transaction must all be assigned to the same synchronizer" ([`cip-0056.md:252-253`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0056/cip-0056.md#L252-L253)).
  - The lending architecture "assumes a single synchronizer" ([`lending.md:79`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L79)).
  - The Standardized Messaging Gateway is a Milestone 4 deliverable ([proposal, lines 369-385](https://github.com/canton-foundation/canton-dev-fund/blob/71c06c8b5f190d9b7542174ef52b901510730f92/proposals/2026-04-OpenZeppelin-canton-ecosystem-stack.md#L369-L385)).
- **Alternatives:** a basket vault with a multi-instrument share price (needs a pricing source, which is an oracle decision outside the library); cross-chain operation through the Messaging Gateway once it exists.
- **Reversal cost:** Medium for baskets; Low for adding cross-chain later as a separate component.
- **Open question for maintainers:** yes: does one vault per instrument meet "multi-asset", and may multi-chain wait for the Messaging Gateway?

## D-03 · Token Standard V2, consumed from the DARs Splice ships at tag 0.8.4

- **Question:** Which Token Standard does the Vault target (V1, V2 or both), and from which artifact source?
- **Decision:** Underlying assets are accessed only through CIP-0112 V2 interfaces. The API DARs are the files in `daml/dars/` of canton-network/splice at tag `0.8.4`, pinned by main package ID in `dars/token-standard-pins.txt` and recorded with their provenance in `dars/manifest.yaml`. `scripts/check-token-dars.sh` (gate Q-16) recomputes and checks every ID.
- **Evidence:**
  - Splice ships the V2 API DARs as files in [`daml/dars/`](https://github.com/canton-network/splice/tree/0.8.4/daml/dars) at tag `0.8.4`.
  - The lending architecture moves assets through the V2 interfaces ([`lending.md:201`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L201)).
- **Consequence:** `dars/vendor/` holds only the Splice DARs that a package of this repository uses (`ARCHITECTURE.md`, section 3). Adding another shipped DAR is one manifest entry, checked by Q-16.
- **Alternatives:** V1 only (CIP-0056 is Final, [`cip-0056.md:10-13`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0056/cip-0056.md#L10-L13)); both V1 and V2; V2 API packages from another build.
- **Risks:** CIP-0112 is Approved, not Final ([`cip-0112.md:9-12`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L9-L12)). "The V2 Daml APIs are ready for initial validation" ([`V2_VALIDATION.md:3`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/V2_VALIDATION.md#L3)), and SDK bumps have "changed their package hashes" ([`V2_VALIDATION.md:215-216`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/V2_VALIDATION.md#L215-L216)). The pin makes any future change visible; it does not prevent it.
- **Reversal cost:** High once released; Low before release.
- **Open question for maintainers:** yes: may library packages depend on the V2 DARs that Splice ships at tag 0.8.4? Fallback if V2 is not accepted before it is Final: V1 interfaces, with the same flows expressed through V1 allocation.

## D-04 · Deposits and redemptions settle as Delivery vs Mint and Delivery vs Burn

- **Question:** How does custody move: by direct transfer or by allocation and batch settlement? Are deposits and redemptions synchronous, or requests followed by an execution or a claim?
- **Decision:** A deposit is one settlement in which the depositor's underlying moves into the vault's account and shares are minted to the depositor. A redemption is one settlement in which the holder's shares are burned and underlying moves from the vault's account to the holder. Both use CIP-0112 allocations and complete in a single transaction. The requester initiates with a request contract and the settlement executes it (request, then execute; no separate claim step).
- **Evidence:**
  - CIP-0112 names "Delivery vs Mint" and "Delivery vs Burn" for "subscriptions or redemptions" ([`cip-0112.md:118`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L118)) and defines the `cip-112/mint` and `cip-112/burn` special accounts ([`cip-0112.md:622-627`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L622-L627)).
  - Splice 0.8.4 settles one batch with both a mint leg and a burn leg in its test `test_delivery_versus_burn_mint` ([`TestDeliveryVersusBurnMint.daml:164-172`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/examples/splice-test-token-v2-test/daml/Splice/Testing/Tokens/TestTokenV2/TestDeliveryVersusBurnMint.daml#L164-L172)).
  - The canton-specs promotion boundary asks for "a clear choice between atomic batch settlement and any supported direct path" ([`cip-0112-promotion-boundary.md:76`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/decisions/cip-0112-promotion-boundary.md#L76)).
  - Direct transfer needs each registry to complete a transfer in the same transaction; the lending venue verifies "instant direct transfer under account-owner authority before listing an instrument" ([`lending.md:547-553`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L547-L553)). Batch settlement of allocations is part of the V2 allocation API ([`AllocationV2.daml:380-434`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L380-L434)).
  - The vault's execution settles the underlying leg and the share leg with one `SettlementFactory_SettleBatch` per registry, in one transaction whose only root is the vault's choice (`test/vault-v1-test/daml/Cayvox/VaultV1Test/Interop.daml`: `test_interop_depositMintsShares`, `test_interop_redemptionBurnsShares`), and a batch in which one request fails rolls back as a whole (`test_interop_atomicity`).
  - Each allocation names its request in `SettlementInfo.cid`, and a settlement rejects allocations made for another settlement (`test/vault-v1-test/daml/Cayvox/VaultV1Test/Allocations.daml`: `test_settleBatch_rejectsOtherSettlement`).
  - A request fails from the instant ledger time reaches its deadline, before any settlement call (`test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultErrors.daml`: `test_vault_requestExpired_atTheDeadline`; `VaultHazards.daml`: `test_hazard_t19_theDeadlineInstant`).
  - The requester authorizes receiving an amount fixed only at execution through a consuming choice on her request, controlled by the operator and run inside the vault's execution (`docs/SPEC.md` §4.2; `test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultErrors.daml`: `test_vault_delegationChecks`).
- **Alternatives:** synchronous direct transfer (registry-dependent); request, then claimable, then claim in EIP-7540 style (an extra step with no benefit once settlement is atomic).
- **Consequence:**
  - Only exact-input operations are requests: `requestDeposit(assets)` and `requestRedeem(shares)`. Exact-output previews (`previewMint`, `previewWithdraw`) are provided as functions, because an allocation fixes its amount before execution ([`AllocationV2.daml:80-96`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/daml/Splice/Api/Token/AllocationV2.daml#L80-L96)).
  - The share registry implements `AllocationFactory` and `SettlementFactory` with `cip-112/mint` and `cip-112/burn` allocations, authorized by the vault as instrument admin (`docs/SPEC.md` §4.3).
  - The requester's receiving allocation is created at execution through the request. The requester's input is allocated either at request time (committed and locked until the deadline, two submissions) or at execution through the same choice (one submission, the request) (`docs/SPEC.md` §4.2, §5.2).
- **Reversal cost:** High.
- **Open question for maintainers:** yes: is allocation-based settlement with request, then execute, the intended flow, rather than direct transfer?

## D-05 · Two modes: Permissioned and Permissionless

- **Question:** How is "permissioned" enforced, and is "permissionless" the absence of that gate? Issue [#28](https://github.com/OpenZeppelin/canton-contracts/issues/28) asks for "permissioned and permissionless" vaults.
- **Decision:** A vault is created in one of two modes, fixed for its lifetime.
  - **Permissioned:** only the operator executes requests. The operator's admission policy decides who is served; on-ledger credential checks are wired by the consuming application.
  - **Permissionless:** any requester can execute their own request, using the vault's authority inside a vault choice. The operator's application need not act: the requester submits, and the operator's authority comes from its signature on the vault state, since "the signatories of the input contract and the actors of the action jointly authorize every consequence of the action" (https://docs.canton.network/overview/reference/ledger-model-detailed, Authorization context). The operator's participant must be online to confirm: Canton uses "a signatory-based confirmation policy: for each signatory of a contract involved in the transaction, the mediator requires confirmation from the participant nodes hosting that signatory", and "A single signatory whose threshold is not met … causes the entire transaction to abort" (https://docs.canton.network/overview/reference/smart-contract-consensus, Confirmation Policies and Aggregation Rule). The operator signs the vault state, so its participant confirms every execution. Both modes run the same deposit and redemption flows (`test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultScenarios.daml`: `test_vault_depositRedeem_permissionlessFunded`, `test_vault_depositRedeem_permissionlessUnfunded`), and in Permissionless mode a requester cannot execute another requester's request (`VaultHazards.daml`: `test_hazard_t17_bobExecutesAlicesRequest`).
- **Evidence:**
  - Consuming applications own party authorization: "A library package cannot establish these application-level assumptions by itself" (canton-contracts [`SECURITY.md:28-31`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/SECURITY.md#L28-L31)).
  - Credentials and Claims are a Milestone 3 library deliverable ([proposal, lines 325-341](https://github.com/canton-foundation/canton-dev-fund/blob/71c06c8b5f190d9b7542174ef52b901510730f92/proposals/2026-04-OpenZeppelin-canton-ecosystem-stack.md#L325-L341)). The vault therefore takes no dependency on a credential mechanism; the example `examples/vault-admission-v1` shows an on-ledger admission check wired by the application.
- **Alternatives:** a built-in allowlist in vault state (unbounded list fields are a daml-lint finding, [`README.md:19`](https://github.com/OpenZeppelin/daml-lint/blob/cba698832991f640f0e0d8a9e2bfb683717c6024/README.md#L19)); a dependency on the Scoped Authorization Grant (canton-contracts `packages/access/scoped-authorization-grant-v1`); attestation contracts.
- **Reversal cost:** Medium.
- **Open question for maintainers:** yes: is the operator's admission policy, with credential checks wired by the application, the intended meaning of "permissioned"?

## D-06 · Accounting is recorded, not derived from holdings

- **Question:** Is `totalAssets` recorded state or derived from holdings?
- **Decision:** The vault state records `totalAssets` and `totalShares`. They change only inside vault choices, in the same transaction as the matching holding movement. Holdings that reach the vault's account by any other path are not counted.
- **Evidence:**
  - Holdings are separate contracts, so a balance query is not an atomic on-ledger read. Lending uses the same model: `availableAmount + feesAccrued == treasury holding` "cannot drift" ([`lending.md:555-563`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L555-L563)).
  - ERC-4626 derives `totalAssets` from the token balance ([`ERC4626.sol:128-130`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L128-L130)), so a "donation" to the vault can inflate the price of a share ([`ERC4626.sol:20-28`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L20-L28)). Recorded accounting removes donation as a price lever (`test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultHazards.daml`: `test_hazard_v05_donationChangesNothing`).
- **Consequence:** yield is recognised explicitly by `Vault_AddAssets` (D-08).
- **Reversal cost:** High.
- **Open question for maintainers:** no. It follows from the ledger model; it is explained in the docs.

## D-07 · Shares are a CIP-0112 V2 token issued by the vault

- **Question:** How are shares represented, and must the vault, as asset admin of a V2 share token, emit `EventLog_HoldingsChange` for every share holding change?
- **Decision:** The vault operator is the instrument admin of the share instrument. The share token implements the V2 holding, transfer, allocation, settlement and event interfaces, and meets every MUST in them, including `EventLog_HoldingsChange` for every holding change. Minting and burning happen only through settlements of the share registry, via the special accounts. Only the operator can mint or burn; a mint outside a vault execution is detectable by reconciliation (T-13, I-02).
- **Implementation:** the share registry is implemented in `cvx-vault-v1` `.Internal` modules without a production dependency on `splice-token-standard-utils`. The twenty utils functions it needs are implemented from the V2 specification in `Cayvox.VaultV1.Internal.TokenStandard`, iterated settlement is rejected (`nextIterationFunding` must be `None`), and a test package tests them differentially against the utils defaults (`test/vault-v1-test/daml/Cayvox/VaultV1Test/Differential.daml`). As built (`docs/SPEC.md` §4.3): allocations are created directly, with no `AllocationInstruction`; allocations and locks do not expire, and a committed allocation must carry a settlement deadline; a locked holding is observed by the parties that act on its lock (`lockObservers`): the executors of the allocation it funds, or the receiver's parties of a pending transfer; a transfer completes in one step when the receiver's owner is among its actors, and is otherwise pending.
- **Scope in v1:** V2 only. A V1 `Holding` instance is not added in v1, because SCU can add an interface instance later but can never remove one (canton-contracts [`ARCHITECTURE.md:68-73`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L68-L73); "Packages with new versions cannot remove an instance that is already there", https://docs.canton.network/appdev/deep-dives/smart-contract-upgrade).
- **Evidence:** the DEX reference architecture mints LP tokens the same way: "LP tokens represent pool-share ownership and are minted/burned via CIP-0112" ([`dex.md:59`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/dex.md#L59)), as "a transfer leg from the special `cip-112/mint` account" ([`dex.md:374-379`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/dex.md#L374-L379)); the CIP-0112 event MUSTs ([`cip-0112.md:811-849`](https://github.com/canton-foundation/cips/blob/ef039e9a6901aeda7755d430c13d4b1ace311f60/cip-0112/cip-0112.md#L811-L849)); canton-contracts keeps its CIP-0112 token under `experiments/`, whose README asks applications not to depend on that directory ([`experiments/README.md:8-12`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/experiments/README.md#L8-L12)).
- **Alternatives:** build on canton-contracts' `tokenCIP112` experiment; local shares with no standard interface; shares as a number in vault state.
- **Reversal cost:** High.
- **Open question for maintainers:** yes: should the share token later move onto the canton-contracts CIP-0112 token once it is promoted?

## D-08 · Yield enters only through an operator choice

- **Question:** Are fees or yield accrual part of the component?
- **Decision:** `Vault_AddAssets`, controlled by the operator, settles incoming underlying into the vault's account and raises `totalAssets` without minting shares. There are no fees in v1. Loss recognition and strategies that move assets out are outside v1.
- **Evidence:** the OpenZeppelin Solidity vault charges no fee in its base contract and shows entry and exit fees as an extension in a documentation example ([`ERC4626Fees.sol:10`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/mocks/docs/ERC4626Fees.sol#L10)). A permissionless add would reintroduce a donation lever on a near-empty vault (`docs/SECURITY.md` T-01).
- **Reversal cost:** Low (additive).
- **Open question for maintainers:** no.

## D-09 · Rounding follows the three OpenZeppelin references, computed exactly

- **Question:** Which rounding direction is normative per operation, and how is it computed in Daml?
- **Decision:** `convertToShares`, `convertToAssets`, `previewDeposit` and `previewRedeem` round down. `previewMint` and `previewWithdraw` round up. Every product-quotient uses `mulDiv` with an explicit rounding direction from `cvx-vault-math-v1`.
- **Evidence:** Solidity, Stellar and Cairo agree per operation ([`ERC4626.sol:132-180`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L132-L180); [`storage.rs:164-300`](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/storage.rs#L164-L300); [`erc4626.cairo:424-433`](https://github.com/OpenZeppelin/cairo-contracts/blob/9df148099ac2f21891add25e335b8472b88c5a3f/packages/token/src/erc20/extensions/erc4626/erc4626.cairo#L424-L433), [`:713-776`](https://github.com/OpenZeppelin/cairo-contracts/blob/9df148099ac2f21891add25e335b8472b88c5a3f/packages/token/src/erc20/extensions/erc4626/erc4626.cairo#L713-L776)). Daml `Numeric` multiply and divide round with "banker's rounding convention" and take no rounding mode ([`daml-lf-2.rst:4034-4053`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4034-L4053)). A `Numeric` has "a precision of at most 38" ([`daml-lf-2.rst:553-555`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L553-L555)), so the product of two large `Decimal` values overflows before division. The `BigNumeric` builtins are "Available in version ≥ 2.dev" only ([`daml-lf-2.rst:4080-4089`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/daml-lf/spec/daml-lf-2.rst#L4080-L4089)).
- **Reversal cost:** Low for directions; the math package is independent.
- **Open question for maintainers:** no.

## D-10 · Inflation defence: virtual shares and assets, recorded accounting, slippage bounds, zero-share rejection

- **Question:** How does the vault defend an empty or near-empty vault against inflation and donation?
- **Decision:**
  1. Virtual shares and assets with a decimals offset, using the formula all three references share ([`ERC4626.sol:237-245`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L237-L245)). The offset is fixed at vault creation, default 0, at most `KMAX = 10`, the upper bound the Stellar vault suggests ([`mod.rs:415-416`](https://github.com/OpenZeppelin/stellar-contracts/blob/b40c5eaefe6a29f0030f00bd2d730b7a91cce330/packages/tokens/src/vault/mod.rs#L415-L416)). The asset bound depends on the offset, `A + VA <= floor(DMAX / 10^k)`, with the matching share bound `S + VS <= 10^k * floor(DMAX / 10^k)`, so no deposit within the asset bound overflows (`docs/MATH.md` §7).
  2. Recorded accounting (D-06) and operator-only asset addition (D-08).
  3. Every request carries a minimum output (`minSharesOut` or `minAssetsOut`) and a deadline.
  4. A deposit that would mint zero shares fails.
- **Evidence:** the virtual offset defence ([`erc4626.adoc:100-175`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/docs/modules/ROOT/pages/erc4626.adoc#L100-L175)); users "can protect against this attack as well as unexpected slippage in general by verifying the amount received is as expected" ([`ERC4626.sol:20-28`](https://github.com/OpenZeppelin/openzeppelin-contracts/blob/32b5b8c4655448291e27272d43607b9e3ae8c1d8/contracts/token/ERC20/extensions/ERC4626.sol#L20-L28)), which the minimum output on every request does whatever the price at execution. The attack is tested on the vault (`test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultHazards.daml`: `test_hazard_t01_inflationAttack`).
- **Reversal cost:** High for the formula once shares exist; Low for bounds.
- **Open question for maintainers:** no.

## D-11 · Daml-LF 2.1, no contract keys, an SDK matrix

- **Question:** Which SDK and Daml-LF target does the Vault build against, and may it use contract keys?
- **Decision:** Target `--target=2.1`. Build and run the in-memory tests on SDK 3.4.11, 3.5.8 and 3.5.10, selected with `DPM_SDK_VERSION`; `multi-package.yaml` pins 3.4.11. Run the sandboxes (gate Q-05), the demo and the upgrade check (gate Q-14) on SDK 3.4.11 (Canton 3.4.11, protocol version 34) and SDK 3.5.10 (Canton 3.5.17, protocol version 35). API packages are built once, with SDK 3.4.11, and implementation and test packages on every SDK consume that one DAR, because the package ID depends on the compiler that builds it. Each API package's main package ID is recorded in `dars/api-packages.yaml`, and CI fails when a build differs from it (`scripts/check-api-ids.sh`).
- **Evidence:** canton-contracts targets 2.1 ([`packages/security/api-pausable-v1/daml.yaml:9`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/packages/security/api-pausable-v1/daml.yaml#L9)) and pins SDK 3.5.8 ([`multi-package.yaml:3`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/multi-package.yaml#L3)); the Splice token API packages target 2.1 ([`splice-api-token-holding-v2/daml.yaml:15`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-holding-v2/daml.yaml#L15)); "Contract keys require Daml-LF 2.3 or later" (https://docs.canton.network/appdev/modules/m3-contract-keys, Enabling Contract Keys).
- **Consequence:**
  - Vaults are located by contract ID and explicit disclosure. Off-ledger indexing uses the interface view (D-12).
  - The Splice packages are built with SDK 3.5.2 ([`splice-api-token-holding-v2/daml.yaml:4`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-holding-v2/daml.yaml#L4)); every SDK of the matrix consumes their prebuilt LF 2.1 DARs from `dars/vendor/`.
  - Switching between SDKs needs clean build outputs, because a build does not recompile outputs left by another SDK (`ARCHITECTURE.md`, section 4; `scripts/ci.sh`).
- **Reversal cost:** High.
- **Open question for maintainers:** no.

## D-12 · A minimal, view-only frozen API package

- **Question:** Does the Vault define Daml interfaces, and what does the interface view carry?
- **Decision:** `cvx-api-vault-v1` defines one interface whose view carries the operator, the vault identifier, the underlying and share instrument IDs, `totalAssets`, `totalShares`, the decimals offset, the mode, the paused flag and a `meta` field of the Splice `Metadata` type (`splice-api-token-metadata-v1`) for extension. It defines no choices.
- **Evidence:** interfaces cannot be upgraded, so a component that defines them ships a frozen API package (canton-contracts [`ARCHITECTURE.md:32-41`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L32-L41)), and its surface stays minimal (the review of the Pausable API, https://github.com/OpenZeppelin/canton-contracts/pull/46#discussion_r4048593591). A `meta` field follows the Splice view pattern ([`HoldingV2.daml:74-87`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-holding-v2/daml/Splice/Api/Token/HoldingV2.daml#L74-L87)). With the Splice `InstrumentId` in the view, a `meta` of type `Metadata` adds no package to the closure, because `splice-api-token-holding-v2` already imports `Splice.Api.Token.MetadataV1` ([`HoldingV2.daml:9`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-holding-v2/daml/Splice/Api/Token/HoldingV2.daml#L9)).
- **Reversal cost:** High.
- **Open question for maintainers:** yes, as part of the API review: is this the view the library should freeze?

## D-13 · Error identifiers behind one internal constructor

- **Question:** Which error identifier format and category should new components use?
- **Decision:** All failures use `failWithStatus` through one `.Internal` constructor per package. The domain, identifier format and category are constants in that module. The working format is `cayvox.com/vault-<name>`; the rename to the format on canton-contracts `main` at submission time is part of D-17.
- **Evidence:** the Pausable component builds its failures in one `.Internal` helper under the `openzeppelin.com/pausable-` prefix ([`PausableV1/Internal.daml:7-14`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/packages/security/pausable-v1/daml/OpenZeppelin/PausableV1/Internal.daml#L7-L14)); review guidance: "The recommended approach for `errorId` is to include the DNS name, not only the relative one" (https://github.com/OpenZeppelin/canton-contracts/pull/48#discussion_r4131586738); `docs/CONVENTIONS.md`, section 6.
- **Consequence:** negative tests assert failures with the failure helper (`test/shared/Cayvox/Testing/Assert.daml`), which matches the exact `errorId` and category both whole and in the truncated form, where the category appears as code 8 (`InvalidIndependentOfSystemState`) or 9 (`InvalidGivenCurrentSystemStateOther`).
- **Reversal cost:** Low by construction.
- **Open question for maintainers:** yes: which identifier format and category should the vault use?

## D-14 · Pause through OpenZeppelin's Pausable interface; redemptions stay open

- **Question:** May the Vault implementation depend on the Pausable packages, and should redemptions stay open while paused?
- **Decision:** While paused, deposit execution and `Vault_AddAssets` fail; redemption execution and request cancellation continue. The operator controls the flag. The vault consumes `openzeppelin-api-pausable-v1` only as one released DAR from canton-contracts, pinned by main package ID in `dars/manifest.yaml`, and then implements its `Pausable` interface. Until such a release is available, the vault holds a local pause flag with identical semantics and no dependency. Adding the `Pausable` interface instance to the vault template later is compatible with Smart Contract Upgrade: an interface instance can be added under SCU, and never removed (canton-contracts [`ARCHITECTURE.md:68-73`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L68-L73)).
- **Evidence:** implementation packages may depend on API packages ([`AGENTS.md:38-40`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/AGENTS.md#L38-L40)); the canton-contracts Pausable vault example keeps `Vault_Redeem` open as "the ungated escape hatch" ([`examples/pausable/vault/README.md:23-24`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/examples/pausable/vault/README.md#L23-L24)). The package ID of an API package depends on the SDK that builds it (D-11), so the vault pins a released DAR rather than a local build.
- **Condition:** a production dependency needs architecture review, because an SCU lineage cannot drop it later ([`ARCHITECTURE.md:81-83`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L81-L83)). Fallback: a local flag with the same semantics and no dependency.
- **Reversal cost:** High after release.
- **Open question for maintainers:** yes: may the vault depend on a released `openzeppelin-api-pausable-v1` DAR, and when will one be available?

## D-15 · Privacy: holders see only their own positions

- **Decision:** The vault state is signed by the operator and disclosed to a requester when they act. Requests are visible to their requester and the operator. Share holdings follow V2 account visibility.
- **Evidence:**
  - "Account providers MUST have visibility on all asset movements and holdings" ([`HoldingV2.daml:34-41`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-holding-v2/daml/Splice/Api/Token/HoldingV2.daml#L34-L41)); consuming applications own disclosure (canton-contracts [`SECURITY.md:28-31`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/SECURITY.md#L28-L31)).
  - Only a party that sees a contract can produce its disclosure (https://docs.canton.network/overview/reference/ledger-model-detailed, Disclosure). The vault state and the share registry's `ShareRules` have the operator as their only signatory and no observer (`docs/SPEC.md` §4.1, §4.3), so the operator discloses them; each underlying registry discloses its own rules.
- **Consequence:** in Permissionless mode the operator serves the current vault state and the share registry's factory contracts to requesters, off ledger; the underlying registry serves its own.
- **Reversal cost:** Medium.
- **Open question for maintainers:** no.

## D-16 · Contention is bounded by batch execution

- **Decision:** Every execution consumes and recreates the vault state contract. The operator can execute up to 25 requests in one transaction (`test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultScenarios.daml`: `test_vault_batch_25AndNot26`). Requesters in Permissionless mode retry against the successor contract.
- **Evidence:**
  - Operations on a shared contract serialize, and the loser of a race retries against the successor ([`lending.md:934-936`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/lending.md#L934-L936); [`dex.md:1094-1100`](https://github.com/OpenZeppelin/canton-specs/blob/fcbe972fe98c6ea8f6d0d98f9b3376682f1e048c/docs/reference-architectures/dex.md#L1094-L1100)). The order of the checks sets the reported error, and the documentation states it (https://github.com/OpenZeppelin/canton-contracts/pull/46#discussion_r4081323652; `docs/SPEC.md` §5.3, §5.4; `test/vault-v1-test/daml/Cayvox/VaultV1Test/VaultOrder.daml`).
  - Each request has its own settlement, so each `SettlementFactory_SettleBatch` carries one leg and two allocations, inside the V2 size limits that registries "MUST support" ([`allocation-v2.yaml:19-31`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-api-token-allocation-v2/openapi/allocation-v2.yaml#L19-L31)); the batch is bounded by the transaction.
- **Reversal cost:** Low.
- **Open question for maintainers:** no.

## D-17 · Working names, and a tested mechanical rename

- **Decision:** Packages use `cvx-*` names and `Cayvox.*` modules. A script renames packages, modules, error domain and README references to the canton-contracts form (`openzeppelin-*`, `OpenZeppelin.*`), and CI proves the renamed tree builds and passes every test (`scripts/rename-d17.py`, `scripts/check-rename.sh`, gate Q-15).
- **Evidence:** naming rules in canton-contracts [`AGENTS.md:31-34`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/AGENTS.md#L31-L34) and [`:47-48`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/AGENTS.md#L47-L48). The working names keep this proposal distinct from OpenZeppelin's packages until the maintainers adopt it.
- **Reversal cost:** Low.
- **Open question for maintainers:** no.

## D-18 · Pins change only by decision

- **Decision:** The pinned revisions (canton-contracts, the Splice tag and its DARs in `dars/manifest.yaml`, the SDK matrix of D-11, and the daml-lint commit of gate Q-10) change only through an entry here, followed by a full gate run (`scripts/ci.sh`).
- **Reversal cost:** Low.
- **Open question for maintainers:** no.

### Pin change 1 · canton-contracts at `aeca01d`

- **Decision:** canton-contracts is pinned at `aeca01d043311d8ccc8ab7cda4d7c16e682429fa`, its `main` after PR 48 ("[Access] Scoped Authorization Grant") was merged. `docs/CONVENTIONS.md` restates the rules at that revision.
- **Reversal cost:** Low.
- **Open question for maintainers:** no.

---

## Open questions for library maintainers

In priority order:

1. D-01: Is a share vault over one underlying instrument, with ERC-4626 semantics, the intended library Vault?
2. D-02: Does one vault per instrument meet "multi-asset", and may multi-chain operation wait for the Messaging Gateway?
3. D-03: May library packages depend on the Token Standard V2 DARs that Splice ships at tag 0.8.4?
4. D-04: Is allocation-based settlement, with a request followed by an execution, the intended flow rather than direct transfer?
5. D-05: Is the operator's admission policy, with credential checks wired by the consuming application, the intended meaning of "permissioned"?
6. D-07: Should the share token later move onto the canton-contracts CIP-0112 token once it is promoted?
7. D-14: May the vault depend on a released `openzeppelin-api-pausable-v1` DAR, and when will one be available?
8. D-13: Which error identifier format and category should the vault use?
9. D-12: Is the view of `cvx-api-vault-v1` the surface the library should freeze?

Questions without a decision here:

- Which reference application should validate the vault before release?
- How should the coverage requirement be measured for acceptance?
- Which verification evidence does the library expect at acceptance?
- Should the vault appear in the Contracts Wizard, and with which configuration surface?
- Who audits the vault, and when?
