#!/usr/bin/env bash
# Build the cli/ wheel and install it via `uv tool` exactly the way a user
# would install from PyPI — but without going through PyPI. Use this to
# validate a release candidate before tagging.
#
# Usage:
#   ./scripts/dev-install.sh           # installs paty[mlx] from local wheel
#   ./scripts/dev-install.sh cuda      # paty[cuda]
#   ./scripts/dev-install.sh cpu       # paty[cpu]
#   ./scripts/dev-install.sh ""        # bare paty, no extras (test no-backend gate)
set -euo pipefail

extra="${1-mlx}"

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root/cli"

echo "==> building wheel"
rm -rf dist
uv build --wheel >/dev/null
wheel="$(ls dist/*.whl)"
echo "    $wheel"

echo "==> uninstalling any existing paty tool"
uv tool uninstall paty 2>/dev/null || true

if [[ -n "$extra" ]]; then
  echo "==> uv tool install '${wheel}[${extra}]'"
  uv tool install "${wheel}[${extra}]"
else
  echo "==> uv tool install ${wheel}  (no extras)"
  uv tool install "$wheel"
fi

echo
echo "Installed: $(which paty)"
paty --version
echo
echo "Run with:  paty run"
