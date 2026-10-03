# Examples

Standalone consumer projects that integrate the production DARs through `data-dependencies`. Each example's templates live in one package, and its Daml Script tests in a sibling `-test` package, so the example DAR does not depend on `daml-script`. Examples are never released or uploaded.

| Example | Tests | Shows |
|---|---|---|
| [`vault-admission-v1`](vault-admission-v1) | [`vault-admission-v1-test`](vault-admission-v1-test) | A Permissioned vault behind an on-ledger admission check, with the pause flag: admitted parties deposit to admitted receivers, others are refused, and while paused deposits fail and redemptions still pay |

## Build and run

Prerequisites: `dpm` with SDK 3.4.11, 3.5.8 and 3.5.10 installed (`dpm install 3.4.11`, `dpm install 3.5.8`, `dpm install 3.5.10`), and the production packages built first, the API package with SDK 3.4.11 (`scripts/build-all.sh` does it).

From the repository root, using the package paths of `multi-package.yaml`:

```sh
DAML_PACKAGE=examples/vault-admission-v1 dpm build
DAML_PACKAGE=examples/vault-admission-v1-test dpm test --all
```

`scripts/check-examples.sh` runs every example's tests. `scripts/demo.sh` runs the admission example's full flow on a sandbox and prints each step.
