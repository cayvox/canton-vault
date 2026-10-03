# Admission example

A Permissioned vault behind an on-ledger admission check. Never released or uploaded.

| Field | Value |
|---|---|
| Package | `com-example-vault-admission-v1` |
| Module | `Example.VaultAdmissionV1` |
| Uses | `cvx-vault-v1`, `cvx-api-vault-v1`, `cvx-vault-math-v1` |

## What it shows

- **Deployment.** The operator creates the share registry's `ShareRules`, a `VaultState` in `Permissioned` mode over a TestTokenV2 underlying, and an `AdmissionDesk` for the vault (`Example.VaultAdmissionV1Test.setup`).
- **Admission.** `AdmissionDesk` holds the parties the operator admits. `Desk_ExecuteDeposits` reads every request of a batch and fails with `cayvox.com/example-not-admitted` unless each requester, and the owner of each receiving account, is admitted. It then exercises `Vault_ExecuteDeposits` with the operator as executor. A desk executes only its own vault (`cayvox.com/example-wrong-vault`).
- **Pause.** The operator pauses the vault with `Vault_Pause`, and anyone with the vault state reads the flag through the `Vault` view. While paused, deposits fail with `cayvox.com/vault-paused`. `Desk_ExecuteRedeems` has no admission check, so neither admission nor the pause blocks a redemption; exit still needs the operator to execute it.

```daml
nonconsuming choice Desk_ExecuteDeposits : ExecResult
  with
    vault : ContractId VaultState
    items : [DepositItem]
    assetContext : ExtraArgs
    shareContext : ExtraArgs
  controller operator
  do
    v <- fetch vault
    unless (v.operator == operator && v.vaultId == vaultId) $ wrongVault
    forA_ items $ \i -> do
      request <- fetch i.request
      unless (request.requester `elem` admitted) $ notAdmitted request.requester
    exercise vault Vault_ExecuteDeposits with
      executor = operator; items; assetContext; shareContext
```

## Authority

The desk is signed by the operator alone, and every choice is the operator's. The admission check adds no authority: the vault's own checks still run inside `Vault_ExecuteDeposits`. A requester learns of its admission off-ledger.

The desk is the operator's policy aid, not a guarantee to anyone: the operator can also execute directly, and shares are transferable through the share registry, so admission governs who deposits, not who holds shares. The tests use no minimum output, a one-day deadline and the operator's basic account as the vault account; an application sets `minOut` from `previewDeposit`, keeps deadlines short and gives each vault its own account.

## Tests

`examples/vault-admission-v1-test`:
- `test_admission_admittedDepositExecutes`
- `test_admission_refusesOthers`
- `test_admission_pauseBlocksDepositsOnly`
- `test_admission_onlyItsVault`
- `test_admission_operatorClosesDesk`
- `demo`, the flow that `scripts/demo.sh` runs on a sandbox.
