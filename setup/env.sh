#!/bin/bash
# Source in each new terminal:  source setup/env.sh   (from the project root)
# Loads OpenFOAM-14, AdditiveFOAM and the project Python venv.

PROJECT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
export PROJECT_DIR

. /opt/openfoam14/etc/bashrc
. "$PROJECT_DIR/external/AdditiveFOAM/etc/bashrc"

if [ -f "$PROJECT_DIR/.venv/bin/activate" ]
then
    . "$PROJECT_DIR/.venv/bin/activate"
fi

echo "OpenFOAM-$WM_PROJECT_VERSION | AdditiveFOAM $ADDITIVEFOAM_VERSION | project $PROJECT_DIR"
