# CLAUDE.md — PAM-4 driver, IHP SG13G2 (agentic design, layout/schematic co-design case study)

**Map, not manual.** [README.md](README.md) is the narrative and the numbers; this file routes agents.

## Mission

A 96 Gb/s inductorless PAM-4 optical-modulator driver in IHP SG13G2, taken from netlist to a
DRC/LVS-clean parameterized layout, kpex extraction and the layout + electrical co-optimization
that closes all eight post-layout specs — the TCAS-2026 paper's co-design case study (Algorithm 1
through `spicexplorer-optimize`, `sim_engine: layout`; v4 is the layout of record).

## Read this before that

| you are about to… | read first |
|---|---|
| anything | `README.md` — the journey, the spec table, what reproduces from where |
| re-run or audit a number | `verification/README.md` (`make verify-report`, static ngspice decks) and `report/README.md` (`make report`) |
| touch the layout | `layout/README.md`, `layout/LAYOUT_REVIEW.md`, `layout/gen_layout.py` (the generator is the layout), `layout/codesign/README.md` (the co-design rounds) |
| change a bench | `testbenches/`, `dut/`, `netlists/` — decks are generated, never text-edited |
| draw or read a schematic | `schematics/` — the xschem sheet of record, generated from the netlist |

## Simulation lanes and reuse (contract for every agent in this repo)

- **Open-source PDK (IHP SG13G2, sky130, gf180 …) → the open lane.** ngspice (with OSDI/openvaf models) through this repo's lane
  module (`design/sim.py` or its equivalent here), KLayout / magic / netgen / kpex for layout and sign-off, xschem for schematics — natively
  on the workstation; `make doctor` proves the lane. An open-PDK bench is never routed through the commercial tools.
- **Commercial PDK under NDA → the bridge lane only.** Those simulations run on the EDA server through the lab's
  remote-simulator bridge (`virtuoso-bridge-lite`, carried by the lab's `analog-skill-directory` with its `spectre` and `virtuoso` skills): decks are built here, uploaded by basename with *relative* `include`s,
  simulated there, and only results come back. Kit bytes never reach the workstation or the model (`pdk_guard`
  blocks it); every server-side artifact is design-named, never tool-named (`naming_guard`).
- **SpiceXplorer first.** Before writing a script, use what exists and compose it: the platform packages
  (`spicexplorer_core` — `spice_engine.run_deck`, measurements; `spicexplorer_harness` — ledger, pack, lint,
  spec; `spicexplorer-optimize`; `spicexplorer_gmid`; `spicexplorer_layout` + `spicexplorer_signoff`;
  `spicexplorer_waveview`; `spicexplorer_circuitgraph`; `spicexplorer_netlist2xschem`), the orchestration
  workflows and MCP tools (`spicexplorer_orchestration.workflows`: layout, sizing, campaign, sign-off,
  literature), and the reusable agents and skills in the lab's `analog-skill-directory` (this repo's `.sx/skills` once its template migration lands). A missing function is added to the platform or the
  library by PR (gap-as-signal), never reimplemented privately in this repo.
- **Visual evidence and reports.** Every design cell and every testbench has a **human-readable xschem
  sheet** (the `schematic-of-record` and `testbench-schematic` skills): generated from the certified netlist with `spicexplorer-netlist2xschem`, proven equal
  to it, PNG render committed — never a hand drawing offered as a schematic. When a cell must live in the
  commercial schematic editor it is **ported from that sheet** through the bridge's `xvport` lane and
  re-proven identical with `circuitgraph`. Findings are **tables or plots regenerated from simulated
  data** with the spec boxes drawn (the `findings-as-plots` skill); a simulation report is one `experiments/NNN-*/` directory —
  `run.py` simulates into git-ignored `out/*.json`, figures land in committed `figs/`, `mk_readme.py`
  rewrites its README from `out/` — or this repo's documented equivalent, so no number is typed into prose.

## Rules

1. **Reference first.** A number that has not passed the frozen benches is a claim; every table in
   `README.md` regenerates from a committed script.
2. **The generator is the layout.** Every GDS, render and verdict is re-derived from
   `layout/gen_layout.py` + its parameters; hand-edited GDS does not exist here.
3. **Designer ≠ verifier.** Post-layout claims are re-measured by the reviewer flow (`report/`).
4. **Provenance.** Reference the PDK by name (`$PDK_ROOT`), never vendor model bytes; no tool name
   in any durable artifact or temp path (`$SX_SCRATCH`).

## Git

`feat/<name>` off `main` → PR → squash; the four-part PR body (What was done / Assumptions /
Errors-setbacks-gotchas / Next Steps). **Ask before pushing.** This repo is mounted in
`macanalog-design-directory` as `designs/agentic-design-pam4-driver-ihp130` (legacy name).
