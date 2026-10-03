# Vault reconciliation tool

A read-only Daml Script that reconciles a vault's recorded accounting with the ledger, over the operator's view. Never released, and no production package depends on it.

| Field | Value |
|---|---|
| Package | `cvx-vault-reconcile-tool` |
| Module | `Cayvox.VaultTools.Reconcile` |
| Entry point | `reconcile : ReconcileInput -> Script Report` |

## What it checks

| Check | Compares | Detects |
|---|---|---|
| I-01 | `totalAssets` with the journal: underlying that vault choices moved into the vault account, minus what they moved out | T-11: totals rewritten by archiving and recreating the vault state |
| I-02 | `totalShares` with the sum of every share holding of the vault's instrument | T-13: shares minted outside a vault execution; T-21: a redemption's input burned outside one |
| Custody (`docs/SPEC.md` §8) | The vault account's underlying with the journal plus the donations | T-10: underlying moved out of the vault account outside vault choices; T-21: a deposit's input moved in outside one, unless counted as a donation |
| Identity, with a baseline | The fields no vault choice changes (instruments, vault account, mode, offset, registries) with the baseline | T-11 with unchanged totals: a state recreated with another offset, account, mode or registry |

The script reads only active contracts, through the operator's party: the vault state, the share holdings and the vault account's holdings, these two through the token standard's `Holding` interface. It submits nothing.

**Who runs it.** The vault state has no observers, and only the operator sees every share holding and the vault account, so the script runs as the operator's party, by the operator or by an auditor given read rights for that party on the operator's participant.

**Inputs.** The script reads active contracts only; the journal and the donations come from the operator's transaction stream, read up to the same ledger offset as the snapshot the script takes:
- **journal**: for every transaction whose root is a vault choice (`Vault_ExecuteDeposits`, `Vault_ExecuteRedeems`, `Vault_AddAssets`) on this vault's state, the vault account's underlying holdings created minus those archived in it;
- **donations**: the same for every other transaction that touches the vault account. A transaction under a request's settlement (`<vaultId>/deposit`, `<vaultId>/redeem`) without a vault choice is T-21, not a donation, and an outflow is T-10.

The tests compute the journal from each execution's transaction tree, as an application reading the stream does (`test/vault-v1-test`, `journaled`). Reading the stream needs a Ledger API client outside Daml Script, which reads only active contracts, so the tool takes the journal as an input. **baseline** is the identity the report returned when the vault was created, or `null`.

Build the production packages first, the API package with SDK 3.4.11, then the tool:

```sh
DAML_PACKAGE=tools/vault-reconcile dpm build
dpm script --dar tools/vault-reconcile/.daml/dist/cvx-vault-reconcile-tool-0.0.0.dar \
  --script-name Cayvox.VaultTools.Reconcile:reconcile \
  --input-file input.json --output-file report.json \
  --ledger-host localhost --ledger-port 6865
```

`input.json` holds `{"operator": "<party>", "vaultId": "<id>", "journal": "<decimal>", "donations": "<decimal>", "baseline": null}`. `report.json` receives the report; its `findings` list is empty when the vault reconciles. Against a participant that requires authentication, add `--access-token-file` with a token whose user can read as the operator party, and the TLS options of `dpm script`.

## Tests

`tools/vault-reconcile-test` (`scripts/check-tools.sh`; it data-depends on the `test/vault-v1-test` DAR for the vault tests' fixtures, so build that first):
- `test_tool_honestRunReconciles`: deposits, a redemption and a donation, no finding;
- `test_tool_detectsRewrittenTotals`: T-11;
- `test_tool_detectsOutsideMint`: T-13;
- `test_tool_detectsCustodyMove`: T-10;
- `test_tool_detectsChangedIdentity`: a recreated state with the same totals and another offset.
