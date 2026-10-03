# Testing and quality gates

## 1. Test layers

| Layer | Runner | What it proves |
|---|---|---|
| Unit | `dpm test`, in memory | Each function and choice in isolation, including every failure with its exact identifier |
| Scenario | `dpm test`, in memory | End-to-end flows: create, request, execute, cancel, pause, add assets, across both modes |
| Ledger | Local Canton sandbox, protocol versions 34 and 35, through the Ledger API | The same scenarios on a real node, including error shapes and disclosure |
| Differential | Python `decimal` oracle at 200-digit precision versus Daml | Math results and failures match exactly |
| Sequence | Seeded random operation sequences in Daml Script | Invariants I-01 to I-08 and V-01 to V-05 after every step |
| Mutation | Scripted source mutations | Every guard and every rounding decision is observed by at least one test |
| Proof | Z3 on an integer model | M-01 to M-07 hold for the specification |
| Static | SDK `damlc lint`, OpenZeppelin daml-lint, repository checks | Conventions, bounded fields, guarded division |

The SDK matrix for the build and the in-memory tests is SDK 3.4.11, 3.5.8 and 3.5.10, selected with `DPM_SDK_VERSION`; `multi-package.yaml` pins 3.4.11. API packages are built by SDK 3.4.11 only, and their package IDs are recorded in `dars/api-packages.yaml` (D-11). Every package targets Daml-LF 2.1. The sandbox runs (Q-05), the demo (`scripts/demo.sh`) and the upgrade check (Q-14) use SDK 3.4.11 (Canton 3.4.11, protocol version 34) and SDK 3.5.10 (Canton 3.5.17, protocol version 35).

## 2. Test fixtures

- **Underlying registry:** Splice `splice-test-token-v2` 1.0.1 at tag 0.8.4. Its DAR is vendored in `dars/vendor/` and recorded in `dars/manifest.yaml`, and `scripts/check-token-dars.sh` verifies it (Q-16).
- **Hostile fixtures:** a forged allocation template (T-06), a forged factory (T-20), an operator that archives and recreates state (T-11), an operator that settles a request's input leg alone (T-21), a second vault of the same operator (T-04).
- **Parties:** operator, at least three requesters, an outsider, and a second operator.
- Fixture identifiers use `example.com/...`; examples use `myapp.com/...`.

## 3. Rules for writing tests

1. Negative tests use `trySubmit` and assert the result with the failure helper of rule 2: the exact `errorId` and category for a `failWithStatus` failure, `Authorization` for an authorization failure. No bare `submitMustFail`, and no other way of asserting a failure.
2. The failure helper is `Cayvox.Testing.Assert`: `matches` and `assertFails` over `Expected`. Its one canonical source is `test/shared/Cayvox/Testing/Assert.daml`. Each test package that needs it carries its own copy at `daml/Cayvox/Testing/Assert.daml`, byte-identical to the canonical source; gate Q-02 fails on any difference (`scripts/check.sh`). The helper is changed only in the canonical source, and every copy is refreshed in the same commit. It uses only the public `Daml.Script` module: `ContractUnavailable` (a contract not visible or archived), `WrongTemplate`, `PreconditionViolated` and `StaleDisclosure`, and `assertActive`, `assertArchived` and `assertNotVisible`, which observe a contract's state through `queryContractId` for a stakeholder. It matches a `failWithStatus` failure whole or truncated (category code 8 or 9), an unhandled exception through its `UNHANDLED_EXCEPTION/...` identifier (`generalError`, `assertionFailed`), and each ledger shape, identically in memory and on the sandbox; the helper's doc comment lists the shapes. Upstream failures are asserted by their own identifier or by `generalError`, never by message text. A negative test also checks that the helper rejects at least one wrong expectation.
3. Test the component, not Daml itself.
4. Every guard has a test that fails when the guard is removed, and a test at each boundary: equal, one unit above and one unit below.
5. Test names state the behaviour: `test_vault_paused_refusesDeposits`.
6. Every documented hazard has a fixture.

## 4. Quality gates

A change is ready when every gate passes. Each gate states what it checks and the command or method that checks it.

| Gate | Requirement | Command or method |
|---|---|---|
| Q-01 | Builds with zero errors on SDK 3.4.11, 3.5.8 and 3.5.10 at `--target=2.1`; API packages are built by SDK 3.4.11 and keep the package IDs recorded in `dars/api-packages.yaml` (D-11) | `scripts/build-all.sh` per SDK, then `scripts/check-api-ids.sh` |
| Q-02 | Repository convention checks pass: required files, package boundaries, test and example package rules, no `exposed-modules`, no `daml-script` in production | `scripts/check.sh`, a port of canton-contracts [`scripts/check.sh`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/scripts/check.sh) |
| Q-03 | Template and choice coverage: every production template created and every choice exercised (100%) | `scripts/check-coverage.sh`, a port of canton-contracts [`scripts/check-coverage.sh`](https://github.com/OpenZeppelin/canton-contracts/blob/aeca01d043311d8ccc8ab7cda4d7c16e682429fa/scripts/check-coverage.sh), whose zero checks count the production package's own templates and choices; the choices of implemented interfaces, which DPM does not count, are derived from the DARs and checked against the test run's saved coverage by `scripts/check-interface-coverage.py`, with the maintained list in `docs/INTERFACE-CHOICES.md` as a cross-check that must match the derived set |
| Q-04 | Every error in SPEC §7 and MATH §4 has a passing negative test with the exact identifier | Test inventory derived from the error table; the tests run with Q-03 |
| Q-05 | All scenario tests pass on each SDK's own sandbox, with that SDK's build and client: SDK 3.4.11 (Canton 3.4.11, protocol version 34) and SDK 3.5.10 (Canton 3.5.17, protocol version 35); and the DAR built by SDK 3.4.11 also passes on the protocol version 35 sandbox with the SDK 3.5.10 client | `scripts/check-sandbox.sh` |
| Q-06 | Differential math: every edge vector in MATH plus at least 20,000 seeded random vectors, zero mismatches, on every SDK of the matrix | `scripts/check-math-oracle.sh` (`scripts/math-oracle.py`) |
| Q-07 | Mutation: zero surviving mutants across guards, rounding directions, bounds and ordering, with the full mutant list in the script's output | `scripts/mutate-math.py`, `scripts/mutate-registry.py` |
| Q-08 | Sequences: at least 1,000 seeded sequences of up to 50 operations, invariants checked after every step, zero violations | `scripts/check-sequences.sh` (`scripts/check-sequences.py`) |
| Q-09 | Z3 proofs of M-01 to M-07 on the integer model | `scripts/check-math-proofs.sh` (`scripts/prove-math.py`) |
| Q-10 | `damlc lint` clean; OpenZeppelin daml-lint at the pinned revision clean, or each finding justified | `scripts/check-lint.sh`; `scripts/check-daml-lint.sh`, with the justifications in `scripts/daml-lint-justified.tsv` |
| Q-11 | Documentation complete: every template and interface documents the items of `docs/CONVENTIONS.md`, section 7; every package has a README with the sections listed there; the docs page `docs/site/vault.mdx` has `title` and `description` front matter | `scripts/check-docs.sh` for the parts a script can check; a reviewer checks the topics of each doc comment |
| Q-12 | Style: no em or en dashes; no absolute paths; no usernames | `scripts/check-style.sh` |
| Q-13 | Independent review: every package is reviewed by two independent reviewers; each finding is fixed in its own commit and listed | Review log |
| Q-14 | Upgrade: `dpm upgrade-check` passes between the release candidate and a compatible patch candidate, and fails as expected for a known breaking change | `scripts/check-upgrade.sh` |
| Q-15 | Rename: the D-17 rename produces a tree that passes Q-01 to Q-05 | `scripts/check-rename.sh` (`scripts/rename-d17.py`) |
| Q-16 | Token DAR identity: every third-party DAR under `dars/vendor/` has an entry in `dars/manifest.yaml` whose SHA-256, main package ID, name, version and package-ID closure match the file; the file is byte-identical to its upstream path at the recorded Splice tag, and the tag resolves to the recorded commit; a Splice token standard API or utils DAR has the main package ID pinned in `dars/token-standard-pins.txt` (D-03); and every Splice DAR named in a data-dependency of a package of this repository is a manifest file | `scripts/check-token-dars.sh`, which reads its pinned IDs from `dars/` |

## 5. Continuous integration

The GitHub workflow (`.github/workflows/ci.yml`) runs on every push to `main` and on every pull request. It runs Q-12, Q-16 and Q-02 once, and on every SDK of the matrix Q-01 and the in-memory unit tests with coverage (Q-03), the example tests and the tool tests.

The local CI script, `scripts/ci.sh`, runs every scripted gate in one run, ordered to fail fast: Q-12, Q-16 and Q-02; Q-01 and `damlc lint` (Q-10) on every SDK of the matrix, then daml-lint (Q-10), Q-09 and Q-11; the in-memory suites on every SDK of the matrix (Q-03 with the unit and scenario tests, Q-06, Q-08, the example and tool tests, and the Q-07 mutant precheck); the sandbox suites (Q-05 and the demo) on SDK 3.4.11 and 3.5.10; Q-14 on SDK 3.4.11 and 3.5.10; and Q-15 last. `CI_FROM` resumes from a stage. The sandbox (Q-05), sequence (Q-08), mutation (Q-07), proof (Q-09), upgrade (Q-14) and rename (Q-15) gates run locally, because they need long runs or a local Canton sandbox with fixed ports. The full Q-07 mutation runs through `scripts/mutate-math.py` and `scripts/mutate-registry.py`, and Q-13 is a review, not a script.
