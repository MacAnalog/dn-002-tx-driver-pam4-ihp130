#!/usr/bin/env bash
# Build the openEMS FDTD toolchain for the EM lane, from source (there is no
# usable wheel/package), into a self-contained prefix + conda env.
#
#     ./install_openems.sh [BUILD_PREFIX] [CONDA_ENV_PREFIX]
#     # defaults:          ~/local/openems  ~/local/openems-env
#
# Needs: conda (or mamba/micromamba via $CONDA_EXE), git, ~10 min of compile.
# Validated on the research server (RHEL 8). The pinned points that matter:
#   * cgal-cpp 5.6 — CGAL 6 breaks CSXCAD's template code
#   * CXXFLAGS=-fpermissive — CSXCAD still needs it against CGAL 5.6 headers
#   * QCSXCAD (the Qt GUI viewer) fails to build headless: harmless, the lane
#     runs AppCSXCAD-free (run_em.py patches it out)
#   * the python bindings need CSXCAD_INSTALL_PATH and --no-build-isolation
# The alternative to this script is the spicexplorer-platform EM container
# (docker compose --profile em build em), which bakes the same toolchain.
set -euo pipefail

PREFIX=${1:-$HOME/local/openems}
ENVP=${2:-$HOME/local/openems-env}
SRC=${OPENEMS_SRC:-$HOME/local/src/openEMS-Project}
CONDA=${CONDA_EXE:-conda}

echo "== 1/4 conda env (compilers + libs + python deps) -> $ENVP"
"$CONDA" create -y -p "$ENVP" -c conda-forge python=3.11 cmake compilers \
    boost-cpp hdf5 vtk 'cgal-cpp=5.6' tinyxml cython numpy h5py matplotlib \
    gdspy pyyaml scikit-rf

echo "== 2/4 sources -> $SRC"
[ -d "$SRC/.git" ] || git clone --recursive \
    https://github.com/thliebig/openEMS-Project.git "$SRC"

echo "== 3/4 build -> $PREFIX  (QCSXCAD/Qt failure here is expected + harmless)"
cd "$SRC"
export CMAKE_PREFIX_PATH="$ENVP" CXXFLAGS="-fpermissive"
./update_openEMS.sh "$PREFIX" --python || true

echo "== 4/4 python bindings into the env"
CSXCAD_INSTALL_PATH="$PREFIX" "$ENVP/bin/pip" install --no-build-isolation \
    "$SRC/CSXCAD/python" "$SRC/openEMS/python"

# the only gate that counts: the bindings import and see the solver libs
LD_LIBRARY_PATH="$PREFIX/lib:$ENVP/lib" "$ENVP/bin/python" - <<'PY'
import CSXCAD, openEMS
print("openEMS python bindings OK:", openEMS.__file__)
PY
echo "done. run the lane through ./run_em.sh (it sets LD_LIBRARY_PATH + env)."
