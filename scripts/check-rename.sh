#!/usr/bin/env bash
# Gate Q-15: the D-17 rename produces a tree that passes Q-01 to Q-05
# (docs/TESTING.md). Renames a copy of the repository into a temporary
# directory outside it with scripts/rename-d17.py, then runs, inside the
# renamed copy and with its renamed scripts, on each SDK: Q-02
# (scripts/check.sh), Q-01 (every package built from clean, the API package
# with SDK 3.4.11, and scripts/check-api-ids.sh against the renamed record),
# Q-03 with Q-04 (scripts/check-coverage.sh: every test, coverage, and the
# interface-choice check, over the test packages and the example) and the
# tool tests (scripts/check-tools.sh); then Q-05 (scripts/check-sandbox.sh)
# once, on the sandboxes of SDK 3.4.11 and 3.5.10. The renamed tree is
# removed afterwards and is never committed.
#
# Usage: scripts/check-rename.sh
#   RENAME_KEEP=1     keep the renamed copy and print its path
#   RENAME_SDKS       the SDKs of Q-01 to Q-04 (default "3.4.11 3.5.8 3.5.10")
#   RENAME_SANDBOX=0  skip Q-05
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="$(mktemp -d)"
DEST="$SCRATCH/renamed"
[ "${RENAME_KEEP:-0}" = 1 ] || trap 'rm -rf "$SCRATCH"' EXIT

python3 "$ROOT/scripts/rename-d17.py" "$DEST"
cd "$DEST"

package_dirs() { sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml; }
expected_sdk() { # dir run-sdk
	case "$(sed -n 's/^name:[[:space:]]*//p' "$1/daml.yaml")" in
	*-test) printf '%s' "$2" ;;
	*-api-*) printf '3.4.11' ;;
	*) printf '%s' "$2" ;;
	esac
}

for sdk in ${RENAME_SDKS:-3.4.11 3.5.8 3.5.10}; do
	export DPM_SDK_VERSION="$sdk"
	printf '\n== Q-02, renamed tree, SDK %s\n' "$sdk"
	scripts/check.sh
	printf '\n== Q-01, renamed tree, SDK %s\n' "$sdk"
	while IFS= read -r dir; do rm -rf "$dir/.daml"; done <<< "$(package_dirs)"
	while IFS= read -r dir; do
		want="$(expected_sdk "$dir" "$sdk")"
		(cd "$dir" && DPM_SDK_VERSION="$want" dpm build --enable-multi-package=no) > /dev/null 2>&1 ||
			{ printf 'rename: build of %s with SDK %s failed\n' "$dir" "$want" >&2; exit 1; }
		printf 'build: %s with SDK %s: %s\n' "$dir" "$want" "$(ls "$dir"/.daml/dist/)"
	done <<< "$(package_dirs)"
	scripts/check-api-ids.sh
	printf '\n== Q-03 and Q-04, renamed tree, SDK %s\n' "$sdk"
	if scripts/check-coverage.sh > "$SCRATCH/coverage-$sdk.txt" 2>&1; then
		grep -E '^(coverage|interface-coverage): (OK|external|testing|cvx|openzeppelin|cross)' "$SCRATCH/coverage-$sdk.txt" || true
		printf 'tests: %s ok, %s failed\n' "$(grep -c ': ok, ' "$SCRATCH/coverage-$sdk.txt")" "$(grep -c ': failed' "$SCRATCH/coverage-$sdk.txt")"
	else
		tail -60 "$SCRATCH/coverage-$sdk.txt" >&2
		printf 'rename: Q-03 failed on SDK %s\n' "$sdk" >&2
		exit 1
	fi
	printf '\n== tools, renamed tree, SDK %s\n' "$sdk"
	scripts/check-tools.sh
done

if [ "${RENAME_SANDBOX:-1}" = 0 ]; then
	printf '\nrename: OK, the renamed tree passes Q-01 to Q-04 and the tool tests on SDK %s; Q-05 skipped\n' "${RENAME_SDKS:-3.4.11 3.5.8 3.5.10}"
	[ "${RENAME_KEEP:-0}" = 1 ] && printf 'rename: kept in %s\n' "$DEST"
	exit 0
fi

printf '\n== Q-05, renamed tree\n'
export DPM_SDK_VERSION=3.5.10
scripts/check-sandbox.sh
printf '\nrename: OK, the renamed tree passes Q-01 to Q-04 on SDK %s and Q-05\n' "${RENAME_SDKS:-3.4.11 3.5.8 3.5.10}"
[ "${RENAME_KEEP:-0}" = 1 ] && printf 'rename: kept in %s\n' "$DEST"
exit 0
