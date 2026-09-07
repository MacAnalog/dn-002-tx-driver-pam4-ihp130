# PAM-4 SiGe HBT driver — flow entry points.
# All Python runs through the uv-managed env (see pyproject.toml / uv.lock).
#
#   make sync       install/update the Python environment
#   make verify     schematic verification benches (results/*.yaml)
#   make eye        PAM-4 eye simulation (results/pam4_eye*.{yaml,png})
#   make signoff    layout DRC + LVS on all three DUTs
#   make notebooks  execute all four notebooks (.py -> .ipynb via jupytext)
#   make codesign   one island of the platform co-design loop (paper Alg. 1)
#   make report     rebuild the reviewer report (report/: figs, data, layout evidence)
#   make verify-report  re-run every number of the final results from static decks + DRC/LVS (verification/)
#   make test       unit tests (tests/) — no simulator, no PDK activation needed
#   make all        verify + eye + signoff + notebooks

# Machine-specific tool locations live in an untracked local.mk
# (PDK_ROOT, and optionally KPEX / KPEX_KLAYOUT_EXE) — see README
# "EDA tool setup". Nothing personal belongs in this Makefile.
-include local.mk

PDK      ?= ihp-sg13g2
PDK_ROOT ?= $(error PDK_ROOT is not set — export it or put it in local.mk, \
see README "EDA tool setup")
ENV       = PDK_ROOT=$(PDK_ROOT) PDK=$(PDK) \
            $(if $(KPEX),KPEX=$(KPEX)) \
            $(if $(KPEX_KLAYOUT_EXE),KPEX_KLAYOUT_EXE=$(KPEX_KLAYOUT_EXE))
RUN       = $(ENV) uv run

# notebook 02's optimizer budget (trials through gen_layout -> DRC/LVS ->
# kpex -> ngspice); the committed result used the default of 8.
NB_BUDGET ?= 8

.PHONY: all sync verify eye signoff notebooks nb01 nb02 nb03 nb04 codesign report verify-report clean

all: verify eye signoff notebooks

sync:
	uv sync

verify:
	cd testbenches && $(RUN) python run_verify.py all

eye:
	cd testbenches && $(RUN) python run_eye.py

signoff:
	cd layout && $(RUN) python signoff.py

notebooks: nb01 nb02 nb03 nb04

nb01:
	cd notebooks && $(RUN) jupytext --to notebook --execute 01_schematic_sizing.py

nb02:
	cd notebooks && $(ENV) NB_BUDGET=$(NB_BUDGET) uv run jupytext --to notebook --execute 02_layout_in_the_loop.py

nb03:
	cd notebooks && $(RUN) jupytext --to notebook --execute 03_signoff.py

nb04:
	cd notebooks && $(RUN) jupytext --to notebook --execute 04_codesign_platform.py

# one island of the layout/schematic co-design through the SpiceXplorer platform
# (paper Alg. 1): make codesign ROUND=r3 SEED=0 BUDGET=40 [ALGO=OnePlusOne]
ROUND ?= r3   # next round (r1/r2 are on the record)
SEED ?= 0
BUDGET ?= 40
ALGO ?= OnePlusOne
codesign:
	cd layout/codesign && $(ENV) ./run_round.sh $(ROUND) $(SEED) $(BUDGET) $(ALGO)

# reviewer report: schematic + v1/v2/v3 layouts rebuilt from the generator,
# DRC/LVS/kpex re-run, every bench re-simulated, KLayout renders, eyes, tables.
# REPORT_ARGS='--skip-build --nsym 200' reuses report/work/<tier> artifacts.
REPORT_ARGS ?=
report:
	$(RUN) python report/build_report.py $(REPORT_ARGS)

# verification/: plain `ngspice -b` on the static decks + KLayout DRC/LVS + GDS regen,
# every number compared with verification/expected.json.  VERIFY_ARGS='--tier d --no-eye'
VERIFY_ARGS ?=
verify-report:
	$(RUN) python verification/verify.py $(VERIFY_ARGS)

clean:
	rm -rf notebooks/nb_opt notebooks/*.ipynb layout/out/signoff report/work verification/work
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

test:  ## unit tests (tests/): fast, no simulator, no PDK activation
	uv run pytest -q tests
