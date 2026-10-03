#!/usr/bin/env bash
# The demo: the full flow of the admission example on a
# Canton sandbox, printing each step. Runs from a clean checkout: it builds
# the packages the demo needs (the API package with SDK 3.4.11, D-11),
# starts the sandbox of the chosen SDK on its own port, uploads the example
# test DAR and runs Example.VaultAdmissionV1Test:demo against it.
#
# Prerequisites: dpm with SDK 3.4.11 and 3.5.10 installed (`dpm install
# 3.4.11`, `dpm install 3.5.10`), and jq, unzip and lsof. The sandbox binds
# fixed admin, JSON API, sequencer and mediator ports (6864, 6866 to 6869)
# besides its Ledger API port, so no other sandbox may run at the same time.
# The script rebuilds the packages it needs in place, with the chosen SDK:
# afterwards, build with scripts/ci.sh, or remove each .daml/ before
# building with another SDK.
#
# Usage: scripts/demo.sh
#   DPM_SDK_VERSION  the SDK (default 3.5.10, protocol version 35)
#   DEMO_PORT        Ledger API port of the sandbox (default 16915)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SDK="${DPM_SDK_VERSION:-3.5.10}"
PORT="${DEMO_PORT:-16915}"
WORK="$(mktemp -d)"

pgid=""
stop() {
	if [ -n "$pgid" ] && kill -0 "-$pgid" 2>/dev/null; then
		kill -TERM -- "-$pgid" 2>/dev/null || true
		for _ in $(seq 1 30); do kill -0 "-$pgid" 2>/dev/null || break; sleep 1; done
		kill -KILL -- "-$pgid" 2>/dev/null || true
	fi
	rm -rf "$WORK"
}
trap stop EXIT

say() { printf 'demo: %s\n' "$*"; }

for tool in dpm jq unzip lsof; do
	command -v "$tool" > /dev/null || { say "$tool is required"; exit 1; }
done
for port in 6864 6866 6867 6868 6869; do
	if lsof -tiTCP:"$port" -sTCP:LISTEN > /dev/null 2>&1; then say "port $port is in use: another sandbox is running"; exit 1; fi
done

say "building with SDK $SDK"
for dir in packages/utils/vault-math-v1 packages/token/api-vault-v1 packages/token/vault-v1 \
	examples/vault-admission-v1 examples/vault-admission-v1-test; do
	sdk="$SDK"
	[ "$dir" = packages/token/api-vault-v1 ] && sdk=3.4.11
	rm -rf "$dir/.daml"
	(cd "$dir" && DPM_SDK_VERSION="$sdk" dpm build --enable-multi-package=no) > "$WORK/build.txt" 2>&1 ||
		{ cat "$WORK/build.txt" >&2; say "build of $dir failed"; exit 1; }
done
scripts/check-api-ids.sh > /dev/null || { say "the API package ID differs from the recorded one"; exit 1; }
dar=examples/vault-admission-v1-test/.daml/dist/com-example-vault-admission-v1-test-0.0.0.dar

say "starting the sandbox of SDK $SDK on port $PORT"
if lsof -tiTCP:"$PORT" -sTCP:LISTEN > /dev/null 2>&1; then say "port $PORT is in use"; exit 1; fi
set -m
(cd "$WORK" && exec env DPM_SDK_VERSION="$SDK" dpm sandbox --ledger-api-port "$PORT" > sandbox.out 2>&1) &
pgid=$!
set +m
for _ in $(seq 1 600); do
	grep -q 'Canton sandbox is ready' "$WORK/sandbox.out" 2>/dev/null && break
	kill -0 "$pgid" 2>/dev/null || break
	sleep 1
done
grep -q 'Canton sandbox is ready' "$WORK/sandbox.out" || { cat "$WORK/sandbox.out" >&2; say "the sandbox did not start"; exit 1; }
say "protocol version $(grep -ohE 'protocol version [0-9]+' "$WORK/log/canton.log" 2>/dev/null | head -1 | grep -oE '[0-9]+$' || printf 'unknown')"

say "running the flow"
DPM_SDK_VERSION="$SDK" dpm script --dar "$dar" --script-name Example.VaultAdmissionV1Test:demo \
	--upload-dar true --ledger-host localhost --ledger-port "$PORT" > "$WORK/script.txt" 2>&1 ||
	{ cat "$WORK/script.txt" >&2; say "the flow failed"; exit 1; }
sed -n 's/^\[DA.Internal.Prelude:[0-9]*\]: //p' "$WORK/script.txt"
say "done"
