# Vault API V1

The frozen Daml interface through which wallets, indexers and other applications read a vault.

| Field | Value |
|---|---|
| Package | `cvx-api-vault-v1` |
| Public module | `Cayvox.Api.VaultV1` |
| Version | `0.1.0` |
| Status | Pre-release; unaudited |

## What it provides

| Name | Kind | Meaning |
|---|---|---|
| `Vault` | Interface, `viewtype VaultView` | A vault, read through its view. It defines no choices |
| `VaultView` | Record | The vault's identity and accounting: `operator`, `vaultId`, `asset`, `shareInstrument`, `totalAssets`, `totalShares`, `decimalsOffset`, `mode`, `paused`, `meta` |
| `Mode` | `data Mode = Permissioned \| Permissionless` | Who executes the vault's requests: the operator, or each requester for its own requests |

`asset` and `shareInstrument` are Splice `InstrumentId` values (`splice-api-token-holding-v2`); `meta` is Splice `Metadata` (`splice-api-token-metadata-v1`). `totalAssets` is the vault's recorded underlying and `totalShares` its share supply; with `decimalsOffset` they are the inputs of the vault's conversion functions.

```daml
readVault : Party -> ContractId Vault -> Script (Optional VaultView)
readVault reader cid = queryInterfaceContractId reader cid
```

The package is a frozen API package: it has no templates and no helper functions.

## Authority and lifecycle

The interface defines no choices of its own, so it grants no authority. Like every interface, it carries the implicit `Archive` choice, whose controllers are the implementing template's signatories: the operator can archive a `VaultState` through it, as it can archive the contract directly ([`docs/SECURITY.md`](../../../docs/SECURITY.md) §2, "State integrity outside choices"). Signatories, observers, disclosure and every operation belong to the implementing template; the vault of `cvx-vault-v1` is signed by its operator and is read by explicit disclosure.

## Scope and security caveats

- The package is pre-release and unaudited.
- A view states what the implementing template reports. Any template can implement `Vault`; a client identifies the implementing template and its package before relying on a view.
- The interface cannot be upgraded. A change to `Vault`, `VaultView` or `Mode` is a new package. Even a patch that changes only a doc comment is refused: "Tried to upgrade interface Vault, but interfaces cannot be upgraded" (`dpm upgrade-check`, run by `scripts/check-upgrade.sh`), so every compatible release of the vault keeps depending on this package at `0.1.0`.

## Compatibility

Daml-LF `2.1`, built with SDK 3.4.11 only (see Build). Tested in memory on SDK 3.4.11, 3.5.8 and 3.5.10, and on Canton sandboxes of SDK 3.4.11 (protocol version 34) and SDK 3.5.10 (protocol version 35).

## Build

Build this package with SDK 3.4.11 only. Its main package ID is recorded in [`dars/api-packages.yaml`](../../../dars/api-packages.yaml), `27fcecf9...`; another SDK compiles it to another ID, and wallets that match the interface by package ID would not recognise it. Remove `.daml/` before building with another SDK, because a build does not recompile another SDK's outputs.

From the repository root:

```sh
DAML_PACKAGE=packages/token/api-vault-v1 DPM_SDK_VERSION=3.4.11 dpm build
```

## Consume a local build

```yaml
data-dependencies:
  - ../canton-vault/packages/token/api-vault-v1/.daml/dist/cvx-api-vault-v1-0.1.0.dar
```

```daml
import Cayvox.Api.VaultV1
```
