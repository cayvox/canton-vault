#!/usr/bin/env bash
# Gate Q-11: documentation (docs/TESTING.md). The parts that a script can
# check:
#   - every template and interface of a production package carries a doc
#     comment of at least four lines (docs/CONVENTIONS.md, section 7, whose
#     list of topics a reviewer checks);
#   - every public module, one not under .Internal, starts with a module doc
#     comment (docs/CONVENTIONS.md, section 7);
#   - every production package README has the sections of
#     docs/CONVENTIONS.md, section 7: the
#     package table with its public modules, what it provides, authority and
#     lifecycle, scope and security caveats, build, and consumption;
#   - every example and tool package has a README;
#   - the docs site page has `title` and `description` frontmatter
#     (docs/CONVENTIONS.md, section 7).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 - <<'PY'
import glob, os, re, sys

errors = []

for path in sorted(glob.glob("packages/**/*.daml", recursive=True)):
    lines = open(path).read().split("\n")
    module = path.split("/daml/", 1)[1][:-5].replace("/", ".")
    if ".Internal" not in module and not lines[0].startswith("-- |"):
        errors.append(f"{path}: public module {module} has no module doc comment")
    for i, line in enumerate(lines):
        m = re.match(r"^(template|interface)\s+(\w+)", line)
        if not m or line.startswith("interface instance"):
            continue
        j, doc = i - 1, 0
        while j >= 0 and lines[j].startswith("--"):
            doc, j = doc + 1, j - 1
        if doc < 4:
            errors.append(f"{path}:{i + 1}: {m.group(1)} {m.group(2)} has {doc} doc comment lines, at least 4 expected")

sections = ["## What it provides", "## Authority and lifecycle", "## Scope and security caveats",
            "## Build", "## Consume a local build"]
for manifest in sorted(glob.glob("packages/*/*/daml.yaml")):
    readme = os.path.join(os.path.dirname(manifest), "README.md")
    if not os.path.exists(readme):
        errors.append(f"{readme}: missing")
        continue
    text = open(readme).read()
    for s in sections:
        if s not in text:
            errors.append(f"{readme}: no section '{s}'")
    if not re.search(r"^\| Public modules? \|", text, re.M):
        errors.append(f"{readme}: no 'Public module' row in the package table")

for manifest in sorted(glob.glob("examples/**/daml.yaml", recursive=True) + glob.glob("tools/*/daml.yaml")):
    d = os.path.dirname(manifest)
    if d.endswith("-test"):
        continue
    if not os.path.exists(os.path.join(d, "README.md")):
        errors.append(f"{d}/README.md: missing")

for page in sorted(glob.glob("docs/site/*.mdx")):
    text = open(page).read()
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    front = m.group(1) if m else ""
    for key in ("title", "description"):
        if not re.search(rf"^{key}: \S", front, re.M):
            errors.append(f"{page}: frontmatter has no {key}")
if not glob.glob("docs/site/*.mdx"):
    errors.append("docs/site: no page")

for e in errors:
    print(f"docs: {e}")
if errors:
    print(f"docs: FAIL ({len(errors)})")
    sys.exit(1)
print("docs: OK")
PY
