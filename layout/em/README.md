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

| step | script | what |
|---|---|---|
| 1 | `extract_nets.py` | metal-only net tracing (KLayout `LayoutToNetlist`, labels name the nets); writes the selected nets' polygons to `em_outnet.gds` on native SG13G2 layer numbers + port rectangles (GDS 300+n) + SUBGND patches (GDS 210) |
| 2 | `gen_ports.py` | computes the 13-port map below from the net geometry; writes `ports.yaml` |
| 3 | `run_em.py` (via `./run_em.sh`) | openEMS FDTD through the PDK workflow (`$PDK_ROOT/ihp-sg13g2/libs.tech/openems/`), one excitation per port → `em_outnet.s13p` |
| 4 | `em_to_subckt.py` | touchstone → passivity-enforced vector fit → ngspice subckt, with an explicit **DC anchor** (see below) |
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
  from an idealized local substrate contact (`SUBGND` stackup layer, drawn
  under the pad) up to the Metal1 device pad.

Approximations, stated: (i) the SUBGND patches idealize the local substrate
potential at each device — the same idealization the lumped bench makes when
it references every port to one ground; (ii) grouping each cell's 3-finger
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

## Solver install (research server)

openEMS is built from source (no packages): conda env
`~/local/openems-env` (python 3.11, conda-forge: cmake, compilers,
boost-cpp, hdf5, vtk, **cgal-cpp 5.6** — CGAL 6 breaks CSXCAD — tinyxml,
cython, numpy, h5py, matplotlib, gdspy, pyyaml, scikit-rf), then

    cd ~/local/src/openEMS-Project
    export CMAKE_PREFIX_PATH=~/local/openems-env CXXFLAGS="-fpermissive"
    ./update_openEMS.sh ~/local/openems --python   # QCSXCAD (Qt GUI) fails: fine
    CSXCAD_INSTALL_PATH=~/local/openems pip install --no-build-isolation CSXCAD/python openEMS/python

`run_em.sh` sets the env + `LD_LIBRARY_PATH`. Field dumps stay off; run
outputs (`target/em_out/`) are scratch — only the touchstone, the fitted
subckt and the comparison numbers are results.

## Cost

One excitation per port × 13 ports; minutes to tens of minutes each at
`--cellsize 0.5` (traces are 0.55–2 µm wide — do not mesh coarser than
0.5 µm here). This is a **verification lane, never in the optimizer loop**.
