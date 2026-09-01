# Layout/schematic co-design through the SpiceXplorer platform

The TCAS-2026 paper's **Algorithm 1** (layout-in-the-loop co-design) run on the
PAM-4 driver DAC *through* `spicexplorer-optimize` with `sim_engine: layout`:
one trial = gdsfactory build → KLayout DRC → LVS → kpex 2.5D → the block's own
`driver_lib` benches on the extracted netlist → the 8-spec score. The LLM agent
(`layout-schematic-codesign`, meta-repo `.claude/agents/`) owns the generator
`G` (`../gen_layout.py`) and the knob bounds (`project_setup.yaml`); the
platform owns the search (`Opt.ask/tell`, gates, `J`). Between rounds the agent
reads the record `R`, gets a layout review, and **fixes `G`** — every such fix
is a commit of `gen_layout.py` and a row of the rounds table below.

```
flow.yaml            layout-flow/1: generator, cell, DRC/LVS/PEX stages, measure hook (this dir; kpex CC, halo 20 = the SEARCH instrument)
flow_halo8.yaml      same flow at the block's report halo (8 um, the SG13G2 tech default)
flow_rc.yaml         same flow in RC mode (wiring R kept) — the report cross-check
remeasure.py         re-measure ONE trial of a round through another flow: remeasure.py runs/r3_s23/.../run_30_layout --tag v4h8
project_setup.yaml   sim_engine: layout; theta_E ∪ theta_L ∪ theta_S knobs, the 8 specs + gates (current round)
measure_post.py      the hook: kpex netlist -> convert -> driver_lib AC/S22/DC/bias benches -> scalars
run_round.sh         ./run_round.sh <round> <seed> <budget> [algo] [project.yaml]  (one island per process)
harvest.py           runs/<round>_s* -> results/<round>/{trials.jsonl, summary.json, best.*, accepted.*}
                     (--accept ISLAND/RUN records the ACCEPTED trial next to the argmax-J one; they differ in r3)
figures.py           annotated parameterized layout, before/after, per-round strip (drawn from the GDS)
peek.py              one line per trial while a round runs
rounds/              the project_setup.yaml of every past round (r1_..., r2_s3_... = multi-start island)
results/<round>/     the committed record R of each round (trials.jsonl, summary.json, best.gds/.png/_post.spice)
results/baseline_r2_instrument.json   the layout of record measured with the r2 instrument (the honest baseline)
*.png, *.pdf         pam4_layout_annotated / before_after (r3 pair) / before_after_r2 / rounds
                     (figures.py writes the PNG + a true-vector PDF twin)
runs/, logs/         per-trial artefacts + island logs (git-ignored; ~2 MB / trial)
```

## Running a round

```sh
# from the block repo (uv env + local.mk with PDK_ROOT / KPEX / KPEX_KLAYOUT_EXE):
make codesign ROUND=r4 SEED=0 BUDGET=40 ALGO=OnePlusOne     # = the run_round.sh line below with the env injected
cd layout/codesign
./run_round.sh r4 0 40 OnePlusOne &                                  # island 0 (from the record)
./run_round.sh r4 1 40 TwoPointsDE &                                 # island 1 (different algorithm)
./run_round.sh r4 2 40 OnePlusOne rounds/r4_s2_project_setup.yaml &   # island 2 (different init / hinges)
uv run --project ../../../../spicexplorer-platform python harvest.py --round r4 runs/r4_s* \
    --accept r4_s2/run_17_layout --instrument "band-edge S-params, kpex CC halo 20"
python3 peek.py --top 10 runs/r4_s*         # while it runs (per-trial lines + leaderboard)
python3 remeasure.py runs/r4_s2/layout/layout/run_17_layout --tag cand   # the candidate at the report halo
```

Every island is a *copy* of `project_setup.yaml` in `rounds/` differing only in
`init` (and, for the acceptance islands, in the s11/s22 hinges) — round 3 used
14 of them; r2's lesson is that structural INT knobs have to be **seeded on**
in their own island or the search never flips them.

The platform's `spicexplorer-optimize` trial loop is sequential, so wall-clock
comes from islands (separate processes / seeds). ~75 s per trial on the research
server (build 5 s, DRC 35 s, LVS 10 s, kpex 15 s, benches 6 s). Trial 1 of every
island is the `init` point (`seed_from_init: true`) — it must reproduce the
baseline scorecard (parity), or the round is not started.

## The measured story (what the loop taught us, in order)

1. **The instrument first.** The scorecard everyone had been reading (repo
   summary: S11 −10.03 / S22 −10.14 dB) took the worst in-band S-parameter on
   the ngspice `dec 20` grid, whose last in-band points are 31.62 and 44.67 GHz —
   32 and 50 GHz were never sampled. Interpolating the exact band edges (as the
   block's own `run_verify.py` spot points do, and as the paper's table
   already did) the **layout of record reads S11 −9.94 / S22 −9.24 dB: it fails
   both reflection specs.** (rf-layout-reviewer, 2026-08-18; `measure_post._band_max`.)
2. **The extractor's halo.** kpex drops every coupling between shapes farther
   apart than the tech's sidewall halo (IHP: 8 µm). `out_gap` sat exactly on it:
   the round-1 "winners" (out_gap 8.2–8.4) over-reported S22 by ≈0.55 dB because
   the outp↔outn sidewall term (2× weight differentially) simply vanished. Fixed
   with `pex.halo_um: 20` (a platform feature added for this — see the platform
   PR); with it the layout of record reads −9.98 / −9.36 dB.
3. **Round 1 = the generator as it was.** 120 trials, 3 islands: 64 evaluated,
   18 DRC skips (15 %), 38 generator refusals (32 %, once the guards existed),
   6 feasible *under the r1 instrument*, none under the honest one. The skips
   were three generator bugs (off-grid via centres → 155 nm contacts, TopVia1
   TopMetal1 enclosure table 0.30 vs the rule's 0.42, two knob interactions:
   Cdeg stack vs collector strap, RC column vs riser stacks) — all fixed as
   guards / table corrections in `gen_layout.py`.
4. **Round 2 = structural options as knobs.** The per-polygon C budget of the
   layout of record (kpex report DB) + the review gave five layout changes; each
   is an INT knob so the *search* decides: `bus_trim` (each output bus spans only
   its own risers + RC: −16 µm TM1 and a shorter outp‖outn run), `sub_bus`
   (taps tie to the ring on Metal1 — no Metal3 bus under the output risers),
   `cell_order` (M0|M1|L0: the MSB input bus 2 cells long instead of 3),
   `c_strip` (cascode-collector M2 tap kept away from the PyCell's Metal2
   emitter plate on the cascode-emitter node), `out_split` (outn on TopMetal2).
   Smoke-tested one at a time on the layout of record (halo 20, band edges):
   S22 −9.36 → −9.81 (bus_trim), −9.66 (sub_bus), −9.59 (out_split), −9.49
   (c_strip 2); S11 −9.98 → −10.20 (cell_order); all five together
   **S11 −10.19 / S22 −10.39 dB with the electrical point untouched** — from
   failing both specs to meeting both, by layout alone.

## Rounds table

| round | G / Θ change (why) | budget | evaluated / feasible / skipped | best scorecard (instrument) | decision |
|---|---|---|---|---|---|
| — | layout of record (`FINAL_LAYOUT`, v2 signoff 2026-08-09) | — | — | S11 −9.94 / S22 −9.24 / gain 2.27 / 8.25 / BW 58.8 / swing 2.21 / 179 mW / 7552 µm² (band edges, halo 8) | the honest baseline; **fails S11 and S22** |
| r1 | generator as-is; θ_E ∪ θ_L, 26 knobs; guards added mid-round after the first DRC skips | 3 × 40 | 64 / 6 (r1 instrument; 0 honest) / 56 | −10.04 / −10.76 (r1: dec-20 grid max, halo 8 — 0.55 dB of that is the halo cliff) | **fix G**: DRC guards + snapped vias + TopVia1 table; fix the instrument; add structural knobs |
| r2 | + `c_strip`, `bus_trim`, `out_split`, `sub_bus`, `cell_order`; bounds re_ohm ≥ 2.8, cdeg ≥ 12, rc_sep ≤ 8, out_gap ≤ 20, stack_w ≥ 1.1; band-edge metrics + halo 20; islands s0/s1 OnePlusOne + s2 TwoPointsDE from the layout of record, s3 OnePlusOne from the review point (all five structural options on) | 4 × 40 | 150 / 15 / 10 (3 build, 7 DRC) — **all 15 feasible points are island s3**; s0–s2 (120 trials from the record) found none | −10.07 / −10.79 / gain 2.23 / 8.20 / BW 61.2 / swing 2.26 / 190.2 mW / 6880 µm² (band edges, halo 20; s3 `run_38`) | **accept** `run_38` as v3 (`gen_layout.FINAL_LAYOUT`); the record's `FINAL_LAYOUT` is kept as `V2_LAYOUT` |
| r3 | balance made an **objective** (owner brief: better p/n balance first, then reflection, then power, then area): the hook measures the MSB *and* LSB path (`pn_*`, `cm_leak_dbc`, `*_lsb`), `J` rewards them (30/dB, 2/deg, 0.5/dB) plus power (0.15/mW) on top of a steeper S11 reward (5/dB); + 2 structural knobs from the r2 matching audit — `out_split` 2/3 (both buses on TM2 / mirrored) and `in_order` (p/n-swapped input rows) — + the continuous knob `rc_gap` (outn bus ↔ RC body **and** the TM2 vcc rail; the r2 extraction reads outn↔vcc 2.33 fF vs outp's 0.25 fF). 14 islands: s10–s15 from v3, s16/s17 with the new structural options on, s18/s19 with reflection-preserving hinges, s20–s23 with the **acceptance rule itself** as the hinge (S11 ≤ −10.065, S22 ≤ −10.785 = v3) | 14 × 30–40 = 520 | 488 / 141 / 32 (28 DRC, 4 generator refusals = 6.2 %) | −10.073 / −10.812 / bal 0.035 dB / 0.64° / −44.5 dBc / gain 2.27 / 8.24 / BW 61.4 / swing 2.24 / 185.0 mW / 7055 µm² (band edges, halo 20; s23 `run_30`) | **accept** `run_30` as v4 (`gen_layout.V4_LAYOUT`); v3 kept as `V3_LAYOUT`. The TCAS paper presents the round by its **best-score** point `s12 run_26` (J = 11.52, the round's max: −10.16 / −10.28 at halo 8, 167.2 mW, bal 0.02 dB / 0.24° / −52.7 dBc, 7268 µm²) — that point is `gen_layout.FINAL_LAYOUT`, the layout of record (report tier f) |

Round-2 reading: the structural options are what carry the design across the
line — the three islands that started from the layout of record with the
structural knobs at 0 never found a feasible point in 120 trials (the
optimizer has to flip several INT knobs at once to see the gain, and the
per-knob step is masked by the electrical knobs' noise), while the island
seeded from the review point (all five on) was feasible from trial 1 and spent
its budget trading margin: `out_gap` 8 → 6.37 (halo-honest now), `rc_ohm`
50 → 46.5 with `tail` 15 → 15.9 mA (BW +2 GHz, S22 −0.4 dB, +11 mW), `cdeg`
16 → 18.5, `re_ohm` 3.2 → 3.24. The accepted point is the argmin-J trial; the
review point itself (`run_1`: −10.19 / −10.40 dB, 179 mW, 7372 µm²) is the
balanced alternative if power matters more than S22 margin — both are on the
committed record.

Round-3 reading — **the structural hypothesis was wrong and the measurement
said so.** The r2 matching audit blamed the asymmetric `out_split` (outn on
TopMetal2, outp on TopMetal1) for the balance loss, so round 3 added the
symmetric variants as knobs. At the v3 electrical point, one knob at a time
(halo 20 CC, all DRC/LVS clean, `runs/r3_s1*/**/run_1_layout`):

| out_split | S11 | S22 | \|gain\| imb | phase | diff→CM | area |
|---|---|---|---|---|---|---|
| 0 both TM1 (symmetric) | −10.070 | −10.628 | 0.0483 | 0.99° | −40.8 dBc | 6880 |
| **1 outn on TM2 (v3)** | −10.070 | −10.790 | 0.0431 | 0.88° | −41.9 dBc | 6880 |
| 2 both TM2 (symmetric) | −10.069 | −10.590 | 0.0502 | 1.00° | −40.7 dBc | 6880 |
| 3 outp on TM2 (mirrored) | −10.069 | −10.812 | 0.0449 | 0.85° | −42.0 dBc | 6880 |
| 1 + `in_order` 1 (p/n rows swapped) | −10.077 | −10.790 | 0.0415 | 0.95° | −41.3 dBc | 6880 |

Both *symmetric* metal options read **worse** than the asymmetric ones, and the
input-row swap is neutral-to-worse: metal symmetry is not the balance lever,
so the accepted point keeps v3's structure (`out_split` 1, `in_order` 0). Both
are recorded as measured nulls, not as improvements. What *did* move the
balance is the per-net C asymmetry the extraction points at — `rc_gap`
(+0.5 µm at the winner) and the continuous spacing/width knobs — and the
electrical point: at the accepted point the output-net asymmetry
`ctot_outn − ctot_outp` falls 2.01 → 1.46 fF and outn↔vcc 2.33 → 1.97 fF,
which is exactly where the 0.043 → 0.035 dB / 0.88 → 0.64° / −41.9 → −44.5 dBc
came from (`results/r3/trials.jsonl` carries the per-net C of every trial).

**The ceiling of this round, and the experiment that shows it.** Every large
balance gain in the 520 trials was paid for in S22: the leaders of the
open-hinge islands (`r3_s12 run_26`: 0.027 dB / 0.46° / −47.4 dBc, 167 mW) sit
0.4–0.5 dB above v3's S22. To test whether the balance win survives without
selling reflection, islands s20–s23 were run with the **acceptance rule as the
feasibility hinge** (S11 ≤ −10.065, S22 ≤ −10.785 dB — v3's own numbers): of
520 trials only **6** hold every spec *and* both reflections at the v3 level,
and 5 of those 6 are the trial-1 structural A/Bs. The sixth is the accepted
point, found by the island seeded at the round's best-balance trial with the
acceptance hinges (`r3_s23`, `run_30`) — i.e. the improvement is real but the
two objectives are coupled through the output-net capacitance, and ~20 % of the
balance is the most the search can buy at constant reflection in this box.
For the record the alternatives are on `results/r3/trials.jsonl` too:
*balance-only* `r3_s23 run_11` (0.0312 dB / 0.57° / −45.5 dBc, 176.6 mW, but
S22 −10.715) and *reflection-only* `r3_s21 run_1` (S11 −10.076 / S22 −10.812
at v3's balance, 6880 µm²).

**Instrument note (why the round is quoted at halo 20).** The candidates were
re-measured at the block's report halo (8 µm) as well: the S22 halo-8 − halo-20
delta is **geometry-dependent and changes sign** (v3 −0.070, accepted +0.098,
`r3_s17 run_26` +0.085 dB). The per-net C explains it: at `rc_gap` ≈ 5 µm the
outn↔vcc pair sits outside the 8 µm sidewall halo and kpex simply drops
0.5–0.85 fF of real coupling, so halo 8 flatters exactly the geometries the
gap knobs open. The round is therefore accepted on the **halo-20** numbers
(the more complete extraction, and the search instrument since r2); the halo-8
column of the scorecard below is the report instrument, not the acceptance
criterion.

## Final scorecard

Accepted point = `gen_layout.FINAL_LAYOUT` (**v4**, r3_s23 `run_30`) re-signed
from `layout/`: `gen_layout.py --dut all` → **DRC + LVS PASS on lsb / msb /
pam4** → `pex_sim.py --dut all` (block default, kpex CC halo 8, pre-vs-post
report `../out/pex_report.yaml`) and `measure_post.measure` through the flow at
halo 20 CC, halo 20 RC and halo 8 CC (`codesign/remeasure.py`, records in
`../out/pex/metrics_v4_*.json`; the v3 column is `metrics_v3_*.json` +
`metrics_v3_cc_halo8_balance.json`). Biases = `FINAL_BIASES`
(tail 15.4977 mA / vcasc 3.2151 V, 4 V supply). The freeze is exact — the GDS
rebuilt from `FINAL_LAYOUT` is byte-identical to the accepted trial's
(`md5 b6a3ede8b1ab2af46b8089d1fdb18036` for `layout/out/dut_pam4.gds`,
`runs/r3_s23/.../run_30_layout/pam4drv_pam4_lay.gds` and
`results/r3/accepted.gds`).

| metric | spec | layout of record (v2) | v3 (r2 accepted), halo 20 CC | **v4 (r3 accepted), halo 20 CC** | v4, halo 20 RC | v3, halo 8 CC | **v4, halo 8 CC** |
|---|---|---|---|---|---|---|---|
| S11 @32 GHz (dB) / −10 dB edge (GHz) | ≤ −10 / ≥ 32 | −9.94 / 31.7 | −10.070 / 32.30 | **−10.073 / 32.32** | −10.073 / 32.32 | −10.047 / 32.21 | −10.034 / 32.15 |
| S22 @50 GHz (dB) / −10 dB edge (GHz) | ≤ −10 / ≥ 50 | −9.24 / 45.5 | −10.790 / 55.16 | **−10.812 / 55.30** | −10.812 / 55.30 | −10.720 / 54.73 | −10.715 / 54.64 |
| \|gain\| imbalance p/n ≤ 48 GHz (dB) | — (r3 objective) | 0.03 | 0.0431 | **0.0346** | 0.0346 | 0.0527 | 0.0470 |
| phase imbalance p/n ≤ 48 GHz (°) | — (r3 objective) | 0.5 | 0.876 | **0.643** | 0.643 | 1.179 | 0.993 |
| diff→CM conversion ≤ 48 GHz (dBc) | — (r3 objective) | −46.5 | −41.87 | **−44.48** | −44.48 | −39.37 | −40.82 |
| gain LSB / MSB (dB) | ≥ 2.2 / ≥ 8.2 | 2.27 / 8.25 | 2.232 / 8.205 | **2.269 / 8.244** | 2.269 / 8.244 | 2.232 / 8.205 | 2.269 / 8.244 |
| DAC weight (dB) | ≥ 5 | 5.98 | 5.972 | **5.975** | 5.975 | 5.972 | 5.975 |
| BW MSB / LSB (GHz) | ≥ 50 | 58.8 / 78.9 | 61.2 / 82.7 | **61.4 / 83.0** | 61.4 / 83.0 | 61.0 / 82.4 | 61.1 / 82.5 |
| swing (Vpp diff) | ≥ 2.1 | 2.21 | 2.258 | **2.237** | 2.237 | 2.258 | 2.237 |
| power @4 V (mW) | ≤ 192 | 179.1 | 190.19 | **185.05** | 185.05 | 190.19 | 185.05 |
| I_C per finger (mA) | < 3 | — | 2.655 | **2.583** | 2.583 | 2.655 | 2.583 |
| core area (µm²) | — | 7552 | 6880 | **7055** (+2.5 % vs v3, −38 % vs the paper's 11 300) | | | |
| tail / vcasc | | 15.0 mA / 3.35 V | 15.93 mA / 3.31 V | **15.4977 mA / 3.2151 V** | | | |

All eight signoff specs are met at every instrument. Against v3 the accepted
point is better on **both reflections, all three balance metrics, power, both
gains, weight and bandwidth** at the search instrument (halo 20 CC), for
+175 µm² (+2.5 %) of area and −0.021 Vpp of swing (2.237 against a 2.1 spec).
At the halo-8 report instrument the balance gain holds (0.053 → 0.047 dB,
1.18 → 0.99°, −39.4 → −40.8 dBc) and the two reflections land within 12 mdB
(S11) and 5 mdB (S22) of v3 — i.e. inside the halo-to-halo spread of the
instrument itself (25–98 mdB, measured above), and both still ~0.03 / 0.71 dB
inside spec. RC extraction at halo 20 (1382 wiring R next to 176 C)
reproduces the CC scorecard to four decimals, as it did for v3.

## Matching audit — is the accepted layout too asymmetric?

The structural options make the layout visibly asymmetric: `bus_trim` gives
each output bus its own extents, and `out_split` puts outn on TopMetal2 while
outp stays on TopMetal1. Round 3 made this a **scored objective** (the hook
measures the MSB *and* the LSB path; `pn_gain_imb_db`, `pn_phase_imb_deg`,
`cm_leak_dbc` and their `*_lsb` twins) and the search bought most of the r2
regression back. Measured on the extracted netlists (kpex CC, `driver_lib.run_ac_balance`):

| | out-net wiring C outp / outn (fF, halo 20) | \|gain\| imb ≤ 48 GHz | phase imb ≤ 48 GHz | diff→CM ≤ 48 GHz | LSB path (same three) |
|---|---|---|---|---|---|
| layout of record (v2), halo 8 | 16.4 / 17.8 (+9 %) | 0.03 dB | 0.5° | −46.5 dBc | — |
| v3 (r2 accepted), halo 8 | 11.9 / 15.0 (+27 %) | 0.0527 dB | 1.18° | −39.4 dBc | 0.0513 / 1.22° / −39.1 |
| v3, halo 20 | 15.25 / 17.26 (+13 %) | 0.0431 dB | 0.88° | −41.9 dBc | 0.0412 / 0.94° / −41.4 |
| **v4 (r3 accepted), halo 8** | | **0.0470 dB** | **0.99°** | **−40.8 dBc** | 0.0436 / 1.06° / −40.3 |
| **v4, halo 20** | 15.14 / 16.60 (+9.6 %) | **0.0346 dB** | **0.643°** | **−44.5 dBc** | 0.0306 / 0.73° / −43.6 |

The mechanism is in the per-net budget, not in the metal choice: the
outn↔vcc coupling (outn's TM2 bus runs alongside the TM2 vcc rail) is
**2.34 fF against outp's 0.26 fF** at v3, and the accepted point takes it to
1.97 fF, which with the other spacing moves brings the total output-net
asymmetry from 2.01 fF to 1.46 fF. The three symmetric metal variants
(`out_split` 0/2/3) and the p/n-swapped input rows (`in_order` 1) were tried
as knobs and measured **neutral-to-worse** (table above) — the balance came
from the C budget and the electrical point.

**What is left (round-4 material).** The residual asymmetry is now (a) the
1.46 fF the output nets still differ by — outn carries the TopVia2 pads and
TM2 stack of the `out_split` riser — and (b) the **input** side, which nothing
in this round touched and which got marginally worse: `ctot_msbp` 8.91 → 9.21 fF
against `ctot_msbn` 8.33 → 8.49 fF (0.58 → 0.72 fF of asymmetry). A generator
option that mirrors the riser/pad stack per net (rather than the bus metal) and
one that equalises the msbp/msbn bus extents are the two knobs a round 4 would
add; `in_order` (which only reorders whole rows) is already measured and is not
that knob.

## Ceiling (why the search stops where it stops)

* **S22** — with *all* output wiring C removed the extracted DUT reads −14.5 dB
  at 50 GHz: the 24.4 fF/side of cascode collector junction C (three Nx=3
  devices per side at 2.5 mA/finger against the 3 mA/finger model-card
  validity) is the floor; the layout of record carried 22.2 fF/side of wiring
  (kpex per-polygon budget: TM1 bus edge C 5.3 fF, M2/M1 risers + pads 6 fF,
  outp↔outn 2.4 fF ×2, outp↔cascode-emitter 4.2 fF at ~0.12 weight, sub-bus
  crossings 1.5 fF …). Sensitivity 0.17 dB/fF at the current point.
* **S11** — device-limited: zeroing all 10.6 fF of MSB input wiring reaches
  −11.4 dB; C_in ≈ τ_F/R_E + C_je/(1+g_mR_E) + C_bc is current-independent, so
  the electrical levers (R_E, R_B, tail) trade the 0.05 dB MSB-gain margin.
* **p/n balance vs reflection (round 3)** — the two are coupled through the
  output-net capacitance: of 520 trials only 6 hold every spec *and* both
  reflections at the v3 level (5 of them are the trial-1 structural A/Bs), and
  the four islands whose feasibility hinge *was* the acceptance rule produced
  exactly one improvement. Balance below ~0.031 dB / 0.57° / −45.5 dBc is
  reachable (`r3_s23 run_11`, `r3_s12 run_26` at 0.027 dB / −47.4 dBc) but
  costs 0.1–0.5 dB of S22 margin every time. The residual asymmetry is
  1.46 fF on the output nets and 0.72 fF on the input nets (matching audit
  above) — a per-net riser/pad mirror knob is what a round 4 would need.
* Unscored, open for tapeout (from the reviews): EM on the single TopVia1 per
  riser (7.5 mA) and the RC stacks (22.5 mA), rsil J_max of the 50 Ω loads,
  vcasc-rail odd-mode stability (bypass + per-cell series R), the 2-row
  floorplan (+0.5 dB S22, held: it splits the thermally matched MSB pair).
  RC-mode wiring R was checked at the accepted point and changes nothing
  (scorecard table above).

## Figures

* `pam4_layout_annotated.png` — every knob of `project_setup.yaml` drawn on the
  render of the accepted point (black = layout µm, red = electrical sizing that
  draws geometry, blue = structural options).

  These figures are **drawn from the GDS**, not by hand: `figures.py` reads the
  generator's GDS with `klayout.db`, flattens the cell, merges each layer into a
  `Region` and draws every polygon (with holes) as a matplotlib `PathPatch` — the
  PDF twins are therefore true vector geometry of the very GDS that passed
  DRC/LVS. Every conductor and via layer of SG13G2 is in the layer map (Activ,
  GatPoly, Cont, Metal1–5 + Via1–4, TopVia1/2, TopMetal1/2, MIM/Vmim/MemCap,
  PolyRes); marker/text/pin datatypes are skipped on purpose, and `draw_gds`
  prints a warning for any other layer that carries shapes, so a figure cannot
  silently drop a metal or a via. Connectivity itself is proved by LVS on the
  same GDS, not by the picture. KLayout has no vector export of its own; its
  native PDK-coloured render is `../out/dut_pam4.png` (`layout/render.py`).
  **The paper and the reviewer report use KLayout's own render** (headless
  `klayout.lay.LayoutView` + `sg13g2.lyp`): `../../report/figs/fig_layouts`,
  `fig_layout_b_vs_d`, and `fig_layout_annotated` (the same `annotate_knobs`
  overlay, dark palette, on the KLayout image — `report/build_report.py`); the
  matplotlib vector drawings here remain as the from-GDS cross-check.
* `before_after.png` — v3 | v4 (the round-3 pair), same scale, changed regions
  boxed and every moved knob listed; `before_after_r2.png` is the round-2 pair
  (layout of record v2 | v3).
* `rounds.png` — layout of record | r1 best | r2 accepted (v3) | r3 accepted (v4)
  strip with scorecards.

Regenerate (needs `PDK_ROOT`, the block's uv env; ~10 s per panel):

```sh
uv run python figures.py annotated --params results/r3/summary.json --out pam4_layout_annotated.png
uv run python figures.py before-after --before results/r2/summary.json --before-metrics results/r2/summary.json \
    --after results/r3/summary.json --after-metrics results/r3/summary.json \
    --labels "before: v3 (round-2 accepted)" "after: v4 (round-3 accepted)" --out before_after.png
uv run python figures.py rounds --panel "layout of record v2 (r2 instrument)=results/baseline_r2_instrument.json=results/baseline_r2_instrument.json" \
    --panel "r1 best (run_22; r1 instrument, halo 8)=results/r1/summary.json" \
    --panel "r2 accepted v3 (s3 run_38)=results/r2/summary.json" \
    --panel "r3 accepted v4 (s23 run_30)=results/r3/summary.json" --out rounds.png
```

`figures.py` reads the **accepted** trial of a harvest `summary.json` when one
is recorded (`harvest.py --accept`), not the argmax-J trial — in round 3 they
are different points on purpose (`best` = `r3_s12 run_26`, which buys balance
by selling 0.5 dB of S22; `accepted` = `r3_s23 run_30`).

`results/baseline_r2_instrument.json` = the layout of record (`gen_layout.V2_LAYOUT`,
tail 15 mA / vcasc 3.35 V) measured with the round-2 instrument = r2_s0 trial 1.
