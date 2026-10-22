#!/usr/bin/env bash
# install_qgis_ubuntu.sh
# qskos QGIS Plugin - install QGIS (LTR) + python3-qgis and create a uv venv
# with pytest + pytest-qgis for the QGIS-bound test suite
# (tests/test_qgis_plugin.py).
#
# Works both in WSL and in a GitHub Actions Ubuntu runner. Requires sudo
# (for the apt install of QGIS). The test tooling is installed into a dedicated
# uv venv (--system-site-packages so it sees QGIS) — the global Python is left
# untouched.
#
# Usage:  sudo scripts/install_qgis_ubuntu.sh
#
# Why the LTR repo: the plugin imports PyQt5 (Qt5). QGIS 4.x moved to Qt6, so
# we must stay on the 3.44 Long Term Release line, which uses PyQt5/Qt5.
#
# Installs:
#   - qgis + python3-qgis from the OSGeo LTR apt repo
#   - a uv venv at .venv-qgis based on QGIS's Python with pytest + pytest-qgis

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv-qgis}"

UBUNTU_CODENAME="${UBUNTU_CODENAME:-}"
if [ -z "$UBUNTU_CODENAME" ]; then
    UBUNTU_CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
fi

# Official QGIS LTR signing key (a ready dearmored keyring) and LTR repo.
# See https://qgis.org/en/site/forusers/alldownloads.html#debian--ubuntu
OSGEO_KEY_URL="https://download.qgis.org/downloads/qgis-archive-keyring.gpg"
OSGEO_REPO_URL="https://qgis.org/ubuntu-ltr"
KEYRING="/usr/share/keyrings/qgis-archive-keyring.gpg"

echo "==> Adding OSGeo QGIS LTR apt repository (${UBUNTU_CODENAME})"
curl -fsSL "$OSGEO_KEY_URL" -o "$KEYRING"

# Modern deb822 .sources file (avoids the old flat 'deb' + signed-by dance).
SOURCE_FILE="/etc/apt/sources.list.d/qgis.sources"
cat > "$SOURCE_FILE" <<EOF
Types: deb deb-src
URIs: ${OSGEO_REPO_URL}
Suites: ${UBUNTU_CODENAME}
Architectures: amd64
Components: main
Signed-By: ${KEYRING}
EOF

echo "==> Updating apt"
apt-get update

echo "==> Installing qgis + python3-qgis"
apt-get install -y --no-install-recommends qgis python3-qgis

# QGIS's Python — the system interpreter that python3-qgis installs into.
PYBIN="${QGIS_PYTHON:-$(command -v python3)}"
echo "==> QGIS python: $PYBIN ($("$PYBIN" --version))"

if ! command -v uv >/dev/null 2>&1; then
    echo "==> uv not found — installing via pipx"
    "$PYBIN" -m pip install --user --break-system-packages pipx
    "$PYBIN" -m pipx ensurepath 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
fi

echo "==> Creating uv venv at $VENV_DIR (based on $PYBIN)"
uv venv --python "$PYBIN" --system-site-packages "$VENV_DIR"

echo "==> Installing pytest + pytest-qgis into the venv"
VIRTUAL_ENV="$VENV_DIR" uv pip install pytest pytest-qgis

echo "==> Done. Run tests with:  scripts/run_qgis_tests.sh"
