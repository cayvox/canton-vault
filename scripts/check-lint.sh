#!/usr/bin/env bash
# Lints every Daml package declared by the workspace with the SDK's damlc lint.
#
# Ported from OpenZeppelin/canton-contracts scripts/check-lint.sh at commit
# a2d576344fe96d49751b276e8c638e02ef682c57.
# Copyright (c) 2026 OpenZeppelin. MIT License; the full license text is in
# LICENSES/canton-contracts-MIT.txt.
#
# Changes from the source: the SDK follows DPM_SDK_VERSION when it is set
# (https://docs.canton.network/appdev/modules/m5-environment-configuration),
# except for API packages, which are linted with SDK 3.4.11, the SDK that
# builds them in every run (D-11): linting one with another SDK fails on its
# data-dependencies' package database.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
	printf 'lint: %s\n' "$*" >&2
	exit 1
}

package_paths="$(sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml)" ||
	fail "failed to read package paths from multi-package.yaml"
[ -n "$package_paths" ] || fail "multi-package.yaml declares no packages"

package_count=0
while IFS= read -r package_path; do
	[ -f "$package_path/daml.yaml" ] || fail "missing $package_path/daml.yaml"

	printf 'lint: checking %s\n' "$package_path"
	case "$(sed -n 's/^name:[[:space:]]*//p' "$package_path/daml.yaml")" in
	*-test) sdk="${DPM_SDK_VERSION:-}" ;;
	*-api-*) sdk=3.4.11 ;;
	*) sdk="${DPM_SDK_VERSION:-}" ;;
	esac
	if [ -n "$sdk" ]; then
		DAML_PACKAGE="$package_path" DPM_SDK_VERSION="$sdk" dpm damlc lint
	else
		DAML_PACKAGE="$package_path" dpm damlc lint
	fi
	package_count=$((package_count + 1))
done <<< "$package_paths"

printf 'lint: OK (%d packages)\n' "$package_count"
