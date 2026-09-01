#!/bin/bash
# Env wrapper for the openEMS harness: the solver lives in its own conda env
# (build notes in README.md), everything else in this repo's .venv.
#   ./run_em.sh run_em.py target/em_outnet.gds target/ports.yaml --out target/em_out
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$HOME/local/openems-env"
export LD_LIBRARY_PATH="$HOME/local/openems/lib:$HOME/local/openems-env/lib:$LD_LIBRARY_PATH"
exec python "$@"
