# Interface choices and their tests

Gate Q-03 requires every choice of a production package to be exercised (`docs/TESTING.md`). DPM's coverage report does not count the choices of interfaces that a package implements: for `test/vault-v1-test`, the report that `scripts/check-coverage.sh` writes under `test-reports/` reads "External interface choices: 0 defined". Those choices are checked automatically. `scripts/check-interface-coverage.py`, run by `scripts/check-coverage.sh`, derives every (interface choice, production template) pair from the DARs and requires each to be exercised in the test run's saved coverage, whose `exercised` field lists each choice with the templates it was exercised on (daml SDK 3.4.11 [`test_results.proto`, `TestResults`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/script-service/protos/test_results.proto#L10-L19) and [`Exercise`](https://github.com/digital-asset/daml/blob/de513339189206e5bcae77b2cfc68afda9b05ef5/sdk/compiler/script-service/protos/test_results.proto#L63-L72)). This list is kept as a cross-check: each row names an interface choice that a production template implements, and the tests that exercise it on a contract of that template; the check fails when the rows and the derived pairs differ. The list changes in the same commit as the interface instances it describes.

## `cvx-vault-v1`

Interfaces at Splice 0.8.4 (`splice-api-token-*-v2`); templates in `Cayvox.VaultV1.Internal.ShareRegistry`; tests in `test/vault-v1-test`.

| Interface choice | Template | Tests |
|---|---|---|
| `AllocationFactory_Allocate` | `ShareRules` | every allocation through `Setup.allocate` and `Setup.tryAllocate`; `test_allocate_*` (`Allocations`); `test_interop_*` (`Interop`) |
| `AllocationFactory_PublicFetch` | `ShareRules` | `test_shareRules_publicFetch` |
| `SettlementFactory_SettleBatch` | `ShareRules` | every settlement through `Setup.settle` and `Setup.trySettleAs`; `test_settleBatch_*` (`Allocations`); `test_interop_*` |
| `SettlementFactory_PublicFetch` | `ShareRules` | `test_shareRules_publicFetch` |
| `TransferFactory_Transfer` | `ShareRules` | `test_transfer_*` (`Transfers`); `test_bounds_transferFields` |
| `TransferFactory_PublicFetch` | `ShareRules` | `test_shareRules_publicFetch` |
| `Allocation_Settle` | `ShareAllocation` | every batch settlement; directly in `test_settleAllocation_*` |
| `Allocation_Cancel` | `ShareAllocation` | `test_cancelAllocation_consumesAllocation`, `test_cancelAllocation_failsForAuthorizer`, `test_diff_cancelAllocation` |
| `Allocation_Withdraw` | `ShareAllocation` | `test_withdrawAllocation_*` |
| `TransferInstruction_Accept` | `ShareTransferInstruction` | `test_acceptTransfer_*` |
| `TransferInstruction_Reject` | `ShareTransferInstruction` | `test_rejectTransfer_*` |
| `TransferInstruction_Withdraw` | `ShareTransferInstruction` | `test_withdrawTransfer_*` |
| `EventLog_HoldingsChange` | `ShareEventLog` | every registry operation that changes holdings; directly in `test_eventLog_*` |

`Holding` defines no choice of its own.

`VaultState` (`Cayvox.VaultV1`) implements `Vault` of `cvx-api-vault-v1`, which defines no choices (D-12). Its view is read through the interface on the ledger in `test_vault_viewThroughInterface` (`VaultScenarios`). The vault's own choices (`Vault_*`, `DepositRequest_*`, `RedeemRequest_*`) are template choices, which DPM's coverage report counts.

## `cvx-api-vault-v1`

The interface `Vault` defines no choices (D-12). Its view is read through the interface in `test_vaultView_readsThroughInterface` (`test/api-vault-v1-test`).
