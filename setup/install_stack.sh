#!/bin/bash
#------------------------------------------------------------------------------
# Install the simulation stack inside WSL2 Ubuntu (22.04 or 24.04):
#   1. OpenFOAM-14 (OpenFOAM Foundation .deb packages, installs to /opt/openfoam14)
#   2. AdditiveFOAM (git submodule external/AdditiveFOAM, built with wmake)
#   3. Python venv (.venv) for case generation and post-processing
#
# Usage (from a WSL terminal):
#   cd /mnt/d/Final_project
#   bash setup/install_stack.sh
#------------------------------------------------------------------------------
set -euo pipefail

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
ADDITIVEFOAM_DIR=$PROJECT_DIR/external/AdditiveFOAM
OPENFOAM_BASHRC=/opt/openfoam14/etc/bashrc

echo "==> Project: $PROJECT_DIR"

#--- 1. System packages and OpenFOAM-14 ---------------------------------------
if [ ! -f "$OPENFOAM_BASHRC" ]
then
    echo "==> Installing OpenFOAM-14"
    sudo apt-get update
    sudo apt-get install -y software-properties-common wget ca-certificates git \
        python3-venv python3-pip
    sudo add-apt-repository -y universe
    sudo sh -c "wget -O - https://dl.openfoam.org/gpg.key > /etc/apt/trusted.gpg.d/openfoam.asc"
    sudo add-apt-repository -y "http://dl.openfoam.org/ubuntu main dev"
    sudo apt-get update
    sudo apt-get install -y openfoam14
else
    echo "==> OpenFOAM-14 already installed at /opt/openfoam14"
fi

#--- 2. AdditiveFOAM ----------------------------------------------------------
if [ ! -f "$ADDITIVEFOAM_DIR/Allwmake" ]
then
    echo "==> Fetching AdditiveFOAM submodule"
    git -C "$PROJECT_DIR" submodule update --init external/AdditiveFOAM
fi

# OpenFOAM's bashrc references unset variables, so relax -u while sourcing
set +u
. "$OPENFOAM_BASHRC"
. "$ADDITIVEFOAM_DIR/etc/bashrc"
set -u

echo "==> Building AdditiveFOAM $ADDITIVEFOAM_VERSION against OpenFOAM-$WM_PROJECT_VERSION"
export WM_NCOMPPROCS=$(nproc)
(cd "$ADDITIVEFOAM_DIR" && ./Allwmake -j 2>&1 | tee "$PROJECT_DIR/setup/build.log")

if ! command -v additiveFoam >/dev/null
then
    echo "ERROR: additiveFoam not found on PATH after build; see setup/build.log" >&2
    exit 1
fi
additiveFoam -help >/dev/null && echo "==> additiveFoam OK: $(command -v additiveFoam)"

#--- 3. Python environment ----------------------------------------------------
echo "==> Creating Python venv in $PROJECT_DIR/.venv"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$ADDITIVEFOAM_DIR/requirements.txt"
"$PROJECT_DIR/.venv/bin/python" -m pip install -r "$PROJECT_DIR/requirements.txt"

echo
echo "Done. In every new WSL terminal run:"
echo "    source $PROJECT_DIR/setup/env.sh"
