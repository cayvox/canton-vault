<!-- markdownlint-disable MD024 -->

# Changelog

User-visible changes to production packages and their public APIs are documented
in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### `cvx-vault-math-v1`

#### Added

- Added the utility package `cvx-vault-math-v1` with public module
  `Cayvox.VaultMathV1`.
- Added `mulDiv : Rounding -> Decimal -> Decimal -> Decimal -> Decimal`, the
  exact `a * b / c` rounded down (`Floor`) or up (`Ceil`) over the whole
  non-negative `Decimal` range. The product is never rounded and never
  overflows on its own.
- Added the failures `cayvox.com/math-negative-operand`,
  `cayvox.com/math-non-positive-divisor` and `cayvox.com/math-overflow`, with
  category `InvalidGivenCurrentSystemStateOther`.

#### Changed

- `mulDiv` converts between `Decimal` and its exact integer with arithmetic
  whose semantics the Daml-LF specification states, instead of through the
  text of the `Decimal`, whose format the specification leaves open. Results
  and failures are unchanged.

### `cvx-api-vault-v1`

#### Added

- Added the API package `cvx-api-vault-v1` with public module
  `Cayvox.Api.VaultV1`. The module exports no definitions.
- Added the interface `Vault`, with view type `VaultView` (`operator`,
  `vaultId`, `asset`, `shareInstrument`, `totalAssets`, `totalShares`,
  `decimalsOffset`, `mode`, `paused`, `meta`) and the type `Mode`
  (`Permissioned`, `Permissionless`). The interface defines no choices.
- Added data-dependencies on the Splice 0.8.4 API packages
  `splice-api-token-metadata-v1` and `splice-api-token-holding-v2`.

### `cvx-vault-v1`

#### Added

- Added the implementation package `cvx-vault-v1` with public module
  `Cayvox.VaultV1`.
- Added the share registry: templates `ShareRules`, `ShareHolding`,
  `ShareAllocation`, `ShareTransferInstruction` and `ShareEventLog`, which
  implement the Canton Token Standard V2 interfaces `AllocationFactory`,
  `SettlementFactory`, `TransferFactory`, `Holding`, `Allocation`,
  `TransferInstruction` and `EventLog` for the vault's share instrument.
  Shares are minted and burned only by settling allocations with the
  CIP-0112 special accounts `cip-112/mint` and `cip-112/burn`.
- Added the registry failures `cayvox.com/registry-...`, with category
  `InvalidGivenCurrentSystemStateOther`. A committed share allocation must
  carry a settlement deadline (`cayvox.com/registry-committed-without-deadline`).
- Added data-dependencies on the Splice 0.8.4 API packages
  `splice-api-token-metadata-v1`, `-holding-v2`, `-allocation-v2`,
  `-allocation-instruction-v2`, `-transfer-instruction-v2` and
  `-transfer-events-v2`.
- Added the public module `Cayvox.VaultV1.Conversion` with `convertToShares`,
  `convertToAssets`, `previewDeposit`, `previewMint`, `previewWithdraw` and
  `previewRedeem`, each taking a `VaultView` and an amount, with the failure
  `cayvox.com/vault-capacity-exceeded`.
- Added data-dependencies on `cvx-vault-math-v1` and `cvx-api-vault-v1`.
- Added the template `VaultState`, which implements `Vault` of
  `cvx-api-vault-v1`, with the choices `Vault_ExecuteDeposits` and
  `Vault_ExecuteRedeems` (batches of 1 to 25 requests, executed by the
  operator in Permissioned mode and by each requester in Permissionless
  mode), `Vault_AddAssets`, `Vault_Pause` and `Vault_Unpause`, and the types
  `RegistryRef`, `DepositItem`, `RedeemItem` and `ExecResult`.
- Added the templates `DepositRequest` and `RedeemRequest`, with the
  operator's one-shot delegation choices `DepositRequest_Allocate` and
  `RedeemRequest_Allocate`, the requester's one-step cancellation choices
  `DepositRequest_Cancel` and `RedeemRequest_Cancel`, and the type
  `RequestAllocations`.
- Added the vault failures `cayvox.com/vault-unauthorized-executor`,
  `-paused`, `-batch-size`, `-duplicate-request`, `-wrong-vault`,
  `-request-expired`, `-allocation-mismatch`, `-zero-shares`,
  `-zero-assets`, `-slippage`, `-insufficient-assets`, `-no-shares`,
  `-already-paused`, `-not-paused` and `-invalid-amount`, with category
  `InvalidGivenCurrentSystemStateOther`.
- `Cayvox.VaultV1` exports `ShareRules`, the share registry's rules
  contract, so that a consumer creates the share registry through the
  public module.

#### Changed

- A share allocation's leg sides must have positive amounts, and a special
  account may appear only on the side it allows (`cip-112/mint` sends,
  `cip-112/burn` receives); otherwise the allocation is not created.
