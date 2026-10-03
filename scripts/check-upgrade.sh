#!/usr/bin/env bash
# Gate Q-14: upgrade compatibility (docs/TESTING.md; docs/CONVENTIONS.md,
# section 4).
#
# In a scratch copy outside the repository, builds three candidates of every
# production package with the SDK in use (API packages with SDK 3.4.11,
# D-11):
#   1. the release candidate: the tree as it is, version 0.1.0;
#   2. a compatible patch candidate, version 0.1.1, of cvx-vault-math-v1 and
#      cvx-vault-v1: a doc-comment change in each public module, and an
#      Optional field appended to VaultState (docs/CONVENTIONS.md, section 4); the vault keeps
#      depending on the API package 0.1.0;
#   3. a breaking candidate, version 0.1.2: the patch candidate with a
#      field appended to VaultState that is not Optional.
# Then `dpm upgrade-check --both` must pass on the release and patch
# candidates, and must fail with the expected message on the breaking
# candidate and on a patch candidate of the API package, which SCU refuses
# because the package defines an interface. Every check's output is kept in
# test-reports/upgrade/.
#
# Usage: scripts/check-upgrade.sh
#   DPM_SDK_VERSION  the SDK (default 3.4.11)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SDK="${DPM_SDK_VERSION:-3.4.11}"
OUT="$ROOT/test-reports/upgrade/$SDK"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rm -rf "$OUT"
mkdir -p "$OUT"
PACKAGES="packages/utils/vault-math-v1 packages/token/api-vault-v1 packages/token/vault-v1"

fail() { printf 'upgrade: FAIL %s\n' "$*" >&2; exit 1; }

# A copy of the production packages and the vendored DARs, outside the
# repository: DPM resolves a package inside it only when multi-package.yaml
# lists it.
copy_tree() { # dest
	mkdir -p "$1"
	for rel in $PACKAGES dars/vendor; do
		mkdir -p "$1/$(dirname "$rel")"
		rsync -a --exclude .daml "$rel/" "$1/$rel/"
	done
}

# Build the three packages of a tree and copy their DARs to dest.
build_tree() { # tree dest
	local d sdk name version
	mkdir -p "$2"
	for d in $PACKAGES; do
		sdk="$SDK"
		case "$d" in *api-*) sdk=3.4.11 ;; esac
		(cd "$1/$d" && DPM_SDK_VERSION="$sdk" dpm build --enable-multi-package=no) > "$WORK/build.txt" 2>&1 ||
			{ cat "$WORK/build.txt" >&2; fail "build of $d in $(basename "$1")"; }
		name="$(sed -n 's/^name:[[:space:]]*//p' "$1/$d/daml.yaml")"
		version="$(sed -n 's/^version:[[:space:]]*//p' "$1/$d/daml.yaml")"
		cp "$1/$d/.daml/dist/$name-$version.dar" "$2/"
	done
}

# Set the given packages of a tree to `version`, and point the tree's
# data-dependencies on those packages at that version.
set_version() { # tree version package-dir...
	local tree="$1" version="$2" d name all
	shift 2
	all="$(for d in $PACKAGES; do printf '%s/%s/daml.yaml ' "$tree" "$d"; done)"
	for d in "$@"; do
		name="$(sed -n 's/^name:[[:space:]]*//p' "$tree/$d/daml.yaml")"
		sed -i.bak -e "s/^version:.*/version: $version/" "$tree/$d/daml.yaml"
		# shellcheck disable=SC2086
		sed -i.bak -e "s/$name-0\.1\.[0-9]*\.dar/$name-$version.dar/" $all
	done
	rm -f "$tree"/packages/*/*/daml.yaml.bak
}

# Replace exactly one occurrence of `old` with `new` in a file of a tree.
edit() { # file old new
	python3 - "$1" "$2" "$3" <<'PY' || fail "edit of $1"
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path).read()
if text.count(old) != 1:
    sys.exit(f"{path}: expected one occurrence of {old!r}, found {text.count(old)}")
open(path, "w").write(text.replace(old, new))
PY
}

# Run upgrade-check on a set of DARs. A run is rejected when it exits
# non-zero (the participant check) or reports an error of the compiler check
# ("Severity: DsError"): the compiler check's errors do not change the exit
# status of `dpm upgrade-check --both` at dpm 1.0.22.
check() { # label expect(pass|fail) pattern dar...
	local label="$1" expect="$2" pattern="$3" status rejected by
	shift 3
	set +e
	DPM_SDK_VERSION="$SDK" dpm upgrade-check --both "$@" > "$OUT/$label.txt" 2>&1
	status=$?
	set -e
	rejected=no; by=""
	[ "$status" -ne 0 ] && { rejected=yes; by="participant check (exit $status)"; }
	grep -q 'Severity: DsError' "$OUT/$label.txt" && { rejected=yes; by="${by:+$by, }compiler check (DsError)"; }
	printf 'upgrade: %s: exit %s, %s\n' "$label" "$status" "$( [ $rejected = yes ] && printf 'rejected by %s' "$by" || printf 'accepted')"
	if [ "$expect" = pass ]; then
		[ "$rejected" = no ] || { grep -v DEBUG "$OUT/$label.txt" | grep -v ' INFO ' >&2; fail "$label should pass"; }
	else
		[ "$rejected" = yes ] || { cat "$OUT/$label.txt" >&2; fail "$label should fail"; }
		grep -Eq "$pattern" "$OUT/$label.txt" || { cat "$OUT/$label.txt" >&2; fail "$label failed without /$pattern/"; }
		printf 'upgrade: %s: %s\n' "$label" "$(grep -Eo "[^.]*$pattern[^.]*" "$OUT/$label.txt" | head -1)"
	fi
}

# 1. Release candidate.
copy_tree "$WORK/rc"
build_tree "$WORK/rc" "$WORK/dars"

# 2. Compatible patch candidate.
copy_tree "$WORK/pc"
set_version "$WORK/pc" 0.1.1 packages/utils/vault-math-v1 packages/token/vault-v1
edit "$WORK/pc/packages/utils/vault-math-v1/daml/Cayvox/VaultMathV1.daml" \
	"-- | Cayvox vault math:" "-- | Cayvox vault math (patch candidate):"
edit "$WORK/pc/packages/token/vault-v1/daml/Cayvox/VaultV1.daml" \
	"-- | Cayvox vault:" "-- | Cayvox vault (patch candidate):"
edit "$WORK/pc/packages/token/vault-v1/daml/Cayvox/VaultV1.daml" \
	"    meta : Metadata
      -- ^ Extension data (D-12).
  where
    signatory operator" \
	"    meta : Metadata
      -- ^ Extension data (D-12).
    upgradeNote : Optional Text
      -- ^ Appended by the patch candidate of Q-14.
  where
    signatory operator"
build_tree "$WORK/pc" "$WORK/dars"

# An API package is never upgraded: SCU refuses an upgrade of a package
# that defines an interface, so its patch candidate must fail (a change is
# a new -v2 package: docs/CONVENTIONS.md, section 4; D-11).
copy_tree "$WORK/ac"
set_version "$WORK/ac" 0.1.1 packages/token/api-vault-v1
edit "$WORK/ac/packages/token/api-vault-v1/daml/Cayvox/Api/VaultV1.daml" \
	"-- | Cayvox vault API:" "-- | Cayvox vault API (patch candidate):"
build_tree "$WORK/ac" "$WORK/dars-ac"

# 3. Breaking candidate of the vault: the patch candidate with one more
# field appended to VaultState that is not Optional (docs/CONVENTIONS.md,
# section 4).
copy_tree "$WORK/bc"
set_version "$WORK/bc" 0.1.2 packages/utils/vault-math-v1 packages/token/vault-v1
cp "$WORK/pc/packages/token/vault-v1/daml/Cayvox/VaultV1.daml" "$WORK/bc/packages/token/vault-v1/daml/Cayvox/VaultV1.daml"
edit "$WORK/bc/packages/token/vault-v1/daml/Cayvox/VaultV1.daml" \
	"    upgradeNote : Optional Text
      -- ^ Appended by the patch candidate of Q-14." \
	"    upgradeNote : Optional Text
      -- ^ Appended by the patch candidate of Q-14.
    upgradeCount : Int
      -- ^ Appended by the breaking candidate of Q-14, not Optional."
build_tree "$WORK/bc" "$WORK/dars-bc"

D="$WORK/dars"
check math-0.1.0-to-0.1.1 pass "" "$D/cvx-vault-math-v1-0.1.0.dar" "$D/cvx-vault-math-v1-0.1.1.dar"
check vault-0.1.0-to-0.1.1 pass "" "$D/cvx-vault-math-v1-0.1.0.dar" "$D/cvx-api-vault-v1-0.1.0.dar" "$D/cvx-vault-v1-0.1.0.dar" \
	"$D/cvx-vault-math-v1-0.1.1.dar" "$D/cvx-vault-v1-0.1.1.dar"
check api-0.1.0-to-0.1.1-refused fail "interfaces cannot be upgraded" \
	"$D/cvx-api-vault-v1-0.1.0.dar" "$WORK/dars-ac/cvx-api-vault-v1-0.1.1.dar"
check vault-0.1.1-to-0.1.2-breaking fail "${UPGRADE_BREAKING_PATTERN:-has added new fields, but those fields are not Optional}" \
	"$D/cvx-vault-math-v1-0.1.1.dar" "$D/cvx-api-vault-v1-0.1.0.dar" "$D/cvx-vault-v1-0.1.1.dar" \
	"$WORK/dars-bc/cvx-vault-math-v1-0.1.2.dar" "$WORK/dars-bc/cvx-vault-v1-0.1.2.dar"
printf 'upgrade: OK (SDK %s)\n' "$SDK"
