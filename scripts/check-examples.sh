#!/usr/bin/env bash
# Runs the consumer examples: each example -test package integrates a
# production DAR through data-dependencies and carries Daml Script tests.
#
# Ported from OpenZeppelin/canton-contracts scripts/check-examples.sh at commit
# a2d576344fe96d49751b276e8c638e02ef682c57.
# Copyright (c) 2026 OpenZeppelin. MIT License; the full license text is in
# LICENSES/canton-contracts-MIT.txt.
#
# Changes from the source: the script reports and exits 0 when examples/ does
# not exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
	printf 'examples: %s\n' "$*" >&2
	exit 1
}

if [ ! -d examples ]; then
	printf 'examples: no examples/ directory, nothing to run\n'
	exit 0
fi

manifests="$(find examples -type d -name .daml -prune -o -name daml.yaml -type f -print | sort)" ||
	fail "failed to discover example package manifests"
[ -n "$manifests" ] || fail "no example package manifests found"

example_count=0
while IFS= read -r manifest; do
	package_dir="$(dirname "$manifest")"
	package_name="$(sed -n 's/^name:[[:space:]]*//p' "$manifest")"

	case "$package_name" in
	*-test) ;;
	*) continue ;;
	esac

	grep -Eq '^[[:space:]]*-[[:space:]]*(\.\./)+packages/.+\.dar$' "$manifest" ||
		fail "example $package_dir must data-depend on a production DAR"

	printf 'examples: running %s\n' "$package_dir"
	DAML_PACKAGE="$package_dir" dpm test --all
	example_count=$((example_count + 1))
done <<< "$manifests"

printf 'examples: OK (%d examples)\n' "$example_count"
