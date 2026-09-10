# PAM-4 driver (2-bit current-mode DAC, SiGe HBT) — ported netlists + testbenches

Port of the **EIC-designer `lumped-broadband-driver` verified reference** —
a block-level replication of *Inac, Peczek, Gerfers, Malignaggi, "Inductorless
96 Gb/s PAM-4 Optical Modulators Driver in SiGe:C BiCMOS", EuMIC 2022* —
into the spicexplorer analog-db staging area. **The first bipolar (HBT)
circuit in the SpiceXplorer repos.** PDK: IHP SG13G2 (`npn13G2` VBIC HBT,
`cornerHBT.lib`), no OSDI needed.

**Provenance:** `~/code/EIC-designer/projects/lumped-broadband-driver/` (16/16
requirements verified, dual sign-off). The port reproduces the EIC golden
reference **bit-exact to the reported precision — zero delta on all 8
system metrics** (see `results/pam4_results.yaml` → `vs_eic_golden`).

## Three DUTs

The driver is factored into three standalone DUT subcircuits (`dut/`),
mirroring the paper's figures:

| DUT | Subckt | Contents | Paper figure |
|---|---|---|---|
| `lsb` | `pam4drv_lsb` | 1 differential-cascode gain cell + R_C + R_B | Fig. 2(a) |
| `msb` | `pam4drv_msb` | 2 identical gain cells in parallel + shared R_C/R_B | Fig. 2(b) |
| `pam4` | `pam4drv_pam4` | 1 LSB + 2 MSB cells current-summing into shared R_C | Fig. 1 |

**Nominal sizing and bias** (the EIC-verified point):

| quantity | value |
|---|---|
| device | `npn13G2`, Nx = 3 |
| tail current per cell | 16 mA (8 mA/device, at peak f_T) |
| R_E | 2.5 Ω/side |
| C_deg | 20 fF |
| R_C | 50 Ω/side |
| R_B | 50 Ω/side |
| V_casc | 3.25 V |
| V_CM | 1.9 V |
| VCC | 4 V |

**DUT port convention:** `... vcc vcasc vcmb bias` — single-input DUTs
`inp inn outp outn ...`; pam4 `lsbp lsbn msbp msbn outp outn ... blsb bmsb`.

**Tail currents are VCCS-driven, 1 mA/V** from the `bias`/`blsb`/`bmsb`
ports, so one DUT netlist serves both the ramped-transient testbenches
(PWL 0→16 V) and the DC/AC testbenches (DC 16).

**Tail sources and input terminations are ideal** — block-level fidelity as
in the EIC reference: no bias mirrors, no pad parasitics, so the simulated
bandwidth is optimistic against measurement, as disclosed there.

## Repository map

```
dut/            dut_{lsb,msb,pam4}.spice     DUT subcircuits
netlists/       tb_*.spice + .spiceinit      static, directly runnable decks
testbenches/    driver_lib.py                builders + runners + extractors
                run_verify.py                full characterization (tran + ac)
                run_eye.py                   48 GBaud PAM-4 eye + metrics
                dump_netlists.py             regenerates dut/ + netlists/
results/        <dut>_results.yaml, *.png    metrics + plots (committed)
schematics/     dut_*.sch/svg/png            xschem schematics (see below)
layout/         gen_layout.py + signoff/PEX  parameterized gdsfactory GDS
                                             (DRC+LVS PASS, kpex+sim loop —
                                             see layout/README.md)
layout/codesign/ flow.yaml, project_setup.yaml, layout/schematic co-design
                measure_post.py, results/    through the SpiceXplorer platform
                                             (paper Alg. 1) — the layout of
                                             record; see layout/codesign/README.md
layout/em/      run_em.py, em_to_subckt.py   openEMS full-wave FDTD re-check
                target/, target_r4/          of the record's output network and
                                             its S22; see layout/em/README.md
notebooks/      01_schematic_sizing          case-study notebooks (jupytext .py
                02_layout_in_the_loop        sources; .ipynb generated locally):
                03_signoff                   sizing, layout/electrical co-opt
                04_codesign_platform         with DRC/LVS/PEX/spice in the
                                             loop, full pre/post-layout signoff
                                             (DC/tran/AC/eye), and the platform
                                             co-design record
report/         build_report.py + README.md  reviewer report: schematic vs
                figs/ data/ layout/ schematic/ all layout tiers, every bench,
                                             DRC/LVS/PEX evidence (make report)
verification/   verify.py, decks/,           re-run every final number from
                extract.py, expected.json    static ngspice decks + DRC/LVS
                                             (make verify-report)
```

## Running

Static decks (from `netlists/`, where the `.spiceinit` lives):

```sh
export PDK_ROOT=$HOME/local/pdks PDK=ihp-sg13g2
cd netlists && ngspice -b tb_pam4_sparam_msb_1ghz.spice
```

Full characterization (needs numpy/matplotlib/pyyaml on the python path;
`make verify` and `make eye` at the repo root run the same two scripts inside
the `uv` environment):

```sh
cd testbenches
python run_verify.py all      # or: lsb | msb | pam4
python run_eye.py
```

**`.spiceinit` is mandatory**: it sets the model `sourcepath` and
`set ngbehavior=hsa`. Without `hsa` the IHP models parse but the HBT
conducts **0 A silently**. The python runners write their own `.spiceinit`
into each run's temp dir (PDK resolved from `$PDK_ROOT/$PDK`, falling back
to `~/local/pdks/ihp-sg13g2`, then the platform-vendored
`docker/pdk/ihp-sg13g2`).

## Measurement methods — and the JPP-361 update

Every metric is computed by **two independent methods** and cross-checked:

1. **`tran` (golden, EIC-validated):** ramp-everything-from-0 (`tran … uic`
   with PWL supplies), single-tone sine probe, single-bin DFT (least-squares
   cos/sin projection) of the steady window. S21 as differential power-wave
   gain `2·Vout/Vsrc` into 50 Ω/side references (the paper's VNA convention);
   S11/S22 via `Z = V/I` at the port.
2. **`sp`:** plain `.op` + ngspice's built-in S-parameter analysis (`sp dec …`,
   port sources `portnum`/`z0 50`; differential Sdd formed from the p/n port
   pair), full sweep in one run (~30× cheaper). The original in-deck
   power-wave algebra (`.ac`, `zin = vdiff·100/(1−vdiff)`, `S = (z−100)/(z+100)`,
   `S21 = 2·Vout/Vsrc`) is kept as `method="algebra"` and agrees to all printed
   digits (`verification/`).

**EIC finding JPP-361 — "the self-heating VBIC HBT does not converge in
ngspice `.op`/`.ac`/`.dc`" — reproduces on ngspice-44 but NOT on
ngspice-45.** On ngspice-45 (KLU), single-device and full-driver `.op`,
`.dc` and `.ac` all converge with self-heating enabled, and agree with the
transient-DFT golden numbers:

| quantity | worst disagreement with the transient-DFT golden |
|---|---|
| LF gain | ≤ 0.011 dB |
| S11 / S22 spot points | ≤ 0.01 dB |
| bias | ≤ 0.1 % |

Consequence for the optimizer case study:

- **ngspice-45:** the cheap `.ac` path is usable per candidate, with the
  transient probes retained as the method-independent check.
- **ngspice-44:** use the transient probes only.

## Results (pre-layout, nominal, typical corner)

`pam4` (combined system) vs the EIC golden reference — all deltas 0.000.
Regenerated by `make verify` and `make eye` into `results/pam4_results.yaml`
(`vs_eic_golden`) and `results/pam4_eye_metrics.yaml`:

| Metric | Value | Paper spec |
|---|---|---|
| LSB / MSB LF gain | 3.10 / 9.07 dB | 3.2 / 9.2 dB measured |
| 3-dB BW (LSB / MSB) | 70.0 / 68.5 GHz | ≥ 50 GHz (block model optimistic) |
| S11 (worst ≤ 32 GHz) | −10.87 dB | < −10 dB |
| S22 (worst ≤ 50 GHz) | −14.76 dB | < −10 dB |
| Power | 191.03 mW @ 4 V | ≤ 192 mW |
| Max diff swing | 2.92 Vpp (at 1577 mVpp input, the top of the drive sweep) | ≥ 2.1 Vpp |
| 48 GBd PAM-4 eye | RLM 0.975, ~265 mV eye openings | Fig. 5 |

**These are not the README's tier (a) column.** The same schematic
re-measured by `report/build_report.py` reads 92.7 GHz LSB bandwidth and
2.37 Vpp swing (README "Results"). The eye difference is accounted for —
these runners sample at a fixed phase and read RLM ≈ 0.97, the report reads
the eye centre and gets 0.995 — but the bandwidth and swing pair is not
reconciled in either document.

**Standalone cells** (`lsb`/`msb` DUTs, new characterization):

| DUT | LF gain | power | S11 |
|---|---|---|---|
| `lsb` | 3.1 dB | 63.7 mW | ≤ −16.4 dB to 32 GHz |
| `msb` | 9.07 dB | 127.3 mW | ≤ −10.87 dB |

That ordering matches the paper's observation: LSB input reflection is lower
because it carries half the input capacitance, and MSB dominates the S11
budget.

## Schematics (`schematics/`)

**Generated with `spicexplorer-netlist2xschem`** from the DUT netlists, then
hand-edited to follow the paper's figures:

| sheet | paper figure | note |
|---|---|---|
| `dut_lsb.sch` | Fig. 2(a) | — |
| `dut_msb.sch` | Fig. 2(b) | — |
| `dut_pam4.sch` | Fig. 1 | top view with amp-block symbols; presentation sheet |
| `dut_pam4_flat.sch` | — | the flat, connectivity-true sheet |

The authoritative netlist is always `../dut/dut_pam4.spice`.

**Open with `xschem`** from `schematics/` — the local `xschemrc` resolves the
IHP `npn13G2` symbols via `$PDK_ROOT`. Rendered `.svg`/`.png` are committed
alongside.

**Tooling note:** `netlist2xschem` gained an HBT symbol mapping for this port
(`npn13G2[l|v]` subckt primitives → `sg13g2_pr/*.sym`, in
`packages/spicexplorer-netlist2xschem/.../mapping.py`). The VCCS tail (`G…`)
is not ingested by the tool — no `G` prefix support yet — and was drawn by
hand with `devices/vccs.sym` in the edited sheets.

## Toward the TCAS-2026 case study

**This port was step 1** — runnable netlists plus validated metric
extraction — of the plan in
`spicexplorer-tcas-2026/doc/pam4_driver_case_study_feasibility.md`. The later
steps are now in this repo:

- **Parameterized layout generator and signoff/PEX chain** — `layout/`.
- **Layout-in-the-loop optimization** — `notebooks/02`.
- **Full pre/post-layout signoff** — `notebooks/03`.
- **Layout/schematic co-design *through the SpiceXplorer platform*** —
  `layout/codesign/`, `notebooks/04`. It produced the layout of record: the
  round-3 best-score point `r3_s12/run_26`, the paper's design of record, at
  post-layout S11 −10.16 dB / S22 −10.28 dB on the block's halo-8 instrument,
  167 mW, 7268 µm². The round-3 accepted point v4 is kept as `V4_LAYOUT`.

**The `bias`-port VCCS convention makes the tail current a plain `.param`
knob** for the optimizer, which is how the electrical knobs (nx, tail, R_C,
R_B, C_deg, V_casc) enter the joint search.

**Reviewer-facing evidence for every claim** is regenerated by `make report`
into `report/`.
