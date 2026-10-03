#!/usr/bin/env bash
# Gate Q-16: token DAR identity.
#
# For every entry in dars/manifest.yaml, checks that:
#   1. the file exists and its SHA-256 equals the recorded `sha256`;
#   2. the main package ID, name and version computed with
#      `dpm damlc inspect-dar --json` equal the recorded values;
#   3. the complete package-ID closure equals the recorded `package-ids`;
#   4. the file is byte-identical to `upstream-path` at `upstream-tag` of the
#      upstream repository, and the tag resolves to `upstream-commit`;
#   5. for a Splice token standard API or utils DAR, the main package ID is the
#      one pinned in dars/token-standard-pins.txt (D-03).
# It also checks that every DAR under dars/vendor/ has an entry, and that every
# Splice DAR named in a data-dependency of a package of this repository is a
# manifest file.
#
# Usage: scripts/check-token-dars.sh
#   SPLICE_CHECKOUT  optional: a clone of canton-network/splice that has the tag.
#                    Files are read with `git show <tag>:<path>`, so the clone is
#                    not modified. When unset, the tag is fetched (sparse,
#                    daml/dars/ only) into a temporary directory.
#
# Requirements: bash 3.2 or later, git, dpm, jq, shasum, awk, sed, grep, cmp.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MANIFEST="dars/manifest.yaml"
PINS="dars/token-standard-pins.txt"

fail_count=0
fail() {
	printf 'token-dars: FAIL %s\n' "$*" >&2
	fail_count=$((fail_count + 1))
}

for tool in git dpm jq shasum awk sed grep cmp; do
	command -v "$tool" >/dev/null 2>&1 || { printf 'token-dars: missing tool %s\n' "$tool" >&2; exit 2; }
done
[ -f "$MANIFEST" ] || { printf 'token-dars: missing %s\n' "$MANIFEST" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# One line per entry: package version file main-id sha256 repo tag commit path.
awk '
	function flush() {
		if (pkg != "") print pkg, ver, file, mid, sha, repo, tag, commit, path
		pkg = ""; ver = ""; file = ""; mid = ""; sha = ""; repo = ""; tag = ""; commit = ""; path = ""
	}
	/^  - kind:/ { flush() }
	/^    package:/ { pkg = $2 }
	/^    version:/ { ver = $2 }
	/^    file:/ { file = $2 }
	/^    main-package-id:/ { mid = $2 }
	/^    sha256:/ { sha = $2 }
	/^    upstream-repository:/ { repo = $2 }
	/^    upstream-tag:/ { tag = $2 }
	/^    upstream-commit:/ { commit = $2 }
	/^    upstream-path:/ { path = $2 }
	END { flush() }
' "$MANIFEST" > "$WORK/entries.txt"

# Recorded closure per file: "file id" lines.
awk '
	/^  - kind:/ { in_ids = 0 }
	/^    file:/ { file = $2 }
	/^    package-ids:/ { in_ids = 1; next }
	in_ids && /^      - / { print file, $2; next }
	in_ids { in_ids = 0 }
' "$MANIFEST" > "$WORK/closures.txt"

[ -s "$WORK/entries.txt" ] || { printf 'token-dars: no entries in %s\n' "$MANIFEST" >&2; exit 1; }

# Upstream checkouts, one per repository and tag.
upstream_dir() {
	local repo="$1" tag="$2" key
	key="$(printf '%s-%s' "$repo" "$tag" | tr -c 'A-Za-z0-9.-' '_')"
	if [ -n "${SPLICE_CHECKOUT:-}" ] && [ "$repo" = "https://github.com/canton-network/splice" ]; then
		printf '%s' "$SPLICE_CHECKOUT"
		return
	fi
	if [ ! -d "$WORK/$key" ]; then
		git clone --quiet --filter=blob:none --no-checkout --depth 1 --branch "$tag" \
			"$repo.git" "$WORK/$key" >&2
		git -C "$WORK/$key" sparse-checkout set --no-cone '/daml/dars/' >&2
	fi
	printf '%s' "$WORK/$key"
}

printf '%-48s %-7s %-16s %-6s %-7s %-8s %-8s %-6s\n' \
	package version main-package-id sha256 closure upstream pin-B.3 result
while read -r pkg ver file mid sha repo tag commit path; do
	result="OK"
	c_sha="-"; c_closure="-"; c_up="-"; c_pin="n/a"

	if [ ! -f "$file" ]; then
		fail "$file: missing"
		printf '%-48s %-7s %-16s %-6s %-7s %-8s %-8s %-6s\n' "$pkg" "$ver" "${mid:0:16}" - - - - FAIL
		continue
	fi

	if [ "$(shasum -a 256 "$file" | cut -d' ' -f1)" = "$sha" ]; then c_sha="ok"; else c_sha="DIFF"; fail "$file: sha256 differs from the manifest"; result="FAIL"; fi

	json="$(dpm damlc inspect-dar --json "$file")"
	a_mid="$(printf '%s' "$json" | jq -r '.main_package_id')"
	a_name="$(printf '%s' "$json" | jq -r --arg m "$a_mid" '.packages[$m].name')"
	a_ver="$(printf '%s' "$json" | jq -r --arg m "$a_mid" '.packages[$m].version')"
	if [ "$a_mid" != "$mid" ]; then fail "$file: main package ID $a_mid, manifest $mid"; result="FAIL"; fi
	if [ "$a_name" != "$pkg" ] || [ "$a_ver" != "$ver" ]; then
		fail "$file: package $a_name $a_ver, manifest $pkg $ver"; result="FAIL"
	fi

	printf '%s' "$json" | jq -r '.packages | keys[]' | sort > "$WORK/actual-closure.txt"
	awk -v f="$file" '$1 == f { print $2 }' "$WORK/closures.txt" | sort > "$WORK/recorded-closure.txt"
	if cmp -s "$WORK/actual-closure.txt" "$WORK/recorded-closure.txt"; then c_closure="ok"; else
		c_closure="DIFF"; fail "$file: package-ID closure differs from the manifest"; result="FAIL"
	fi

	up="$(upstream_dir "$repo" "$tag")"
	up_commit="$(git -C "$up" rev-parse --verify --quiet "$tag^{commit}" || true)"
	if [ "$up_commit" != "$commit" ]; then
		c_up="DIFF"; fail "$file: tag $tag of $repo resolves to ${up_commit:-nothing}, manifest $commit"; result="FAIL"
	elif git -C "$up" show "$tag:$path" > "$WORK/upstream.dar" 2>/dev/null && cmp -s "$file" "$WORK/upstream.dar"; then
		c_up="ok"
	else
		c_up="DIFF"; fail "$file: not byte-identical to $path at $tag"; result="FAIL"
	fi

	case "$pkg" in
	splice-api-token-* | splice-token-standard-utils)
		if grep -Eq "^$pkg-$ver $mid\$" "$PINS"; then c_pin="ok"; else
			c_pin="DIFF"; fail "$file: $mid is not the ID pinned for $pkg-$ver in $PINS"; result="FAIL"
		fi
		;;
	esac

	printf '%-48s %-7s %-16s %-6s %-7s %-8s %-8s %-6s\n' \
		"$pkg" "$ver" "${mid:0:16}" "$c_sha" "$c_closure" "$c_up" "$c_pin" "$result"
done < "$WORK/entries.txt"

# Every vendored DAR has an entry.
for dar in dars/vendor/*.dar; do
	[ -e "$dar" ] || continue
	awk -v f="$dar" '$3 == f { found = 1 } END { exit found ? 0 : 1 }' "$WORK/entries.txt" ||
		fail "$dar: vendored but not in $MANIFEST"
done

# Every Splice DAR used as a data-dependency is a manifest file.
trees=""
for tree in packages test examples tools; do
	[ -d "$tree" ] && trees="$trees $tree"
done
manifests=""
if [ -n "$trees" ]; then
	# $trees is a list of fixed directory names; word splitting is intended.
	# shellcheck disable=SC2086
	manifests="$(find $trees -type d -name .daml -prune -o \
		-name daml.yaml -type f -print | sort)"
fi
while IFS= read -r manifest; do
	[ -n "$manifest" ] || continue
	dir="$(dirname "$manifest")"
	sed -n 's/^[[:space:]]*-[[:space:]]*\(.*splice[^[:space:]]*\.dar\)[[:space:]]*$/\1/p' "$manifest" |
		while IFS= read -r dep; do
			resolved="$(cd "$dir" && cd "$(dirname "$dep")" 2>/dev/null && pwd)/$(basename "$dep")"
			rel="${resolved#"$ROOT/"}"
			awk -v f="$rel" '$3 == f { found = 1 } END { exit found ? 0 : 1 }' "$WORK/entries.txt" && continue
			printf 'token-dars: FAIL %s: data-dependency %s is not a manifest file\n' "$manifest" "$dep" >&2; echo x
		done > "$WORK/dep-fails.txt"
	[ ! -s "$WORK/dep-fails.txt" ] || fail_count=$((fail_count + $(wc -l < "$WORK/dep-fails.txt")))
done <<< "$manifests"

if [ "$fail_count" -ne 0 ]; then
	printf 'token-dars: %d failure(s)\n' "$fail_count" >&2
	exit 1
fi
printf 'token-dars: OK (%d DARs)\n' "$(wc -l < "$WORK/entries.txt" | tr -d ' ')"
