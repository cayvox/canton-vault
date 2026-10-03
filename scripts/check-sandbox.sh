#!/usr/bin/env bash
# Gate Q-05: every test script of the test packages passes on a Canton
# sandbox (docs/TESTING.md, Q-05), in three runs:
#   1. DAR, client and sandbox of SDK 3.4.11 (Canton 3.4.11, protocol version 34);
#   2. DAR, client and sandbox of SDK 3.5.10 (Canton 3.5.17, protocol version 35);
#   3. the DAR built by SDK 3.4.11 on the SDK 3.5.10 sandbox with the SDK 3.5.10
#      client (the SDK 3.4.11 client does not work against that sandbox).
# Each run builds the packages with the DAR's SDK from clean outputs, starts a
# fresh sandbox with static time, uploads each test DAR and runs every script
# with `dpm script --all`. Any FAILURE fails the gate. The sandbox runs in its
# own process group and is stopped as a group, as in canton-contracts
# scripts/check-sandbox.sh at a2d5763.
#
# Usage: scripts/check-sandbox.sh [test package ...]   (default: every test package)
#   SANDBOX_PORT  optional: the Ledger API port (default 16865)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${SANDBOX_PORT:-16865}"
WORK="$ROOT/test-reports/sandbox"
rm -rf "$WORK"; mkdir -p "$WORK"

if [ "$#" -gt 0 ]; then TESTS=("$@"); else
	TESTS=()
	while IFS= read -r dir; do TESTS+=("$dir"); done < <(sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml | grep '^test/')
fi

fail() { printf 'sandbox: %s\n' "$*" >&2; exit 1; }
pgid=""
stop() {
	if [ -n "$pgid" ] && kill -0 "-$pgid" 2>/dev/null; then
		kill -TERM -- "-$pgid" 2>/dev/null || true
		for _ in $(seq 1 30); do
			kill -0 "-$pgid" 2>/dev/null || break
			sleep 1
		done
		kill -KILL -- "-$pgid" 2>/dev/null || true
	fi
	pgid=""
	for _ in $(seq 1 30); do
		lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || return 0
		sleep 1
	done
	printf 'sandbox: port %s still in use\n' "$PORT" >&2
	return 1
}
trap stop EXIT

# The SDK that builds a package: API packages always 3.4.11, every other
# package the SDK of the run (D-11, as in scripts/ci.sh).
build_sdk() {
	case "$(sed -n 's/^name:[[:space:]]*//p' "$1/daml.yaml")" in
	*-test) printf '%s' "$2" ;;
	*-api-*) printf '3.4.11' ;;
	*) printf '%s' "$2" ;;
	esac
}

build_all() { # sdk
	local dir sdk
	while IFS= read -r dir; do rm -rf "$dir/.daml"; done < <(sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml)
	while IFS= read -r dir; do
		# The SDK is chosen before the cd: build_sdk reads $dir/daml.yaml
		# relative to the repository root.
		sdk="$(build_sdk "$dir" "$1")"
		(cd "$dir" && DPM_SDK_VERSION="$sdk" dpm build --enable-multi-package=no) > "$WORK/build-$1.txt" 2>&1 ||
			{ cat "$WORK/build-$1.txt"; return 1; }
	done < <(sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml)
	# D-11: the API packages these DARs consume are the 3.4.11 builds with
	# their recorded IDs.
	scripts/check-api-ids.sh || return 1
	for dir in "${TESTS[@]}"; do cp "$dir"/.daml/dist/*.dar "$WORK/$(basename "$dir")-$1.dar"; done
}

start_sandbox() { # sdk
	local logdir="$WORK/sandbox-$1-$2"
	mkdir -p "$logdir"
	lsof -tiTCP:"$PORT" -sTCP:LISTEN > /dev/null 2>&1 && fail "port $PORT is in use"
	set -m
	(cd "$logdir" && exec env DPM_SDK_VERSION="$1" dpm sandbox --static-time --ledger-api-port "$PORT" > sandbox.out 2>&1) &
	pgid=$!
	set +m
	disown "$pgid"
	for _ in $(seq 1 600); do
		grep -q 'Canton sandbox is ready' "$logdir/sandbox.out" 2>/dev/null && break
		kill -0 "$pgid" 2>/dev/null || break
		sleep 1
	done
	grep -q 'Canton sandbox is ready' "$logdir/sandbox.out" || fail "sandbox of SDK $1 did not start"
	printf 'sandbox: SDK %s, %s\n' "$1" "$(grep -hoE 'protocol version = [0-9]+' "$logdir/log/canton.log" | head -n 1)"
}

run() { # dar-sdk sandbox-and-client-sdk
	local darsdk="$1" sdk="$2" dir out successes failures status=0
	start_sandbox "$sdk" "$darsdk"
	for dir in "${TESTS[@]}"; do
		out="$WORK/$(basename "$dir")-dar$darsdk-client$sdk.txt"
		DPM_SDK_VERSION="$sdk" dpm script --dar "$WORK/$(basename "$dir")-$darsdk.dar" --all --upload-dar true \
			--static-time --ledger-host localhost --ledger-port "$PORT" > "$out" 2>&1
		successes="$(grep -c ' SUCCESS$' "$out")"
		failures="$(grep -c ' FAILURE' "$out")"
		printf 'sandbox: %s, DAR of SDK %s, client and sandbox of SDK %s: %s SUCCESS, %s FAILURE\n' \
			"$dir" "$darsdk" "$sdk" "$successes" "$failures"
		grep ' FAILURE' "$out" | cut -c1-300 >&2
		{ [ "$failures" -eq 0 ] && [ "$successes" -gt 0 ]; } || status=1
	done
	stop
	return "$status"
}

status=0
build_all 3.4.11 || fail "build with SDK 3.4.11 failed"
run 3.4.11 3.4.11 || status=1
run 3.4.11 3.5.10 || status=1
build_all 3.5.10 || fail "build with SDK 3.5.10 failed"
run 3.5.10 3.5.10 || status=1
[ "$status" -eq 0 ] || fail "a script failed on a sandbox"
printf 'sandbox: OK\n'
