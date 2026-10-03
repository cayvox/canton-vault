#!/usr/bin/env bash
# Gate Q-12: style. No em or en dashes, no absolute paths, no usernames, no
# email addresses, and none of a list of words that do not belong in this
# repository's files.
#
# The dash check covers the whole working tree with a byte-level grep under
# bash. The other checks cover every text file that git tracks or would
# track (tracked, plus untracked and not ignored), since build outputs are
# ignored and rebuilt. The username check uses the account running the
# script and is skipped on GitHub Actions, whose account name is a common
# word.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

status=0

printf 'style: dashes\n'
if LC_ALL=C grep -rn $'\xe2\x80\x94\|\xe2\x80\x93' .; then
	printf 'style: FAIL em dash or en dash found (above)\n' >&2
	status=1
fi

files="$(git ls-files -z --cached --others --exclude-standard | tr '\0' '\n' | sort -u)"

scan() {
	# Print matches of an extended regex in the text files of the list.
	local flags="$1" pattern="$2"
	printf '%s\n' "$files" | while IFS= read -r f; do
		[ -f "$f" ] || continue
		LC_ALL=C grep -I -n $flags -e "$pattern" "$f" 2>/dev/null | sed "s|^|$f:|" || true
	done
}

printf 'style: absolute paths\n'
# The pattern is split with '' so that this line does not match itself.
hits="$(scan -E '(/Use''rs/|/ho''me/[A-Za-z0-9_.-]+/|/priv''ate/(tmp|var)/|[A-Za-z]:\\\\Use''rs\\\\)')"
if [ -n "$hits" ]; then
	printf '%s\n' "$hits" >&2
	printf 'style: FAIL absolute path found (above)\n' >&2
	status=1
fi

if [ "${GITHUB_ACTIONS:-}" != true ]; then
	printf 'style: usernames\n'
	user="$(id -un)"
	hits="$(scan -wiF "$user")"
	if [ -n "$hits" ]; then
		printf '%s\n' "$hits" >&2
		printf 'style: FAIL username %s found (above)\n' "$user" >&2
		status=1
	fi
fi

printf 'style: email addresses\n'
hits="$(scan -E '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[A-Za-z]{2,}')"
if [ -n "$hits" ]; then
	printf '%s\n' "$hits" >&2
	printf 'style: FAIL email address found (above)\n' >&2
	status=1
fi

printf 'style: words\n'
# Third-party license texts under LICENSES/ are kept verbatim and skipped.
# Split with '' so that this line does not match itself.
hits="$(files="$(printf '%s\n' "$files" | grep -v '^LICENSES/')" scan -iE 'clau''de|anthro''pic|open''ai|cod''ex|chat''gpt|copi''lot|gener''ated')"
if [ -n "$hits" ]; then
	printf '%s\n' "$hits" >&2
	printf 'style: FAIL word from the excluded list found (above)\n' >&2
	status=1
fi

[ "$status" -eq 0 ] && printf 'style: OK\n'
exit "$status"
