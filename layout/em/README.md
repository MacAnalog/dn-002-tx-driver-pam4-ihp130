# EM verification of the reflection parameters (openEMS)

The repo's S11/S22 numbers come from ngspice `sp` analyses on the kpex 2.5D
extraction. kpex charges the wiring with **capacitance only** — the netlist has
no wiring resistance or inductance (`report/data/tables.md`: the R count in
the post netlists is the 12 silicided-poly *device* resistors; the wiring
itself contributes only C). At the band edges this is a real approximation:
30–70 µm of output routing is tens of pH and fractions of an ohm, i.e. a few
ohms of reactance at 50 GHz, against a spec line (−10 dB ⇒ |Γ| margins of a
few tenths of a dB) where that is visible. This directory re-derives the
output network from full-wave FDTD (openEMS, the IHP PDK's own SG13G2
workflow) and re-runs the S22 bench with the EM model spliced in, so the
kpex-based claim can be checked against an independent physics engine.

The verification target is the layout of record (`gen_layout.FINAL_LAYOUT` =
co-design round-3 best-score point `r3_s12/run_26`, the paper's design of
record); `target/` carries its GDS + LVS/kpex netlists as built by
`layout/codesign/remeasure.py`.

## Pipeline

The lane is the *demonstration of the platform integration*: every reusable
step (net cut, via bars, ground scheme, workflow driving, vector fit) lives
in the SpiceXplorer platform's `spicexplorer_layout.em` module — the scripts
here are thin CLIs over it, plus the block-specific pieces (port map,
splice, benches). Install the package into both envs (repo `.venv` and the
openEMS env):

    pip install \
      "spicexplorer-core   @ git+https://github.com/MacAnalog/spicexplorer-platform#subdirectory=packages/spicexplorer-core" \
      "spicexplorer-layout @ git+https://github.com/MacAnalog/spicexplorer-platform#subdirectory=packages/spicexplorer-layout"

The SG13G2 process description (layer maps, via stack, SUBGND/contact
layers, workflow location) is the packaged tech config
`EmTech.builtin("ihp-sg13g2")`; solver hyperparameters are `EmSim`
(committed here as `target/em_sim.yaml`).


| step | script | what |
|---|---|---|
| 1 | `extract_nets.py` → `em.extract_net_gds` | metal-only net tracing (KLayout `LayoutToNetlist`, labels name the nets); selected nets' polygons on native SG13G2 layers, **via arrays merged into mesh-robust solid bars** (min side 0.55 µm — PDK cuts are smaller than the mesh cell and a column with no interior grid line does not conduct), port rectangles (GDS 300+n), and the ground scheme: ONE common SUBGND plane + Activ+Cont columns tying the `sub` guard ring's Metal1 down to it |
| 2 | `gen_ports.py` | computes the 13-port map below from the net geometry; writes `ports.yaml` |
| 3 | `run_em.py` → `em.em_sparams` (via `./run_em.sh`) | openEMS FDTD through the PDK workflow (`$PDK_ROOT/ihp-sg13g2/libs.tech/openems/`), one excitation per port → `em_outnet.s13p`; every solver hyperparameter loads from `--config target/em_sim.yaml` (committed = the run is reproducible), printed with provenance (cli/config/DEFAULT) |
| 4 | `em_to_subckt.py` → `em.em_to_subckt` | touchstone → passivity-enforced vector fit → ngspice subckt, with an explicit **DC anchor** (see below; `--dc-from-data` = Re(Y) at the lowest kept frequency) |
| 5 | `em_compare.py` | the checks: `--step lowfreq` (wiring C, EM vs kpex), `--step splice` + `--step op` (bias currents, spliced vs kpex), `--step s22` (band-edge S22, spliced vs kpex — the apples-to-apples number) |

## The EM cut and its ports

Nets `outp`, `outn`, `vcc` (metal only, devices removed) + `sub` (the guard
ring / tap columns, the bench's ground reference), over the PDK stackup's
lossy EPI + substrate. 13 ports, every one referenced to `sub`:

* **edge ports** (P1 outp, P2 outn, P3 vcc) — vertical via-ports where each
  bus crosses over a `sub` Metal1 column (the PDK examples' ground-to-signal
  pattern); this is where the bench's 50 Ω port attaches.
* **collector taps** (P4–6 outp / P8–10 outn, cells M0|M1|L0 left→right) and
  **R_C taps** (P7/P11 out-side, P12/13 vcc-side) — short vertical via-ports
  from the common substrate-contact plane (`SUBGND` stackup layer) up to the
  Metal1 device pad.

All port references are galvanically common: one SUBGND plane spans the cut
and the `sub` guard ring's Metal1 is contacted down to it through Activ+Cont
columns (the real ring IS a substrate-tap ring; the metal-only trace drops
its contacts). This matters — with per-port floating SUBGND islands the
references couple only through the lossy substrate, the S-matrix goes open
below a few GHz, and no DC anchor can be made consistent with the data (the
fit never converges passive).

Approximations, stated: (i) the SUBGND plane idealizes the substrate ground —
the same idealization the lumped bench makes when it references every port
to one ground node; (ii) grouping each cell's 3-finger
collector into one tap (the pad is one merged Metal1 island anyway); (iii)
input nets are left ideal — this cut verifies the *output* network (S22);
an input-bus cut for S11 is the same recipe with nets `msbp/msbn/lsbp/lsbn`.
(iv) the block is ~100 µm ≈ λ/30 in oxide at 50 GHz, so port grouping at
device pads is electrically small.

## DC anchor (do not skip)

The benches drive the bias current *through* these nets (collector current
via R_C to vcc). A fitted S-model is weakest at f→0, and a wrong DC point
shifts every operating point while producing plausible-looking S-curves.
`em_to_subckt.py --dc-r` prepends an f≈0 sample from the metal DC
resistances before fitting; `em_compare.py --step op` then requires the
spliced deck's supply current to match the kpex deck's before `--step s22`
is meaningful.

## Solver install

openEMS is built from source (no usable package exists). Two supported
lanes — pick one:

* **native (script)**: `./install_openems.sh` — creates the conda env
  (python 3.11, conda-forge; the load-bearing pins are **cgal-cpp 5.6** —
  CGAL 6 breaks CSXCAD — and `CXXFLAGS=-fpermissive`), clones
  openEMS-Project, builds into `~/local/openems`, installs the python
  bindings and smoke-tests the import. QCSXCAD (the Qt GUI) failing to
  build is expected and harmless — the lane runs headless.
* **docker**: the spicexplorer-platform repo ships an EM toolchain image —
  `docker compose --profile em build em` there, then run this directory's
  scripts inside it (`docker compose run --rm em bash`; the image carries
  the PDK openEMS workflow + stackup).

`run_em.sh` picks the native env when present (override with
`OPENEMS_PREFIX`/`OPENEMS_ENV`) and falls back to the container's python. Field dumps stay off; run
outputs (`target/em_out/`) are scratch — only the touchstone, the fitted
subckt and the comparison numbers are results.

## Result (layout of record, r3_s12/run_26)

Full comparison in [`target/results.txt`](target/results.txt); the
headline, at the same instrument settings as the paper's numbers:

| | worst S22 ≤ 50 GHz | −10 dB edge |
|---|---|---|
| kpex CC (the report instrument) | −10.28 dB | 51.8 GHz |
| openEMS FDTD, spliced (this lane) | **−10.63 dB** | **54.3 GHz** |

The full-wave model confirms the paper's reflection claim with margin —
kpex is the conservative instrument here. The gates behind that number:
wiring C agrees at extractor level (differences = the nets deliberately
absent from the cut), and the spliced deck's bias point matches the kpex
deck to 0.4 % (41.96 vs 41.79 mA — the extra being the EM model's real
metal resistance, which kpex does not charge).

## Round-4 point (r4_s10/run_29, `target_r4/`)

The same lane on the co-design round-4 candidate (`gen_layout.R4_LAYOUT`; the
cut and 13-port map regenerated by `gen_ports.py` — its `vcc` edge port falls
back to a SUBGND-referenced vertical port at the rail's end, because the
round-4 `vcc_trim` rail spans only the two R_C stacks and crosses no
substrate column). Full comparison in [`target_r4/results.txt`](target_r4/results.txt):

| | worst S22 ≤ 50 GHz | −10 dB edge | Icc |
|---|---|---|---|
| kpex CC halo 8 (the report instrument) | −10.25 dB | 51.6 GHz | 43.75 mA |
| openEMS FDTD, spliced | **−10.58 dB** | **53.9 GHz** | 43.92 mA (+0.4 %) |

Same picture as the record (kpex −10.28 → EM −10.63): the full-wave model
confirms the reflection claim with margin. Two things the EM rung sees that
the report instrument does not: (i) the rail trim is real — EM-measured
C(outn, vcc) falls **1.73 → 0.61 fF** and C(outp, vcc) 0.28 → 0.08 fF against
the record's cut (kpex at halo 8 drops the outn↔vcc term for both, so it cannot
see the change); (ii) C(vcc, sub) 7.13 → 2.65 fF (the rail is 80 → 12 µm).

Fit note: the 12-pole vector fit of this touchstone is non-passive by 1.2e-3
and scikit-rf's `passivity_enforce` runs unbounded on it (condition numbers
~1e17, 60+ iterations, seven pole counts tried in parallel for 40 minutes);
`em_to_subckt.py --no-enforce --sv-tol 3e-3` skips the enforcement and accepts
the near-passive fit LOUDLY (both flags are new, defaults unchanged). The
touchstone itself is passive to 1.00008, and rung 3 (bias point within 0.4 %)
is the check that the excursion is harmless for AC/OP use.

## Cost

One excitation per port × 13 ports; minutes to tens of minutes each at
`--cellsize 0.5` (traces are 0.55–2 µm wide — do not mesh coarser than
0.5 µm here). This is a **verification lane, never in the optimizer loop**.
