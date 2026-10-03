#!/usr/bin/env bash
# Gate Q-06: the differential math suite (docs/TESTING.md). Builds the math
# test package with the SDK in use, confirms that the edge vectors drive every
# path of Algorithm D, then compares `mulDiv` with the Python `decimal`
# oracle on every edge vector and on seeded random vectors
# (scripts/math-oracle.py). It then compares the six conversion functions of
# `cvx-vault-v1` with the exact model of docs/MATH.md section 7, on edge
# vectors and seeded random vectors over k from 0 to 10, through the vault
# test package built with the same SDK (the API package with SDK 3.4.11,
# D-11).
#
# Usage: scripts/check-math-oracle.sh
#   DPM_SDK_VERSION   the SDK (default: the workspace SDK, 3.4.11)
#   ORACLE_SEED       optional: seed of the random vectors (default 20260930)
#   ORACLE_RANDOM     optional: number of random vectors (default 20000)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SDK="${DPM_SDK_VERSION:-3.4.11}"
PKG=packages/utils/vault-math-v1
TEST=test/vault-math-v1-test
DAR="$TEST/.daml/dist/cvx-vault-math-v1-test-0.0.0.dar"

# Build the package and its tests with this SDK unless both DARs already
# record it (a build does not recompile the other SDK's output).
built_by() { unzip -p "$1" META-INF/MANIFEST.MF 2>/dev/null | tr -d '\r' | sed -n 's/^Sdk-Version: //p'; }
if [ "$(built_by "$PKG/.daml/dist/cvx-vault-math-v1-0.1.0.dar")" != "$SDK" ] || [ "$(built_by "$DAR")" != "$SDK" ]; then
	rm -rf "$PKG/.daml" "$TEST/.daml"
	(cd "$PKG" && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
	(cd "$TEST" && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
fi
printf 'oracle: %s built by SDK %s\n' "$DAR" "$(built_by "$DAR")"

python3 scripts/math-oracle.py paths
python3 scripts/math-oracle.py check --dar "$DAR" --sdk "$SDK" \
	--seed "${ORACLE_SEED:-20260930}" --random "${ORACLE_RANDOM:-20000}"

VAULT_DAR=test/vault-v1-test/.daml/dist/cvx-vault-v1-test-0.0.0.dar
if [ "$(built_by "$VAULT_DAR")" != "$SDK" ]; then
	rm -rf packages/token/api-vault-v1/.daml packages/token/vault-v1/.daml test/vault-v1-test/.daml
	(cd packages/token/api-vault-v1 && DPM_SDK_VERSION=3.4.11 dpm build --enable-multi-package=no) > /dev/null
	(cd packages/token/vault-v1 && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
	(cd test/vault-v1-test && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
fi
printf 'oracle: %s built by SDK %s\n' "$VAULT_DAR" "$(built_by "$VAULT_DAR")"
python3 scripts/math-oracle.py check-conversion --dar "$VAULT_DAR" --sdk "$SDK" \
	--seed "${ORACLE_SEED:-20260930}" --random "${ORACLE_RANDOM:-20000}"
printf 'oracle: OK (SDK %s)\n' "$SDK"
