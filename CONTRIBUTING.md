# Contributing

## Setup

Install dpm by the method of the [dpm documentation](https://docs.canton.network/sdks-tools/cli-tools/dpm), with a JDK 17 or later on the path, then the three SDKs of the matrix:

```sh
curl https://get.digitalasset.com/install/install.sh | sh
dpm install 3.4.11
dpm install 3.5.8
dpm install 3.5.10
```

The gate scripts also need Python 3, `jq`, `unzip`, `git` and `shasum`; the sandbox gates need `lsof`; the daml-lint gate needs `cargo` and a checkout of [OpenZeppelin/daml-lint](https://github.com/OpenZeppelin/daml-lint) at the revision `scripts/check-daml-lint.sh` pins. The proof gate installs `z3-solver` into a virtual environment under `~/.cache/cvx-vault` on first use.

## The SDK matrix

`multi-package.yaml` pins SDK 3.4.11, and every manifest mirrors it. A run selects another SDK with `DPM_SDK_VERSION`, which overrides the `sdk-version` of every manifest. The build and the in-memory tests run on SDK 3.4.11, 3.5.8 and 3.5.10. The sandbox, demo and upgrade gates run on SDK 3.4.11 (Canton 3.4.11, protocol version 34) and SDK 3.5.10 (Canton 3.5.17, protocol version 35).

The API package `cvx-api-vault-v1` is always built by SDK 3.4.11, and the other packages consume that one DAR on every SDK, because a build with another SDK has another package ID. Its ID is recorded in `dars/api-packages.yaml`, and `scripts/check-api-ids.sh` fails when a build differs from it (D-11 in [`docs/DECISIONS.md`](docs/DECISIONS.md)). A build does not recompile outputs left by another SDK, so `scripts/build-all.sh` removes them first.

## The gates

[`docs/TESTING.md`](docs/TESTING.md) defines the gates Q-01 to Q-16. Each scripted gate is one script:

| Gate | Script |
|---|---|
| Q-01 build, on one SDK | `DPM_SDK_VERSION=<sdk> scripts/build-all.sh` |
| Q-02 conventions | `scripts/check.sh` |
| Q-03 and Q-04 unit tests, coverage, interface choices | `scripts/check-coverage.sh` |
| Q-05 sandboxes | `scripts/check-sandbox.sh` |
| Q-06 differential math | `scripts/check-math-oracle.sh` |
| Q-07 mutation | `scripts/mutate-math.py`, `scripts/mutate-registry.py` |
| Q-08 operation sequences | `scripts/check-sequences.sh` |
| Q-09 proofs | `scripts/check-math-proofs.sh` |
| Q-10 lint | `scripts/check-lint.sh`, `scripts/check-daml-lint.sh <daml-lint checkout>` |
| Q-11 documentation | `scripts/check-docs.sh` |
| Q-12 style | `scripts/check-style.sh` |
| Q-14 upgrade | `scripts/check-upgrade.sh` |
| Q-15 rename | `scripts/check-rename.sh` |
| Q-16 token DAR identity | `scripts/check-token-dars.sh` |

`scripts/check-examples.sh` and `scripts/check-tools.sh` run the example and tool tests. `scripts/ci.sh` runs every scripted gate in one run, ordered to fail fast, and `CI_FROM=<stage>` resumes from a stage; a full run takes several hours. On macOS, run it as `caffeinate -dimsu scripts/ci.sh` with the lid open, because a sleeping host stops the sandbox.

The GitHub workflow runs Q-12, Q-16 and Q-02, then Q-01 and the unit, coverage, example and tool tests on each SDK of the matrix. The other gates need a local Canton sandbox on fixed ports or long runs, so they run through `scripts/ci.sh`.

Package-scoped work uses DPM directly, for example:

```sh
DAML_PACKAGE=packages/token/vault-v1 dpm damlc lint
DAML_PACKAGE=test/vault-v1-test dpm test --all --show-coverage
```

## Conventions

[`docs/CONVENTIONS.md`](docs/CONVENTIONS.md) restates the conventions of OpenZeppelin/canton-contracts that this repository follows, each linked to its source, and lists where this repository differs. Package names keep the working prefix `cvx` and modules the prefix `Cayvox`; `scripts/rename-d17.py` produces the library's names (D-17).

## Commits

- Conventional Commits, with one of the types `feat`, `fix`, `docs`, `test`, `refactor`, `chore` or `ci`, and a subject in the imperative mood of at most 72 characters.
- One logical change per commit. Behaviour changes are separate from restructuring.
- No em dashes and no en dashes, in commit messages or in files. `scripts/check-style.sh` checks the files.
- A change to an API package changes its package ID: record the new ID in `dars/api-packages.yaml` in the same commit.

## Pull requests

Describe the affected packages, the compatibility impact, changes to dependencies, authority or privacy, the tests that show the change, and the documents updated. Report security problems privately, as [`SECURITY.md`](SECURITY.md) describes.
