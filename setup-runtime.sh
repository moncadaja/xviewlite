#!/bin/bash

# Runtime directory relative to the Pixi project
export XDG_RUNTIME_DIR="${PIXI_PROJECT_ROOT}/.runtime"

mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Relocated environments can retain an old absolute prefix in Qt's qt.conf.
# Resolve the Qt 5 platform plugins from the environment being activated.
if [ -n "${CONDA_PREFIX:-}" ] && [ -d "$CONDA_PREFIX/plugins/platforms" ]; then
    export QT_QPA_PLATFORM_PLUGIN_PATH="$CONDA_PREFIX/plugins/platforms"
fi
