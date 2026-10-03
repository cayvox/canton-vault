#!/usr/bin/env bash
# Local CI: every gate of docs/TESTING.md that a script runs, in one run,
# ordered to fail fast, and stopping at the first failure:
#
#   static   Q-12 style, Q-16 token DARs, Q-02 conventions (once)
#   build    per SDK: Q-01 build and Q-10 damlc lint; then Q-10 daml-lint,
#            Q-09 math proofs and Q-11 documentation (once)
#   memory   per SDK: Q-03 unit tests with coverage, Q-06 differential
#            math, Q-08 sequences, the example tests and the tool tests; then
#            the Q-07 mutant precheck (once)
#   sandbox  Q-05 on the protocol version 34 and 35 sandboxes, then the
#            demo on each SDK's sandbox
#   upgrade  Q-14 per SDK
#   rename   Q-15: the renamed tree through Q-01 to Q-04 on every SDK of the
#            matrix and Q-05 on the sandboxes
#
# The build and in-memory stages run SDK 3.4.11, 3.5.8 and 3.5.10 in turn; the
# sandbox and upgrade stages run SDK 3.4.11 and 3.5.10 (D-11). Q-07's full mutation runs
# and Q-13's reviews run at phase exits (scripts/mutate-math.py,
# scripts/mutate-registry.py; the phase report).
#
# The SDK is selected with DPM_SDK_VERSION, which overrides the sdk-version of
# every daml.yaml (https://docs.canton.network/appdev/modules/m5-environment-configuration).
# A build does not recompile outputs left by another SDK, so Q-01 removes the
# package build directories first, builds API packages with SDK 3.4.11 and
# every other package with the SDK of the run (D-11), and checks the
# `Sdk-Version` and Daml-LF version of every DAR and the recorded API package
# IDs (ARCHITECTURE.md, section 4; scripts/check-api-ids.sh).
#
# Run it on a host that cannot sleep: `caffeinate -dimsu scripts/ci.sh` on
# macOS, with the lid open: a sleeping host stops the sandbox.
#
# Usage: scripts/ci.sh
#   CI_SDKS          optional: the SDKs of the build and memory stages
#                    (default "3.4.11 3.5.8 3.5.10")
#   CI_SANDBOX_SDKS  optional: the SDKs of the demo and Q-14
#                    (default "3.4.11 3.5.10")
#   CI_FROM          optional: the stage to start from, to resume after a
#                    failure (static, build, memory, sandbox, upgrade, rename)
#   SPLICE_CHECKOUT  optional: passed to scripts/check-token-dars.sh
#   DAML_LINT_CHECKOUT  optional: passed to scripts/check-daml-lint.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SDKS="${CI_SDKS:-3.4.11 3.5.8 3.5.10}"
SANDBOX_SDKS="${CI_SANDBOX_SDKS:-3.4.11 3.5.10}"

# Every run keeps the Canton log and the script output of each Q-05 sandbox
# run, compressed, in ci-logs/<UTC time>-<commit>/, which no script deletes,
# so that a rejection seen in any run can be read afterwards. The
# directory is ignored by git; the style gate still reads it, so the logs are
# compressed by xz_clean (scripts/xz-clean.sh).
# shellcheck source=scripts/xz-clean.sh
. scripts/xz-clean.sh
RUN_STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
retain_logs() {
	local status=$? dest="ci-logs/$RUN_STAMP" f
	if [ -d test-reports/sandbox ]; then
		mkdir -p "$dest"
		while IFS= read -r f; do
			mkdir -p "$dest/$(dirname "${f#test-reports/sandbox/}")"
			xz_clean "$f" "$dest/${f#test-reports/sandbox/}.xz"
		done < <(find test-reports/sandbox \( -name canton.log -o -name 'sandbox.out' -o -name '*.txt' \) -type f)
		printf 'ci: sandbox logs kept in %s\n' "$dest"
	fi
	exit "$status"
}
trap retain_logs EXIT

step() {
	local gate="$1"
	shift
	printf '\n== %s, SDK %s: %s\n' "$gate" "$DPM_SDK_VERSION" "$*"
	if ! "$@"; then
		printf '\nci: FAIL %s on SDK %s\n' "$gate" "$DPM_SDK_VERSION" >&2
		exit 1
	fi
}

# Q-01 (scripts/build-all.sh).
build_all() {
	scripts/build-all.sh
}

# The unit tests of every test package, with template and choice coverage;
# the recorded API package IDs are checked again afterwards, so a test run
# cannot rebuild an API package unnoticed (D-11).
tests_and_coverage() {
	scripts/check-coverage.sh && scripts/check-api-ids.sh
}

STAGES="static build memory sandbox upgrade rename"
FROM="${CI_FROM:-static}"
case " $STAGES " in *" $FROM "*) ;; *) printf 'ci: unknown stage %s\n' "$FROM" >&2; exit 2 ;; esac
started=""
stage() { # name: whether to run it
	[ "$1" = "$FROM" ] && started=1
	if [ -n "$started" ]; then printf '\nci: stage %s\n' "$1"; return 0; fi
	printf '\nci: stage %s skipped (CI_FROM=%s)\n' "$1" "$FROM"
	return 1
}
built=""

printf 'ci: dpm %s, run %s\n' "$(dpm -v 2>&1 | sed -n 's/^version: //p')" "$RUN_STAMP"

if stage static; then
	export DPM_SDK_VERSION=3.4.11
	step Q-12 scripts/check-style.sh
	step Q-16 scripts/check-token-dars.sh
	step Q-02 scripts/check.sh
fi

if stage build; then
	for sdk in $SDKS; do
		export DPM_SDK_VERSION="$sdk"
		printf '\nci: SDK %s, active SDK reported by dpm: %s\n' "$sdk" "$(dpm version --active)"
		step Q-01 build_all
		built="$sdk"
		step Q-10 scripts/check-lint.sh
	done
	step Q-10 scripts/check-daml-lint.sh ${DAML_LINT_CHECKOUT:+"$DAML_LINT_CHECKOUT"}
	step Q-09 scripts/check-math-proofs.sh
	step Q-11 scripts/check-docs.sh
fi

if stage memory; then
	for sdk in $SDKS; do
		export DPM_SDK_VERSION="$sdk"
		[ "$built" = "$sdk" ] || { step Q-01 build_all; built="$sdk"; }
		step Q-03 tests_and_coverage
		step Q-06 scripts/check-math-oracle.sh
		step Q-08 scripts/check-sequences.sh
		step examples scripts/check-examples.sh
		step tools scripts/check-tools.sh
		step Q-01 scripts/check-api-ids.sh
	done
	# Every run checks that each mutant still applies to the current
	# sources, so a code change cannot silently retire one.
	step Q-07 python3 scripts/mutate-registry.py --check-only
fi

if stage sandbox; then
	# Q-05 builds and runs both SDKs itself (scripts/check-sandbox.sh).
	export DPM_SDK_VERSION=3.5.10
	step Q-05 scripts/check-sandbox.sh
	for sdk in $SANDBOX_SDKS; do
		export DPM_SDK_VERSION="$sdk"
		step demo scripts/demo.sh
	done
fi

if stage upgrade; then
	for sdk in $SANDBOX_SDKS; do
		export DPM_SDK_VERSION="$sdk"
		step Q-14 scripts/check-upgrade.sh
	done
fi

if stage rename; then
	export DPM_SDK_VERSION=3.5.10
	step Q-15 scripts/check-rename.sh
fi

printf '\nci: OK (SDKs: %s; sandbox SDKs: %s; from stage %s)\n' "$SDKS" "$SANDBOX_SDKS" "$FROM"
