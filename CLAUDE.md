# CLAUDE.md — PAM-4 driver, IHP SG13G2 (agentic design, layout/schematic co-design case study)

**Map, not manual.** [README.md](README.md) carries the design history and the numbers; this file routes agents.

## Mission

A 96 Gb/s inductorless PAM-4 optical-modulator driver in IHP SG13G2, taken from netlist to a
DRC/LVS-clean parameterized layout, kpex extraction and the layout + electrical co-optimization
that closes all eight post-layout specs — the TCAS-2026 paper's co-design case study (Algorithm 1
through `spicexplorer-optimize`, `sim_engine: layout`).

**The layout of record is `gen_layout.FINAL_LAYOUT`** — the co-design round-3 best-score point
`r3_s12/run_26`, report tier (f). `V2_LAYOUT`, `V3_LAYOUT` and `V4_LAYOUT` are the earlier points;
`R4_LAYOUT` is the round-4 reviewer-response point (tier (g)). None of those four is the record: owner
ruling 2026-09-02 keeps the paper's round-3 column (`layout/gen_layout.py`, above `R4_LAYOUT`).

## Read this before that

| you are about to… | read first |
|---|---|
| anything | `README.md` — the design history, the spec table, what reproduces from where |
| re-run or audit a number | `verification/README.md` (`make verify-report`, static ngspice decks) and `report/README.md` (`make report`) |
| touch the layout | `layout/README.md`, `layout/LAYOUT_REVIEW.md`, `layout/gen_layout.py` (the generator is the layout), `layout/codesign/README.md` (the co-design rounds) |
| change a bench | `testbenches/`, `dut/`, `netlists/` — decks are generated, never text-edited |
| draw or read a schematic | `schematics/` — the xschem sheet of record, generated from the netlist |

## Simulation lanes and reuse (contract for every agent in this repo)

- **Open-source PDK (IHP SG13G2, sky130, gf180 …) → the open lane.** ngspice (with OSDI/openvaf models) through
  this repo's lane module — here `testbenches/driver_lib.py` — plus
  KLayout / magic / netgen / kpex for layout and sign-off and xschem for schematics, natively on the
  workstation; `make doctor` proves the lane. An open-PDK bench is never routed through the commercial tools.
- **Commercial PDK under NDA → the remote lane only.** Those simulations run on the lab's licensed-tool
  machine through the remote-simulator lane carried by the lab's `analog-skill-directory`: decks are built
  here, uploaded by basename with *relative* `include`s, simulated there, and only results come back. Kit
  bytes never reach the workstation or the model (`pdk_guard` blocks it); every artifact on that machine is
  design-named, never tool-named (`naming_guard`).
  **A declined kit-access prompt is never a stop:** continue without those bytes (the kit is consumed by
  path on that machine; open-PDK files are unrestricted; ask the person one sentence if a kit fact is needed).
- **SpiceXplorer first.** Before writing a script, compose what exists. A missing function is added to the
  platform or the library by PR (gap-as-signal), never reimplemented privately in this repo.
  - **Platform packages:** `spicexplorer_core` (`spice_engine.run_deck`, measurements), `spicexplorer_harness`
    (ledger, pack, lint, spec), `spicexplorer-optimize`, `spicexplorer_gmid`, `spicexplorer_layout` +
    `spicexplorer_signoff`, `spicexplorer_waveview`, `spicexplorer_circuitgraph`, `spicexplorer_netlist2xschem`.
  - **Orchestration workflows and MCP tools:** `spicexplorer_orchestration.workflows` — layout, sizing,
    campaign, sign-off, literature.
  - **Reusable agents and skills:** the lab's `analog-skill-directory` (this repo's `.sx/skills` once its
    template migration lands).
- **Visual evidence and reports.** No number is typed into prose; every schematic and every finding is
  regenerated from committed data.
  - **Schematics:** every design cell and every testbench has a **human-readable xschem sheet** (the
    `schematic-of-record` and `testbench-schematic` skills), generated from the certified netlist with
    `spicexplorer-netlist2xschem`, proven equal to it, PNG render committed — never a hand drawing offered
    as a schematic. When a cell must live in the commercial schematic editor it is **ported from that
    sheet** through the remote lane's `xvport` path and re-proven identical with `circuitgraph`.
  - **Findings:** **tables or plots regenerated from simulated data** with the spec boxes drawn (the
    `findings-as-plots` skill). A simulation report is one `experiments/NNN-*/` directory — `run.py`
    simulates into git-ignored `out/*.json`, figures land in committed `figs/`, `mk_readme.py` rewrites its
    README from `out/` — or this repo's documented equivalent (`report/build_report.py` into `report/`).

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
`macanalog-design-directory` as `designs/dn-002-tx-driver-pam4-ihp130`
(was `agentic-design-pam4-driver-ihp130`; GitHub redirects the old name).
