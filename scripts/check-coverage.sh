#!/usr/bin/env bash
# Gate Q-03: production package tests and DPM template and choice coverage.
#
# Ported from OpenZeppelin/canton-contracts scripts/check-coverage.sh at commit
# aeca01d043311d8ccc8ab7cda4d7c16e682429fa.
# Copyright (c) 2026 OpenZeppelin. MIT License; the full license text is in
# LICENSES/canton-contracts-MIT.txt.
#
# Changes from the source: the tree pairs packages:test and examples:examples,
# as in scripts/check.sh (this repository has no experiments/ tree); reports
# go to a directory named by the SDK in use, so every SDK can run in one tree;
# the zero checks count only the production package's own templates and
# choices, because a test package may also depend on third-party fixture DARs
# (Splice TestTokenV2) whose unused templates are not the package's coverage
# (docs/TESTING.md, Q-03: "every production template created and every choice
# exercised"); the choices of implemented interfaces, which DPM does not
# count, are derived from the DARs and checked against the saved coverage by
# scripts/check-interface-coverage.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REPORTS="test-reports/${DPM_SDK_VERSION:-workspace-sdk}"
mkdir -p "$REPORTS"

# Trees under policy as "<source tree>:<test tree>" pairs; keep in sync with
# scripts/check.sh.
TREES=("packages:test" "examples:examples")

fail() {
	printf 'coverage: %s\n' "$*" >&2
	exit 1
}

# Print the relative path from directory $1 to directory $2. Both arguments
# are normalized paths relative to the repository root, and neither contains
# the other. Portable replacement for GNU `realpath --relative-to`, which the
# BSD realpath on macOS does not support.
relpath() {
	local from="$1"
	local to="$2"
	local up=""

	while [ "${from%%/*}" = "${to%%/*}" ] &&
		[ "$from" != "${from#*/}" ] && [ "$to" != "${to#*/}" ]; do
		from="${from#*/}"
		to="${to#*/}"
	done
	while :; do
		up="../$up"
		case "$from" in
		*/*) from="${from#*/}" ;;
		*) break ;;
		esac
	done
	printf '%s%s' "$up" "$to"
}

# Fail when the metric lists an entry of the production package. DPM prints
# "  <metric>: <n>" followed by one indented "    <package>:<module>:<name>"
# line per entry.
check_zero() {
	local report="$1"
	local metric="$2"
	local package="$3"
	local value="" own=""

	value="$(sed -n "s/^  ${metric}: //p" "$report")"
	[ -n "$value" ] || fail "DPM metric not found in $report: $metric"
	own="$(awk -v m="  $metric:" -v p="    $package:" '
		index($0, m) == 1 { inlist = 1; next }
		inlist && index($0, "    ") == 1 { if (index($0, p) == 1) { n++; print > "/dev/stderr" }; next }
		{ inlist = 0 }
		END { print n + 0 }' "$report")"
	[ "$own" -eq 0 ] || fail "$metric: $own of $package ($report)"
	printf 'coverage: %s: %s in %s (of %s listed)\n' "$metric" "$own" "$package" "$value"
}

package_count=0

for tree_pair in "${TREES[@]}"; do
	source_tree="${tree_pair%%:*}"
	test_tree="${tree_pair##*:}"

	[ -d "$source_tree" ] || continue
	excluded_tree="$test_tree"
	if [ "$source_tree" = "$test_tree" ]; then
		excluded_tree="$source_tree/*-test"
	fi
	production_manifests="$(find "$source_tree" -type d -name .daml -prune -o -path "$excluded_tree" -prune -o -name daml.yaml -type f -print | sort)" ||
		fail "failed to discover production package manifests under $source_tree"
	[ -n "$production_manifests" ] || continue

	while IFS= read -r manifest; do
		package_dir="$(dirname "$manifest")"
		component="$(basename "$package_dir")"
		test_package="$test_tree/$component-test"
		if [ "$source_tree" = "$test_tree" ]; then
			test_package="$package_dir-test"
			# Versioned upgrade examples can share a test package that imports
			# both DARs instead of having one test package per version.
			if [ ! -f "$test_package/daml.yaml" ]; then
				test_package=""
				while IFS= read -r candidate_manifest; do
					candidate="$(dirname "$candidate_manifest")"
					case "$candidate" in
					*-test) ;;
					*) continue ;;
					esac
					candidate_dar_dir="$(relpath "$candidate" "$package_dir")/.daml/dist/"
					if grep -Fq "$candidate_dar_dir" "$candidate_manifest"; then
						[ -z "$test_package" ] || fail "multiple test packages for $package_dir"
						test_package="$candidate"
					fi
				done < <(find "$test_tree" -type d -name .daml -prune -o -name daml.yaml -type f -print | sort)
				[ -n "$test_package" ] || fail "missing test package for $package_dir"
			fi
		fi
		test_manifest="$test_package/daml.yaml"
		coverage_report="$REPORTS/$component-coverage.txt"

		[ -f "$test_manifest" ] ||
			fail "missing test package for $package_dir: $test_manifest"
		dar_dir="$(relpath "$test_package" "$package_dir")/.daml/dist/"
		grep -Fq "$dar_dir" "$test_manifest" ||
			fail "$test_manifest must data-depend on $package_dir"

		printf 'coverage: testing %s\n' "$component"
		# Report paths are absolute: dpm resolves --save-coverage against the package
		# directory and --junit against the working directory.
		DAML_PACKAGE="$test_package" dpm test \
			--all \
			--show-coverage \
			--junit "$ROOT/$REPORTS/$component-junit.xml" \
			--save-coverage "$ROOT/$REPORTS/$component.coverage" \
			| tee "$coverage_report"

		production_package="$(sed -n 's/^name:[[:space:]]*//p' "$manifest")"
		check_zero "$coverage_report" "external templates never created" "$production_package"
		check_zero "$coverage_report" "external template choices never exercised" "$production_package"
		check_zero "$coverage_report" "external interface choices never exercised" "$production_package"

		# The choices of interfaces the package's templates implement, which
		# DPM does not count, derived from the DARs and checked against the
		# saved coverage, with docs/INTERFACE-CHOICES.md as a cross-check.
		production_dar="$(ls "$package_dir"/.daml/dist/*.dar)"
		python3 scripts/check-interface-coverage.py \
			--dar "$production_dar" \
			--coverage "$ROOT/$REPORTS/$component.coverage" \
			--interface-dars dars/vendor/splice-api-token-*.dar packages/*/api-*/.daml/dist/*.dar \
			--manual docs/INTERFACE-CHOICES.md --manual-section "$production_package" \
			--sdk "${DPM_SDK_VERSION:-3.4.11}" ||
			fail "interface choices of $production_package not all exercised, or the list differs"

		package_count=$((package_count + 1))
	done <<< "$production_manifests"
done

[ "$package_count" -gt 0 ] || fail "no production package manifests found"

printf 'coverage: OK (%d production packages)\n' "$package_count"
