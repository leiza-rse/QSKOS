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

# When run via sudo, $HOME is root's; the invoking user's uv lives in their
# own home. Resolve it so we find the right per-user uv.
REAL_USER="${SUDO_USER:-$(id -un)}"
REAL_HOME="$(getent passwd "$REAL_USER" | cut -d: -f6)"
if [ -z "$REAL_HOME" ]; then
    REAL_HOME="$HOME"
fi

# Locate uv. It is often installed per-user (~/.local/bin), which is not on
# root's PATH under sudo, so search it explicitly.
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [ -z "$UV_BIN" ] && [ -x "$REAL_HOME/.local/bin/uv" ]; then
    UV_BIN="$REAL_HOME/.local/bin/uv"
fi
if [ -z "$UV_BIN" ] && [ -x "/usr/local/bin/uv" ]; then
    UV_BIN="/usr/local/bin/uv"
fi
if [ -z "$UV_BIN" ]; then
    echo "error: uv not found. Install it first, e.g.:" >&2
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    echo "then re-run:  sudo scripts/install_qgis_ubuntu.sh" >&2
    exit 1
fi
echo "==> uv: $UV_BIN"

# Run the venv + pip steps as the invoking user (not root) so .venv-qgis is
# owned by the developer, not root. 'sudo -u -H' sets HOME to their home so uv
# uses the right cache/install locations.
run_as_user() {
    if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
        sudo -u "$SUDO_USER" -H env "UV_BIN=$UV_BIN" "VENV_DIR=$VENV_DIR" \
            "PYBIN=$PYBIN" "$@"
    else
        env "UV_BIN=$UV_BIN" "VENV_DIR=$VENV_DIR" "PYBIN=$PYBIN" "$@"
    fi
}

echo "==> Creating uv venv at $VENV_DIR (based on $PYBIN)"
# --clear replaces any pre-existing venv without prompting (needed for CI).
run_as_user bash -c '"$UV_BIN" venv --clear --python "$PYBIN" --system-site-packages "$VENV_DIR"'

echo "==> Installing pytest + pytest-qgis into the venv"
run_as_user bash -c 'VIRTUAL_ENV="$VENV_DIR" "$UV_BIN" pip install pytest pytest-qgis'

echo "==> Done. Run tests with:  scripts/run_qgis_tests.sh"
