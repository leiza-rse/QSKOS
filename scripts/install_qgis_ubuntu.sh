#!/usr/bin/env bash
# install_qgis_ubuntu.sh
# qskos QGIS Plugin - install QGIS (LTR) + python3-qgis and pytest-qgis on
# Ubuntu, for running the QGIS-bound test suite (tests/test_qgis_plugin.py).
#
# Works both in WSL and in a GitHub Actions Ubuntu runner. Requires sudo.
#
# Usage:  sudo scripts/install_qgis_ubuntu.sh
#
# Why the LTR repo: the plugin imports PyQt5 (Qt5). QGIS 4.x moved to Qt6, so
# we must stay on the 3.44 Long Term Release line, which uses PyQt5/Qt5.
#
# Installs:
#   - qgis + python3-qgis from the OSGeo LTR apt repo
#   - pytest + pytest-qgis into QGIS's own Python (site-packages)
#     so `python3 -m pytest` uses real QGIS objects.

set -euo pipefail

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

# Identify QGIS's Python so we can pip into the right interpreter.
PYBIN="${QGIS_PYTHON:-}"
if [ -z "$PYBIN" ]; then
    # Debian/Ubuntu package puts the QGIS python at /usr/bin/python3 (system).
    PYBIN="$(command -v python3)"
fi
echo "==> QGIS python: $PYBIN"

echo "==> Installing pytest + pytest-qgis into QGIS python"
"$PYBIN" -m pip install --upgrade pip
# Ubuntu 24.04+ marks the system Python as externally-managed (PEP 668);
# --break-system-packages lets us install into QGIS's system interpreter.
"$PYBIN" -m pip install --break-system-packages pytest pytest-qgis

echo "==> Done. Run tests with:  scripts/run_qgis_tests.sh"
