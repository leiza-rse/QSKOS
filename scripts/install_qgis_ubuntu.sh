#!/usr/bin/env bash
# install_qgis_ubuntu.sh
# qskos QGIS Plugin - install QGIS + python3-qgis and pytest-qgis on Ubuntu,
# for running the QGIS-bound test suite (tests/test_qgis_plugin.py).
#
# Works both in WSL and in a GitHub Actions Ubuntu runner. Requires sudo.
#
# Usage:  sudo scripts/install_qgis_ubuntu.sh
#
# Installs:
#   - qgis + python3-qgis from the OSGeo apt repo
#   - pytest + pytest-qgis into QGIS's own Python (site-packages)
#     so `python3 -m pytest` uses real QGIS objects.

set -euo pipefail

UBUNTU_CODENAME="${UBUNTU_CODENAME:-}"
if [ -z "$UBUNTU_CODENAME" ]; then
    UBUNTU_CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
fi

# OSGeo QGIS apt repository (stable 3.4x / 3.44 line).
OSGEO_KEY_URL="https://qgis.org/downloads/qgis-2023.gpg.key"
OSGEO_REPO_URL="https://qgis.org/ubuntu"

echo "==> Adding OSGeo QGIS apt repository (${UBUNTU_CODENAME})"
curl -fsSL "$OSGEO_KEY_URL" | gpg --dearmor -o /usr/share/keyrings/qgis-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/qgis-archive-keyring.gpg] ${OSGEO_REPO_URL} ${UBUNTU_CODENAME} main" \
    > /etc/apt/sources.list.d/qgis.list

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
"$PYBIN" -m pip install pytest pytest-qgis

echo "==> Done. Run tests with:  scripts/run_qgis_tests.sh"
