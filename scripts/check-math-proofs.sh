#!/usr/bin/env bash
# Gate Q-09: Z3 proofs of M-01 to M-07 and of the KMAX derivation on an
# integer model (scripts/prove-math.py). Z3 comes from the z3-solver package
# at a pinned version, installed into a virtual environment in a cache
# outside the repository (${XDG_CACHE_HOME:-~/.cache}/cvx-vault).
#
# Usage: scripts/check-math-proofs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
Z3_SOLVER="z3-solver==5.1.0.0"
venv="${XDG_CACHE_HOME:-$HOME/.cache}/cvx-vault/z3-venv"

if ! "$venv/bin/python" -c 'import z3' 2> /dev/null ||
	[ "$("$venv/bin/pip" show z3-solver 2>/dev/null | sed -n 's/^Version: //p')" != "${Z3_SOLVER#*==}" ]; then
	python3 -m venv "$venv"
	"$venv/bin/pip" install --quiet --disable-pip-version-check "$Z3_SOLVER"
fi
"$venv/bin/python" scripts/prove-math.py
