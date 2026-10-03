#!/usr/bin/env bash
# Gate Q-01: every package of multi-package.yaml built from clean with the SDK
# in DPM_SDK_VERSION, except API packages, which are built by SDK 3.4.11
# (D-11, dars/api-packages.yaml). A build does not recompile outputs left by
# another SDK, so the package build directories are removed first. Each DAR's
# `Sdk-Version` and Daml-LF version are checked, then the recorded API package
# IDs (scripts/check-api-ids.sh).
#
# Usage: DPM_SDK_VERSION=<sdk> scripts/build-all.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${DPM_SDK_VERSION:?set DPM_SDK_VERSION to the SDK of the run}"

package_dirs() {
	sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml
}

# The SDK that builds a package: API packages are built once, by SDK 3.4.11,
# and every other package, their test packages included, consumes that DAR
# with the SDK of the run (D-11, dars/api-packages.yaml).
expected_sdk() {
	case "$(sed -n 's/^name:[[:space:]]*//p' "$1/daml.yaml")" in
	*-test) printf '%s' "$DPM_SDK_VERSION" ;;
	*-api-*) printf '3.4.11' ;;
	*) printf '%s' "$DPM_SDK_VERSION" ;;
	esac
}

count=0
while IFS= read -r dir; do
	rm -rf "$dir/.daml"
done <<< "$(package_dirs)"

# In multi-package.yaml order, which lists dependencies first. Each package
# is built on its own, so that no API package is rebuilt by another SDK.
while IFS= read -r dir; do
	want="$(expected_sdk "$dir")"
	printf 'build: %s with SDK %s\n' "$dir" "$want"
	(cd "$dir" && DPM_SDK_VERSION="$want" dpm build --enable-multi-package=no)
done <<< "$(package_dirs)"

while IFS= read -r dir; do
	want="$(expected_sdk "$dir")"
	for dar in "$dir"/.daml/dist/*.dar; do
		[ -f "$dar" ] || { printf 'build: no DAR in %s\n' "$dir" >&2; exit 1; }
		sdk="$(unzip -p "$dar" META-INF/MANIFEST.MF | tr -d '\r' | sed -n 's/^Sdk-Version: //p')"
		lf="$(dpm damlc inspect "$dar" | grep -m1 -o 'daml-lf [0-9.]*' | cut -d' ' -f2)"
		printf 'build: %s Sdk-Version %s, Daml-LF %s\n' "$dar" "$sdk" "$lf"
		[ "$sdk" = "$want" ] ||
			{ printf 'build: %s was built by SDK %s, expected %s\n' "$dar" "$sdk" "$want" >&2; exit 1; }
		[ "$lf" = "2.1" ] ||
			{ printf 'build: %s targets Daml-LF %s, expected 2.1\n' "$dar" "$lf" >&2; exit 1; }
		count=$((count + 1))
	done
done <<< "$(package_dirs)"

printf 'build: OK (%d DARs)\n' "$count"
scripts/check-api-ids.sh
