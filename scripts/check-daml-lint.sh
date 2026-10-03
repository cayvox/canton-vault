#!/usr/bin/env bash
# Gate Q-10, second part: OpenZeppelin daml-lint at the pinned revision
# cba698832991f640f0e0d8a9e2bfb683717c6024 on every package of the workspace.
# The tool is built from a checkout at that revision into a cache outside the
# repository (${XDG_CACHE_HOME:-~/.cache}/cvx-vault), never inside the
# checkout. Every finding must be matched by a row of
# scripts/daml-lint-justified.tsv, and every row must match a finding.
#
# daml-lint is AGPL-3.0 licensed; it is run as a tool and none of its code
# is copied into this repository.
#
# Usage: scripts/check-daml-lint.sh [DAML_LINT_CHECKOUT]   (default ../ref/daml-lint)
#   DAML_LINT_JUSTIFIED  optional: another justification table (for testing the gate)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PIN="cba698832991f640f0e0d8a9e2bfb683717c6024"
checkout="${1:-../ref/daml-lint}"

fail() {
	printf 'daml-lint: %s\n' "$*" >&2
	exit 1
}

command -v cargo > /dev/null || fail "cargo is required to build daml-lint"
[ "$(git -C "$checkout" rev-parse HEAD 2>/dev/null)" = "$PIN" ] ||
	fail "$checkout is not a daml-lint checkout at $PIN"
[ -z "$(git -C "$checkout" status --porcelain)" ] || fail "$checkout has local changes"

target="${XDG_CACHE_HOME:-$HOME/.cache}/cvx-vault/daml-lint"
CARGO_TARGET_DIR="$target" cargo build --quiet --release --locked \
	--manifest-path "$checkout/Cargo.toml" 2> /dev/null ||
	fail "cargo build of $checkout failed"
bin="$target/release/daml-lint"
printf 'daml-lint: %s at %s\n' "$("$bin" --version)" "$PIN"

findings="$(mktemp)"
trap 'rm -f "$findings"' EXIT
while IFS= read -r dir; do
	# Exit status 1 only signals findings; they are judged below.
	"$bin" "$dir/daml" --format json --fail-on info 2>/dev/null > "$findings.one" || [ $? -eq 1 ] ||
		fail "daml-lint failed on $dir"
	python3 -c 'import json,sys; [print(json.dumps(f)) for f in json.load(open(sys.argv[1]))["findings"]]' \
		"$findings.one" >> "$findings"
	printf 'daml-lint: scanned %s\n' "$dir"
done <<< "$(sed -n 's/^[[:space:]]*-[[:space:]]*//p' multi-package.yaml)"
rm -f "$findings.one"

python3 - "$findings" "$ROOT" "${DAML_LINT_JUSTIFIED:-scripts/daml-lint-justified.tsv}" <<'PY'
import json, re, sys
findings_file, root, table = sys.argv[1], sys.argv[2], sys.argv[3]
rows = []
for line in open(table):
    if line.startswith("#") or not line.strip():
        continue
    detector, path, pattern, why = line.rstrip("\n").split("\t")
    rows.append({"detector": detector, "path": path, "re": re.compile(pattern), "why": why, "hits": 0})
unjustified = 0
total = 0
for line in open(findings_file):
    f = json.loads(line)
    total += 1
    path = f["file"].replace(root + "/", "")
    evidence = f["evidence"].strip()
    match = next((r for r in rows if r["detector"] == f["detector"] and r["path"] == path
                  and r["re"].search(evidence)), None)
    if match:
        match["hits"] += 1
    else:
        unjustified += 1
        print(f"daml-lint: UNJUSTIFIED {f['severity']} {f['detector']} {path}:{f['line']}: {f['message']}")
for r in rows:
    print(f"daml-lint: justified {r['hits']:>3} x {r['detector']} {r['path']} /{r['re'].pattern}/: {r['why']}")
stale = [r for r in rows if r["hits"] == 0]
for r in stale:
    print(f"daml-lint: STALE row matches no finding: {r['path']} /{r['re'].pattern}/")
print(f"daml-lint: {total} findings, {total - unjustified} justified, {unjustified} unjustified, {len(stale)} stale rows")
sys.exit(1 if unjustified or stale else 0)
PY
printf 'daml-lint: OK\n'
