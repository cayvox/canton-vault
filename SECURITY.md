# Security policy

## Status

This code has not been audited. It is a proposed contribution to the OpenZeppelin Canton contracts library, and it is not intended for production use. The open questions to answer before any production deployment are listed in [`docs/SECURITY.md`](docs/SECURITY.md#6-open-questions-before-production-use).

## Reporting a vulnerability

Report a suspected vulnerability through [GitHub private vulnerability reporting](https://github.com/cayvox/canton-vault/security/advisories/new). Do not disclose it in a public issue, discussion or pull request.

A useful report names the package and the commit, the steps that reproduce the problem (a Daml Script test is ideal), the behaviour you expected and the behaviour you observed, and the ledger and topology assumptions it depends on, such as which parties host which participants and who discloses which contracts.

## Scope

In scope are the three production packages under `packages/`: `cvx-vault-math-v1`, `cvx-api-vault-v1` and `cvx-vault-v1`. The vault's trust model, its threat catalogue and the properties each threat is tested against are in [`docs/SECURITY.md`](docs/SECURITY.md). A finding that shows a stated property does not hold is in scope; so is a property the documents should state and do not.

The example under `examples/`, the reconciliation tool under `tools/`, the test packages and the scripts are never released. Problems in them are welcome as ordinary issues.

Out of scope are the choices that belong to the application deploying the vault: which contracts it treats as canonical, how it binds parties and participants, what it discloses to whom, which packages its participants vet, and how it configures its synchronizer.
