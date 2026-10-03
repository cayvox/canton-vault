#!/usr/bin/env bash
# The tests of the never-released tooling packages under tools/: each -test
# package there runs with `dpm test --all`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

count=0
for manifest in $(find tools -type d -name .daml -prune -o -name daml.yaml -type f -print | sort); do
	dir="$(dirname "$manifest")"
	case "$(sed -n 's/^name:[[:space:]]*//p' "$manifest")" in
	*-test) ;;
	*) continue ;;
	esac
	printf 'tools: running %s\n' "$dir"
	DAML_PACKAGE="$dir" dpm test --all
	count=$((count + 1))
done
[ "$count" -gt 0 ] || { printf 'tools: no tool test package found\n' >&2; exit 1; }
printf 'tools: OK (%d test packages)\n' "$count"
