#!/bin/bash
# Env wrapper for the openEMS harness: the solver lives in its own conda env
# (built by ./install_openems.sh, or use the spicexplorer-platform EM
# container), everything else in this repo's .venv.
#   ./run_em.sh run_em.py target/em_outnet.gds target/ports.yaml --config target/em_sim.yaml
# Override the install locations with OPENEMS_PREFIX / OPENEMS_ENV.
PREFIX="${OPENEMS_PREFIX:-$HOME/local/openems}"
ENVP="${OPENEMS_ENV:-$HOME/local/openems-env}"
if [ -x "$ENVP/bin/python" ]; then
    export LD_LIBRARY_PATH="$PREFIX/lib:$ENVP/lib:$LD_LIBRARY_PATH"
    exec "$ENVP/bin/python" "$@"
fi
# inside the platform EM container the toolchain is on PATH already
exec python3 "$@"
