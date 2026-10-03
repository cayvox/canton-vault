#!/usr/bin/env bash
# Gate Q-08: seeded operation sequences on the vault (docs/TESTING.md).
# Builds the vault package and its tests with the SDK in use (the API
# package with SDK 3.4.11, D-11) unless the test DAR already records it, then
# runs the sequences (scripts/check-sequences.py).
#
# Usage: scripts/check-sequences.sh
#   DPM_SDK_VERSION   the SDK (default: the workspace SDK, 3.4.11)
#   SEQUENCE_COUNT    optional: number of sequences (default 1000)
#   SEQUENCE_JOBS     optional: parallel runs (default 8)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SDK="${DPM_SDK_VERSION:-3.4.11}"
DAR=test/vault-v1-test/.daml/dist/cvx-vault-v1-test-0.0.0.dar

built_by() { unzip -p "$1" META-INF/MANIFEST.MF 2>/dev/null | tr -d '\r' | sed -n 's/^Sdk-Version: //p'; }
if [ "$(built_by "$DAR")" != "$SDK" ]; then
	rm -rf packages/token/api-vault-v1/.daml packages/token/vault-v1/.daml test/vault-v1-test/.daml
	(cd packages/token/api-vault-v1 && DPM_SDK_VERSION=3.4.11 dpm build --enable-multi-package=no) > /dev/null
	(cd packages/token/vault-v1 && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
	(cd test/vault-v1-test && DPM_SDK_VERSION="$SDK" dpm build --enable-multi-package=no) > /dev/null
fi
printf 'sequences: %s built by SDK %s\n' "$DAR" "$(built_by "$DAR")"
python3 scripts/check-sequences.py --dar "$DAR" --sdk "$SDK" \
	--count "${SEQUENCE_COUNT:-1000}" --jobs "${SEQUENCE_JOBS:-8}"
