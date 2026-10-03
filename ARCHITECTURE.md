# Architecture

This file records the structure of the repository and the reasons for it. Design decisions are in `docs/DECISIONS.md`; this file records how the tree implements them. Paths into upstream repositories are at the revisions named where they are cited: OpenZeppelin/canton-contracts at `aeca01d043311d8ccc8ab7cda4d7c16e682429fa` unless stated otherwise, and canton-network/splice at tag `0.8.4`.

## 1. Directory layout

| Path | Contents |
|---|---|
| `multi-package.yaml` | The workspace: SDK pin and the list of packages |
| `packages/<category>/<component>-vN` | Production packages, one package and one DAR each |
| `test/<component>-vN-test` | The isolated `-test` package of each production package |
| `examples/<example>-vN`, `examples/<example>-vN-test` | Consumer examples and their `-test` packages, never released (section 6) |
| `tools/<tool>` | Never-released tooling, with its `-test` package: the reconciliation aid (section 7) |
| `docs/site/` | The documentation page, written for the OpenZeppelin docs site |
| `dars/manifest.yaml`, `dars/vendor/` | Vendored third-party DARs and their provenance (section 3) |
| `scripts/` | Gate scripts (section 5) |
| `LICENSES/` | License texts of third-party material in this tree |

The categories are:

| Category | Packages | Precedent |
|---|---|---|
| `token` | `cvx-api-vault-v1`, `cvx-vault-v1` | canton-contracts keeps its CIP-0112 token under a `token` category ([`multi-package.yaml:28`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/multi-package.yaml#L28)). OpenZeppelin places its vaults under token: Solidity `contracts/token/ERC20/extensions/ERC4626.sol`, Cairo `packages/token/src/erc20/extensions/erc4626.cairo`, Stellar `packages/tokens/src/vault` |
| `utils` | `cvx-vault-math-v1` | OpenZeppelin places its math under utils: Solidity `contracts/utils/math/Math.sol`, Cairo `packages/utils/src/math.cairo` |

Category directories are navigation only and never appear in package or module names (canton-contracts [`AGENTS.md:47-48`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/AGENTS.md#L47-L48), [`multi-package.yaml:1-2`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/multi-package.yaml#L1-L2)). The production tree `packages/<category>/` and the flat test tree `test/<component>-vN-test` follow the canton-contracts conventions at `aeca01d` ([`multi-package.yaml:5-12`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/multi-package.yaml#L5-L12), [`CONTRIBUTING.md:92-93`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/CONTRIBUTING.md#L92-L93), with the differences listed in `docs/CONVENTIONS.md`.

## 2. Packages

| Package | Module | Kind | Data dependencies now |
|---|---|---|---|
| `cvx-vault-math-v1` | `Cayvox.VaultMathV1` | Utility ([`ARCHITECTURE.md:79-80`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L79-L80)) | none |
| `cvx-api-vault-v1` | `Cayvox.Api.VaultV1` | Frozen API ([`ARCHITECTURE.md:32-41`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L32-L41)) | `splice-api-token-metadata-v1`, `splice-api-token-holding-v2` |
| `cvx-vault-v1` | `Cayvox.VaultV1`, `Cayvox.VaultV1.Conversion` | Implementation | `cvx-vault-math-v1`, `cvx-api-vault-v1`, and the Splice V2 API packages `metadata-v1`, `holding-v2`, `allocation-v2`, `allocation-instruction-v2`, `transfer-instruction-v2`, `transfer-events-v2` |

Each data dependency was added in the change that first used it, because a production dependency cannot be dropped from an SCU lineage (canton-contracts [`ARCHITECTURE.md:81-83`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/ARCHITECTURE.md#L81-L83)) and `damlc` reports an unused one. No production package depends on `splice-token-standard-utils` or on a test token (section 3.1).

Each test package is named `<package>-test`, has version `0.0.0`, depends on `daml-script`, and data-depends on its production DAR by a relative path (`docs/CONVENTIONS.md`, section 8). Every package builds with `--target=2.1` (D-11).

## 3. Vendored DARs

`dars/vendor/` holds the Splice 0.8.4 DARs that the vault and its tests use, byte-identical to `daml/dars/` of canton-network/splice at tag `0.8.4` (`fa6b029f`). This follows D-03: the API DARs are the files Splice ships at that tag. `dars/manifest.yaml` records each one: source URL, tag, commit, path, name, version, main package ID, package-ID closure, SHA-256, SDK and LF version, license, and use. `scripts/check-token-dars.sh` verifies every field (gate Q-16). The license is Apache-2.0 (Splice `LICENSE` at the tag); Splice has no `NOTICE` file at the tag. The text is in `LICENSES/splice-Apache-2.0.txt`.

| DAR | Why it is here | Used by | Production use |
|---|---|---|---|
| `splice-api-token-metadata-v1` 1.0.0 | Every V2 choice the vault calls takes `extraArgs : ExtraArgs` from this package (`AllocationV2.daml:272`, `:430`; `AllocationInstructionV2.daml:168`), and holding, allocation and allocation-instruction V2 import it (`HoldingV2.daml:9`, `AllocationV2.daml:26`, `AllocationInstructionV2.daml:10`) | `cvx-vault-v1`, `cvx-api-vault-v1` (the view's `meta`); tests | `cvx-vault-v1`, `cvx-api-vault-v1` (D-03, D-12) |
| `splice-api-token-holding-v2` 1.0.0 | `InstrumentId`, `Account` and `Holding`, used by every leg and allocation (`AllocationV2.daml:27`) | `cvx-vault-v1`, `cvx-api-vault-v1` (the view's `InstrumentId`); tests | `cvx-vault-v1`, `cvx-api-vault-v1` |
| `splice-api-token-allocation-v2` 1.0.0 | `SettlementFactory_SettleBatch`, `Allocation_Settle` and the settlement types (`AllocationV2.daml:224-434`); every settlement of a deposit or redemption | `cvx-vault-v1`; tests | `cvx-vault-v1` |
| `splice-api-token-allocation-instruction-v2` 1.0.0 | `AllocationFactory_Allocate` (`AllocationInstructionV2.daml:140-182`); every allocation the vault creates | `cvx-vault-v1`; tests | `cvx-vault-v1` |
| `splice-api-token-transfer-instruction-v2` 1.0.0 | The share registry's transfers; the tests fund holdings by accepting the `TransferInstruction` that `TokenRules_OfferMint` creates (`test/vault-v1-test/daml/Cayvox/VaultV1Test/Underlying.daml`) | `cvx-vault-v1`: the share registry's `TransferFactory` and `TransferInstruction` (SPEC §4.3); tests | `cvx-vault-v1` |
| `splice-api-token-transfer-events-v2` 1.0.0 | `EventLog` and `EventLog_HoldingsChange`, with which the share registry reports every change to share holdings (`TransferEventsV2.daml:49-106`; SPEC §8) | `cvx-vault-v1`; tests | `cvx-vault-v1` |
| `splice-token-standard-utils` 2.0.0 | The reference implementation of the twenty token-standard functions that the vault implements itself; the differential tests run both on the same inputs (`Cayvox.VaultV1Test.Differential`) | test | Needs architecture review before any production use (section 3.1) |
| `splice-test-token-v2` 1.0.1 | The underlying registry of the tests and the example (`Cayvox.VaultV1Test.Underlying`) | test | never |

Not vendored, because no package of this repository uses them as files: the V1 API packages, `splice-api-token-allocation-request-v1` and `-v2`, and `splice-api-token-burn-mint-v1`. The packages that `splice-test-token-v2` and `splice-token-standard-utils` depend on travel inside those DARs (`dars/manifest.yaml`, `package-ids`).

### 3.1 `splice-token-standard-utils` as a production dependency

The vault is the instrument admin of its shares, so its share registry implements `AllocationFactory` and `SettlementFactory` for the mint and burn legs (`docs/SPEC.md`, section 4.3). In `splice-test-token-v2` those implementations delegate to utils, for example `settlementFactoryV2_settleBatchDefaultImpl` ([`Utils/Internal/Allocations.daml:368-399`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml/Splice/TokenStandard/Utils/Internal/Allocations.daml#L368-L399)). Depending on utils in production would add its whole closure to the `cvx-vault-v1` lineage: every V1 and V2 API package of the token standard, including `allocation-request` and `transfer-events` ([`splice-token-standard-utils/daml.yaml:11-23`](https://github.com/canton-network/splice/blob/0.8.4/token-standard/splice-token-standard-utils/daml.yaml#L11-L23); `dars/manifest.yaml`, 44 package IDs). Such a production dependency needs architecture review (`docs/CONVENTIONS.md`, section 3). No production package depends on it: `cvx-vault-v1` carries its own implementation of the twenty utils functions that the share registry needs, in `Cayvox.VaultV1.Internal.TokenStandard`, over the API packages alone, and the test package checks each against utils on the same inputs (`test/vault-v1-test`, `Cayvox.VaultV1Test.Differential`).

## 4. Two SDKs

The workspace pins SDK 3.4.11 in `multi-package.yaml` and in every `daml.yaml` (`docs/CONVENTIONS.md`, section 9). The same tree builds and runs its in-memory tests on SDK 3.5.8 and SDK 3.5.10 with the environment variable `DPM_SDK_VERSION`. The DPM configuration reference defines it as: "Override the SDK version globally. This overrides the `sdk-version` in all `daml.yaml` files. It does not affect `dpm install`." (https://docs.canton.network/appdev/modules/m5-environment-configuration; https://docs.canton.network/appdev/reference/configuration-reference). The sandbox runs (gate Q-05), the demo and the upgrade check (gate Q-14) use SDK 3.4.11 (Canton 3.4.11, protocol version 34) and SDK 3.5.10 (Canton 3.5.17, protocol version 35).

```sh
dpm build --all                          # SDK 3.4.11, from multi-package.yaml
DPM_SDK_VERSION=3.5.8 dpm build --all    # SDK 3.5.8, same tree
DPM_SDK_VERSION=3.5.10 dpm build --all   # SDK 3.5.10, same tree
```

On this tree:

- With `DPM_SDK_VERSION=3.5.10`, `dpm version --active` reports `3.5.10`, and every DAR from a clean build records `Sdk-Version: 3.5.10` in `META-INF/MANIFEST.MF`.
- A build over the outputs of the other SDK does not recompile them: after an SDK 3.4.11 build, `DPM_SDK_VERSION=3.5.10 dpm build --all` left DARs with `Sdk-Version: 3.4.11`. `scripts/ci.sh` therefore removes each package's `.daml/` before building, and checks the `Sdk-Version` and the Daml-LF version of every DAR.

API packages are the exception: they are built once, by SDK 3.4.11, and the runs on SDK 3.5.8 and 3.5.10 consume that DAR. `scripts/ci.sh` builds each package on its own (`--enable-multi-package=no`) in `multi-package.yaml` order, with SDK 3.4.11 for API packages, and `scripts/check-api-ids.sh` compares each API package's main package ID with `dars/api-packages.yaml` (D-11).

One DAR tree exists at a time. Test reports go to `test-reports/<sdk>/` (`scripts/check-coverage.sh`).

## 5. Gate scripts

| Script | Gate | Origin |
|---|---|---|
| `scripts/check-style.sh` | Q-12 | Written here |
| `scripts/check-token-dars.sh` | Q-16 | Written here |
| `scripts/check.sh` | Q-02 | Port of canton-contracts `scripts/check.sh` |
| `scripts/check-lint.sh` | Q-10, `damlc lint` | Port of canton-contracts `scripts/check-lint.sh` |
| `scripts/check-daml-lint.sh`, `scripts/daml-lint-justified.tsv` | Q-10, OpenZeppelin daml-lint at `cba69883`, every finding fixed or justified in the table | Written here |
| `scripts/check-math-oracle.sh`, `scripts/math-oracle.py` | Q-06, differential math against Python `decimal` | Written here |
| `scripts/mutate-math.py` | Q-07 for `cvx-vault-math-v1` | Written here |
| `scripts/check-math-proofs.sh`, `scripts/prove-math.py` | Q-09, Z3 on an integer model | Written here |
| `scripts/check-coverage.sh` | Q-03 | Port of canton-contracts `scripts/check-coverage.sh` |
| `scripts/check-interface-coverage.py` | Q-03, interface choices derived from the DARs | Written here |
| `scripts/check-api-ids.sh` | Q-01, the recorded API package IDs (D-11) | Written here |
| `scripts/check-sandbox.sh` | Q-05, every test on the protocol version 34 and 35 sandboxes | Written here; it stops the sandbox as a process group, as canton-contracts `scripts/check-sandbox.sh` at `a2d5763` does |
| `scripts/check-sequences.sh`, `scripts/check-sequences.py` | Q-08, 1,000 seeded sequences per SDK | Written here |
| `scripts/mutate-registry.py` | Q-07 for `cvx-vault-v1`, with the mutant precheck that `ci.sh` runs | Written here |
| `scripts/check-upgrade.sh` | Q-14, `dpm upgrade-check` on a patch and a breaking candidate | Written here |
| `scripts/rename-to-openzeppelin.py`, `scripts/check-rename.sh` | Q-15, the D-17 rename in a copy outside the repository | Written here |
| `scripts/check-examples.sh` | examples | Port of canton-contracts `scripts/check-examples.sh` |
| `scripts/check-tools.sh` | the tooling tests | Written here |
| `scripts/demo.sh` | the demo on a sandbox | Written here |
| `scripts/xz-clean.sh` | compression of kept logs that the style gate accepts | Written here |
| `scripts/ci.sh` | Every scripted gate in one run, ordered to fail fast: Q-12, Q-16, Q-02; Q-01, Q-10, Q-09, Q-11; the in-memory suites; Q-05 and the demo; Q-14; Q-15 | Written here from `docs/TESTING.md`, section 5 |
| `scripts/check-docs.sh` | Q-11, the documentation a script can verify | Written here |

Tools that the scripts install (the daml-lint build, the Z3 virtual environment) live in a cache outside the repository, `${XDG_CACHE_HOME:-~/.cache}/cvx-vault`, so that no third-party file enters the tree that gate Q-12 scans.

The ports are from canton-contracts, which is MIT licensed ([`LICENSE:1-21`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/LICENSE#L1-L21)). `scripts/check.sh` and `scripts/check-coverage.sh` are ported from `aeca01d043311d8ccc8ab7cda4d7c16e682429fa`. `scripts/check-lint.sh` and `scripts/check-examples.sh` name `a2d576344fe96d49751b276e8c638e02ef682c57` in their headers; both source files are identical at `a2d5763` and `aeca01d`. Each ported file names its source path, the commit and the license in its header, and lists its changes. The license text is in `LICENSES/canton-contracts-MIT.txt`.

## 6. Examples

`examples/` holds standalone consumer projects (canton-contracts [`examples/README.md:3-6`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/examples/README.md#L3-L6)). Each example's templates are one package, and its Daml Script tests a sibling `-test` package that data-depends on the example DAR, so the example DAR does not depend on `daml-script`. Both are listed in `multi-package.yaml`, as canton-contracts lists its examples, and are never released or uploaded.

| Package | Shows |
|---|---|
| `com-example-vault-admission-v1` (`examples/vault-admission-v1`) | A Permissioned vault behind an on-ledger admission check, with the pause flag |
| `com-example-vault-admission-v1-test` | Its tests, and the flow that `scripts/demo.sh` runs on a sandbox |

## 7. Tools

`tools/` holds never-released tooling. No production package depends on it, and it is outside `packages/`.

| Package | Contents |
|---|---|
| `cvx-vault-reconcile-tool` (`tools/vault-reconcile`) | The reconciliation aid: a read-only Daml Script over the operator's view that checks I-01, I-02 and custody (SPEC §8) |
| `cvx-vault-reconcile-tool-test` | Its tests: an honest run reconciles; T-10, T-11 and a mint outside the vault are reported. It reuses the vault tests' fixtures through the `cvx-vault-v1-test` DAR |

