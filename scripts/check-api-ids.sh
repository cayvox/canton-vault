#!/usr/bin/env bash
# D-11: every API package listed in dars/api-packages.yaml is built by SDK
# 3.4.11 and has its recorded main package ID. Checks the DAR in the
# package's .daml/dist/, building it with SDK 3.4.11 first when it is absent.
#
# Usage: scripts/check-api-ids.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RECORD="dars/api-packages.yaml"
[ -f "$RECORD" ] || { printf 'api-ids: missing %s\n' "$RECORD" >&2; exit 1; }

entries="$(awk '
	function flush() { if (pkg != "") print pkg, ver, path, sdk, id; pkg = ""; ver = ""; path = ""; sdk = ""; id = "" }
	/^  - package:/ { flush(); pkg = $3 }
	/^    version:/ { ver = $2 }
	/^    path:/ { path = $2 }
	/^    sdk-version:/ { sdk = $2 }
	/^    main-package-id:/ { id = $2 }
	END { flush() }
' "$RECORD")"
[ -n "$entries" ] || { printf 'api-ids: no entries in %s\n' "$RECORD" >&2; exit 1; }

# Every API package of the workspace must be recorded.
while IFS= read -r manifest; do
	name="$(sed -n 's/^name:[[:space:]]*//p' "$manifest")"
	case "$name" in
	*-api-*)
		printf '%s\n' "$entries" | awk -v n="$name" '$1 == n { f = 1 } END { exit f ? 0 : 1 }' ||
			{ printf 'api-ids: FAIL %s is not recorded in %s\n' "$name" "$RECORD" >&2; exit 1; }
		;;
	esac
done <<< "$(find packages -type d -name .daml -prune -o -name daml.yaml -type f -print | sort)"

status=0
while read -r pkg ver path sdk id; do
	dar="$path/.daml/dist/$pkg-$ver.dar"
	if [ ! -f "$dar" ]; then
		(cd "$path" && DPM_SDK_VERSION="$sdk" dpm build --enable-multi-package=no) > /dev/null
	fi
	built_sdk="$(unzip -p "$dar" META-INF/MANIFEST.MF | tr -d '\r' | sed -n 's/^Sdk-Version: //p')"
	built_id="$(DPM_SDK_VERSION="$sdk" dpm damlc inspect-dar --json "$dar" | jq -r '.main_package_id')"
	result="OK"
	[ "$built_sdk" = "$sdk" ] || { result="FAIL"; printf 'api-ids: FAIL %s built by SDK %s, expected %s\n' "$pkg" "$built_sdk" "$sdk" >&2; }
	[ "$built_id" = "$id" ] || { result="FAIL"; printf 'api-ids: FAIL %s has package ID %s, recorded %s\n' "$pkg" "$built_id" "$id" >&2; }
	printf 'api-ids: %s %s %s %s\n' "$pkg" "$ver" "${built_id:0:16}" "$result"
	[ "$result" = OK ] || status=1
done <<< "$entries"
exit "$status"
