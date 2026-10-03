#!/usr/bin/env bash
# Gate Q-02: static repository-policy checks.
#
# Ported from OpenZeppelin/canton-contracts scripts/check.sh at commit
# aeca01d043311d8ccc8ab7cda4d7c16e682429fa.
# Copyright (c) 2026 OpenZeppelin. MIT License; the full license text is in
# LICENSES/canton-contracts-MIT.txt.
#
# Changes from the source:
#   - two source and test tree pairs, packages:test and examples:examples
#     (this repository has no experiments/ tree); tools/ holds never-released
#     Daml Script tooling and is checked by scripts/check-tools.sh;
#   - the required-file list names this repository's files;
#   - the package-name prefix is a variable, PREFIX, so the rename of D-17
#     changes one line, and production packages under packages/ must use it;
#   - three added checks from docs/CONVENTIONS.md: every package targets
#     Daml-LF 2.1 (section 9), production packages declare no contract key
#     (docs/CONVENTIONS.md, section 9), and utility packages under packages/utils/ define no
#     templates, interfaces or exceptions (section 3);
#   - every copy of the failure helper is byte-identical to its canonical
#     source (docs/TESTING.md, section 3, rule 2).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="cvx"

# Source/test tree pairs. Shared trees distinguish tests by their -test directories.
TREES=("packages:test" "examples:examples")

fail() {
	printf 'check: %s\n' "$*" >&2
	exit 1
}

require_file() {
	[ -f "$ROOT/$1" ] || fail "missing $1"
}

# Print every package manifest in a tree, ignoring build output and an optional
# nested tree. An absent tree prints nothing.
find_manifests() {
	local tree="$1"
	local excluded="${2:-}"
	local exclusion=()

	[ -d "$ROOT/$tree" ] || return 0
	if [ -n "$excluded" ]; then
		exclusion=(-path "$ROOT/$excluded" -prune -o)
	fi

	# The guarded expansion keeps bash 3.2 (macOS default) from treating the
	# empty array as an unbound variable under `set -u`.
	find "$ROOT/$tree" \
		-type d -name .daml -prune -o \
		${exclusion[@]+"${exclusion[@]}"} \
		-name daml.yaml -type f -print
}

for file in \
	README.md ARCHITECTURE.md CHANGELOG.md CONTRIBUTING.md SECURITY.md LICENSE \
	multi-package.yaml dars/manifest.yaml dars/token-standard-pins.txt \
	scripts/check-coverage.sh scripts/check-lint.sh scripts/check-examples.sh \
	scripts/check-token-dars.sh scripts/check-style.sh scripts/check-api-ids.sh scripts/ci.sh \
	scripts/check-daml-lint.sh scripts/daml-lint-justified.tsv \
	scripts/check-math-oracle.sh scripts/math-oracle.py \
	scripts/check-math-proofs.sh scripts/prove-math.py scripts/mutate-math.py \
	dars/api-packages.yaml; do
	require_file "$file"
done

if [ -f "$ROOT/daml.yaml" ]; then
	fail "the repository root is a workspace, not a Daml package"
fi

if ! grep -Eq '^sdk-version:[[:space:]]*[^[:space:]]+' "$ROOT/multi-package.yaml"; then
	fail "multi-package.yaml must pin the workspace SDK version"
fi

workspace_sdk="$(sed -n 's/^sdk-version:[[:space:]]*//p' "$ROOT/multi-package.yaml")"

production_manifests=""
test_manifests=""

for tree_pair in "${TREES[@]}"; do
	source_tree="${tree_pair%%:*}"
	test_tree="${tree_pair##*:}"

	if [ "$source_tree" = "$test_tree" ]; then
		while IFS= read -r manifest; do
			case "$(basename "$(dirname "$manifest")")" in
			*-test) test_manifests+="$manifest"$'\n' ;;
			*) production_manifests+="$manifest"$'\n' ;;
			esac
		done <<< "$(find_manifests "$source_tree")"
	else
		production_manifests+="$(find_manifests "$source_tree" "$test_tree")"$'\n'
		test_manifests+="$(find_manifests "$test_tree")"$'\n'
	fi
done

production_manifests="$(printf '%s' "$production_manifests" | sed '/^$/d' | sort)"
[ -n "$production_manifests" ] || fail "no production package manifests found"

test_manifests="$(printf '%s' "$test_manifests" | sed '/^$/d' | sort -u)"
[ -n "$test_manifests" ] || fail "no test package manifests found"

for manifest_list in "$production_manifests" "$test_manifests"; do
	while IFS= read -r manifest; do
		[ -n "$manifest" ] || continue
		package_sdk="$(sed -n 's/^sdk-version:[[:space:]]*//p' "$manifest")"
		[ "$package_sdk" = "$workspace_sdk" ] ||
			fail "${manifest#"$ROOT/"} sdk-version must match multi-package.yaml"
		grep -Eq '^[[:space:]]*-[[:space:]]*--target=2\.1[[:space:]]*$' "$manifest" ||
			fail "${manifest#"$ROOT/"} must build with --target=2.1"
	done <<< "$manifest_list"
done

package_paths="$(sed -n 's/^[[:space:]]*-[[:space:]]*//p' "$ROOT/multi-package.yaml")" ||
	fail "failed to read package paths from multi-package.yaml"
[ -n "$package_paths" ] || fail "multi-package.yaml declares no packages"

while IFS= read -r package_path; do
	require_file "$package_path/daml.yaml"
done <<< "$package_paths"

while IFS= read -r manifest; do
	if grep -n -E '^[[:space:]]*exposed-modules:' "$manifest"; then
		fail "exposed-modules is not a supported public-API boundary"
	fi
done <<< "$production_manifests"

while IFS= read -r manifest; do
	package_dir="$(dirname "$manifest")"
	package_name="$(sed -n 's/^name:[[:space:]]*//p' "$manifest")"

	case "$package_name" in
	*-test)
		fail "test package ${manifest#"$ROOT/"} must use a supported test-package location"
		;;
	esac

	case "${package_dir#"$ROOT/"}:$package_name" in
	packages/*:"$PREFIX"-* | examples/*) ;;
	*)
		fail "production package ${manifest#"$ROOT/"} must be named $PREFIX-<component>-vN"
		;;
	esac

	if grep -Eq '(^|[[:space:]-])daml-script($|[[:space:]])' "$manifest"; then
		fail "production package ${manifest#"$ROOT/"} depends on daml-script"
	fi

	if [[ "$package_name" == "$PREFIX"-api-* ]]; then
		if grep -R -n -E --include='*.daml' '^[[:space:]]*template[[:space:]]+' "$package_dir/daml"; then
			fail "API package ${manifest#"$ROOT/"} defines templates"
		fi
	else
		# `interface instance` blocks implement an upstream interface and are
		# allowed; only new interface or exception definitions are not.
		if grep -R -n -E --include='*.daml' '^[[:space:]]*(interface|exception)[[:space:]]+' "$package_dir/daml" |
			grep -v -E 'interface[[:space:]]+instance[[:space:]]'; then
			fail "implementation package ${manifest#"$ROOT/"} defines interfaces or exceptions; create a frozen $PREFIX-api-<component>-vN package"
		fi
	fi

	# A utility package holds pure functions only (docs/CONVENTIONS.md,
	# section 3): no templates, interfaces or exceptions.
	case "${package_dir#"$ROOT/"}" in
	packages/utils/*)
		if grep -R -n -E --include='*.daml' '^[[:space:]]*(template|interface|exception)[[:space:]]+' "$package_dir/daml"; then
			fail "utility package ${manifest#"$ROOT/"} defines templates, interfaces or exceptions"
		fi
		;;
	esac

	if grep -R -n -E --include='*.daml' '^[[:space:]]+key[[:space:]]' "$package_dir/daml"; then
		fail "production package ${manifest#"$ROOT/"} declares a contract key"
	fi

	require_file "${package_dir#"$ROOT/"}/README.md"
done <<< "$production_manifests"

while IFS= read -r manifest; do
	package_name="$(sed -n 's/^name:[[:space:]]*//p' "$manifest")"
	package_version="$(sed -n 's/^version:[[:space:]]*//p' "$manifest")"

	case "$(basename "$(dirname "$manifest")")" in
	*-test)
		;;
	*)
		fail "test package ${manifest#"$ROOT/"} must use a -test directory name"
		;;
	esac

	case "$package_name" in
	*-test)
		;;
	*)
		fail "test package ${manifest#"$ROOT/"} must use a -test name"
		;;
	esac

	[ "$package_version" = "0.0.0" ] ||
		fail "test package ${manifest#"$ROOT/"} must use version 0.0.0"

	grep -Eq '(^|[[:space:]-])daml-script($|[[:space:]])' "$manifest" ||
		fail "test package ${manifest#"$ROOT/"} must depend on daml-script"

	grep -Eq '^[[:space:]]*-[[:space:]]*(\.\./)+.+\.dar$' "$manifest" ||
		fail "test package ${manifest#"$ROOT/"} must data-depend on a production DAR"
done <<< "$test_manifests"

# Every copy of the failure helper in a test package is byte-identical to its
# canonical source (docs/TESTING.md, section 3, rule 2).
HELPER="test/shared/Cayvox/Testing/Assert.daml"
require_file "$HELPER"
helper_copies=0
while IFS= read -r copy; do
	[ -n "$copy" ] || continue
	cmp -s "$ROOT/$HELPER" "$copy" ||
		fail "${copy#"$ROOT/"} differs from the canonical failure helper $HELPER"
	helper_copies=$((helper_copies + 1))
done <<< "$(find "$ROOT/test" -path "$ROOT/test/shared" -prune -o -type d -name .daml -prune -o \
	-path '*/Cayvox/Testing/Assert.daml' -type f -print)"
[ ! -f "$ROOT/test/shared/daml.yaml" ] || fail "test/shared holds canonical sources and is not a package"

printf 'check: OK (failure helper copies identical: %d)\n' "$helper_copies"
