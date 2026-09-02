# Extraction-driven review of `r3_s12/run_26` (paper Round-3 point) — round-4 material

Instrument: kpex 2.5D **CC** (no wiring R, no L), sidewall halo 20 um, MIM stripped.
Sources: `runs/r3_s12/layout/layout/run_26_layout/{summary.json, pam4drv_pam4_lay_pex_cc.sp,
pam4drv_pam4_lay.gds}`; generator `external/pam4-wt/codesign-r4/layout/gen_layout.py`.
Geometry below is measured with `klayout.db` on the run's own GDS — **layer 126/0 = TopMetal1,
134/0 = TopMetal2** (confirmed against the `ow = max(out_w, MIN_W[oL])` rule: the 1.97-um bus is
TM1, the 2.00-um bus is TM2, i.e. `out_split=1`, outn on TM2).

## 0. Headline

**(a) A validated model.** Output-net capacitance asymmetry alone reproduces two of the three
balance metrics of run_26 from the extracted netlist:

| quantity | model | measured | source |
|---|---|---|---|
| R_eff per output (S-param bench, 50 ohm ports) | `rc_ohm 51.77 \|\| 50` = **25.44 ohm** | — | `driver_lib.tb_ac_balance` (method `sp`, 4-port) |
| dC_out = ctot_outn - ctot_outp | **0.976 fF** | — | `summary.json` 16.680 - 15.704 |
| phase imbalance @48 GHz = `2*pi*f*R_eff*dC` | **0.429 deg** | **0.455 deg** | 94 % reproduced |
| diff->CM = `20log10(0.5*sqrt((2*pi*f*R*dC)^2+(dG/8.686)^2))` | **-47.85 dBc** | **-47.40 dBc** | 0.45 dB |
| \|gain\| imbalance from dC_out (2nd order in f/fp) | **0.0088 dB** | **0.0267 dB** | **not** reproduced |

Reading: **phase imbalance and diff->CM are output-net metrics** (first order in dC_out;
sensitivity **0.44 deg/fF** and about **1 dB of CM-leak per 0.11 fF** at the current point).
**Gain imbalance is not** — the output pole is 343-362 GHz so (f/fp)^2 = 0.018, whereas the MSB
input pole is ~3x lower in frequency, making gain imbalance ~10x more sensitive per fractional
dC on the *input* nets. The two objectives therefore have two different owners.

**(b) The README's round-4 knob (a) is mis-aimed — refuted by this extraction.** The proposed
"per-net riser/pad via-stack mirror" targets the TopVia2/TM1/TM2 pads of the `out_split=1`
risers. Those pads are worth **+0.22 fF** (the whole outn-outp VSUBS delta; 4 pads x 1.9x1.9 um
TM1 + 4 on TM2, measured in the GDS). The real 1.12 fF is somewhere else (section 1), and the r3
A/B table already refutes the pad hypothesis independently: `out_split=2` gives *identical*
stacks to both nets and read **worse** (0.0502 dB / 1.00 deg / -40.7 dBc).

**(c) Objective audit.** `rounds/r3_s12_project_setup.yaml` scores S11 (5/dB), S22 (2/dB),
pn_gain (30/dB), pn_phase (2/deg), cm_leak (0.5/dB), power (0.15/mW), area (0.2/1000 um2).
Two knobs sit on or near a bound: `out_gap` 3.18 against a 3.0 floor, and `rc_gap` 2.87 against
a 2.0 floor — both are the levers on the two largest removable output-C terms, and both cost
area/power, which J opposes. Nothing in J scores the *input-bus* extents at all, which is why
`ctot_msbp - ctot_msbn` grew across r3 (0.58 -> 0.63 fF at this point).

## 1. Where each asymmetry physically is (from the extraction, not the picture)

Per-net totals from `summary.json`: outp/outn 15.704/16.680, msbp/msbn 9.114/8.488,
lsbp/lsbn 5.393/6.636.

### 1a. outn heavier than outp by 0.976 fF

| counterpart | outp (fF) | outn (fF) | delta n-p | polygon |
|---|---|---|---|---|
| **vcc** | 0.180 | **1.300** | **+1.120** | **outn TM2 bus x[-24.135,40.185] runs coplanar with the TM2 vcc rail x[-40.185,40.185] over 64.32 um at a 10.635 um edge gap (20.2 aF/um). outp is on TM1 — different layer AND 5.15 um further away.** |
| VSUBS | 10.921 | 11.141 | +0.220 | the 4 TopVia2 stacks (TM1 + TM2 pads, 1.9 um each) + 3 outn M2 risers that are 5.15 um longer |
| own-side cascode collectors | 2.294 ($37/$39/$41) | 2.191 ($38/$40/$42) | -0.103 | `c_strip=2` tab geometry, mirrored |
| tail/emitter nodes $10..$15 | 0.159 | 0.040 | -0.119 | outp TM1 bus overhangs left to x -40.185, over the M0 tail bus |
| sub / vcasc / cross terms | 0.611 | 0.454 | -0.157 | |
| **total** | | | **+0.976** | |

Mechanism, exactly: `build_dut` draws the vcc rail with the **untrimmed** extents
`rect(c,"TopMetal2drawing", x_bus_l, ..., x_bus_r, ...)` even when `bus_trim=1` trims the output
buses. The rail is therefore 80.37 um long while its only loads are the two RC vcc stacks at
x = +/-2.24 um (`rc_sep/2`). 64.32 um of that rail is a pure aggressor on outn.

### 1b. lsbn heavier than lsbp by 1.244 fF, msbp heavier than msbn by 0.627 fF — one root cause

Measured M4 input-bus polygons (GDS, `in_bus_layer="Metal4"`, `in_order=0`):

| net | bus x-extent | length | R_B column x | its own drop columns x | ctot |
|---|---|---|---|---|---|
| msbp | [-43.165, +2.200] | **45.365** | **+1.200 (outside, to the right)** | -42.165, -11.505 | 9.114 |
| msbn | [-20.155, +12.505] | **32.660** | +3.600 (**inside** the drop span) | -19.155, +11.505 | 8.488 |
| lsbp | [-4.600, +20.155] | **24.755** | -3.600 (outside) | +19.155 | 5.393 |
| lsbn | [-2.200, +43.165] | **45.365** | -1.200 (outside) | +42.165 | 6.636 |

Two-parameter fit on the four VSUBS entries (differences within each channel cancel the
unknown constants) gives **64 aF/um for the 0.6-um M4 bus** and 31 aF/um for the 0.4-um M2 drop
column. Attribution:

| pair | delta | of which |
|---|---|---|
| msbp - msbn | **+0.627** | VSUBS **+0.578** (12.705 um of extra msbp bus); tmsb0 +0.152 + tmsb1 +0.076 (the msbp overhang runs over both tail buses); **-0.326** cancelling from lsbp's adjacency to msbn; misc +0.147 |
| lsbn - lsbp | **+1.244** | VSUBS **+1.440** (20.61 um of extra lsbn bus, plus its 3.86-um-longer M2 drop); -0.351 lsbp<->msbn adjacency; +0.077 lsbn<->vcmb; misc +0.078 |
| emitter nodes $10-$11 / $12-$13 / $14-$15 | +0.293 / +0.319 / +0.327 | e1 carries the Cdeg M5 arm + bottom plate, e2 the TM1 arm + top plate. At Z_e = 1/gm \|\| 2R_E = 2-3 ohm this is ~0.02-0.04 deg — **noted, no knob warranted** |

Root cause: `input_feed="center"` puts all four R_B columns within +/-3.6 um of x=0
(`x_rb0 = -(n_in-1)*rb_pitch/2`, `inputs = [lsbp, lsbn, msbp, msbn]`), while `place_cell` always
drops the **p** net on the LEFT of a cell and the **n** net on the RIGHT. With `cell_order=1`
(M0 | M1 | L0) the MSB cells are not symmetric about x=0, so the msbp drops sit at centroid
-26.8 um and the msbn drops at -3.8 um: msbn's R_B lands inside its own drop span and adds zero
bus, msbp's lands 12.7 um outside it. (With `cell_order=0` both MSB buses would be ~63 um and
symmetric — r2 traded that symmetry for length; the fix below recovers symmetry *at* the shorter
length.) The same geometry produces the LSB pair's 20.6 um difference.

## 2. One generator option per asymmetry (each defaults to the current geometry)

| # | knob (new field on `LayoutParams`) | function / lines to change | what it does | expected effect | DRC risk |
|---|---|---|---|---|---|
| **A** | `vcc_trim: int = 0` | `build_dut`, the `# vcc rail` block: at 1, draw the rail over `[-h, +h]` with `h = max(rc_sep/2 + 2.0*stack_w, 6.0)` instead of `x_bus_l..x_bus_r` | rail 80.37 -> ~12 um; outn<->vcc overlap 64.32 -> 12 um | **C(outn,vcc) 1.30 -> ~0.30 fF, C(outp,vcc) 0.18 -> ~0.05**: dC_out **0.976 -> ~0.11 fF**. Predicted phase **0.455 -> 0.05-0.15 deg**, cm_leak **-47.4 -> -52..-56 dBc**, gain imb ~unchanged (0.027), and S22 **-0.08 to -0.10 dB better** (0.17 dB/fF on the mean of the two sides). Both objectives move the same way — the only decoupled win found | (i) rail must still enclose the two vcc TM2 stack pads (x +/-2.24, y 37.51-39.41, rail y 35.96-40.96 -> fine) **and the `vcc` label at x=0** — a symmetric trim satisfies both. (ii) TM2 area 530 -> 189 um2 = 2.6 % of the block; `TM2Fil.*` density rules ARE in the deck (534 categories, 0 violations) but TM1 already passes at 2.67 %, so 2.6 % has an in-design precedent — **verify on the first build**. (iii) TM2.bR guard untouched (`vcc_w` still 5.0). (iv) Tapeout honesty: a 12-um rail is only DUT-realistic with a perpendicular feed stub to the pad — draw the stub, or the knob games the extraction |
| **B** | `rb_off: float = 0.0` (um) | `build_dut`, `if p.input_feed == "center": x_rb0 = -(n_in-1)*p.rb_pitch/2 + p.rb_off` | slides the whole R_B block along x so each net's R_B column falls inside its own drop span | msbp bus shortens 64 aF/um: at `rb_off = -9.75` the **msbp-msbn delta zeroes**; at -12.7 it overshoots to ~-0.19 fF. Removes 0.8 fF from msbp; lsbp/lsbn both lengthen 12.7 um (LSB has 5 dB of S11 margin, and their delta is unchanged). Expected: gain imbalance the main mover (input side owns it), plus **S11 ~0.03 dB** (0.115 dB/fF from the README ceiling x 0.29 fF mean) and a real improvement in the **unscored** `cm_leak_dbc_lsb` (-46.4) | **Needs a new guard in `check_knob_interactions`**: at rb_off = -10 a column lands at x = -11.2, within 0.3 um of msbp's drop stack at -11.505 (1.0 um M2->M4 pad). Require `min_over_all(|rb_x - x_drop|) >= 0.5 + rb_w/2 + 1.0`. Also watch M0<->M1 branch skew (the H-tree's original purpose) — add a group-delay spot check |
| **B'** | alternative: `rb_order: int = 0` + put the existing field `rb_pitch` in theta_L | permutation of `spec["inputs"]` -> column assignment | order `[msbp, msbn, lsbp, lsbn]` with `rb_pitch = 8.0` puts msbp's column at -12.0 (just left of its -11.505 drop) | zero msbp overhang with **no** area cost and no feed asymmetry; also shortens lsbp -7.6 um and lsbn -13.2 um (total input wiring **-2.2 fF**) | **`rb_pitch` alone goes the WRONG way** — msbp's column is at `x_rb0 + 2*pitch = +0.5*pitch`, so raising pitch moves it further right. Only valid paired with `rb_order` |
| **C** | *not* a new knob: `out_gap` A/B, **sequenced after A** | — | outp<->outn mutual is **1.552 fF, x-overlap 48.27 um at 3.18 um gap = 32 aF/um, and counts x2 differentially = 3.10 fF/side** — the largest removable output term after vcc | out_gap 3.18 -> 5.0 removes 0.56 fF of mutual = 1.13 fF/side differential = **~0.19 dB S22** | out_gap raises `y_outN` only, so it lengthens the three outn M2 risers by 1.82 um each: **+0.2-0.3 fF on outn and ~+0.1 deg** of phase imbalance. That is the likely reason the search parked it at 3.18. Net after A removes the dominant term: ~**+0.15 dB S22** for a small balance give-back. **Do not raise the lower bound before A is measured** |

## 3. Cheap reflection items the r3 ceiling does not rule out

The ceiling section rules out: series output padding, device-C floor (24.4 fF/side junction),
and declares balance-vs-reflection coupled. These three are outside that:

| item | mechanism | expected | flow mapping |
|---|---|---|---|
| **A (`vcc_trim`)** | removes 1.0 fF of pure aggressor C from outn | **S22 -0.08..-0.10 dB** *and* the balance triple — decoupled, contra the ceiling's claim | new INT knob |
| **`in_bus_lvl` into theta_S** | the field already exists (`in_bus_lvl: int = 0`, 3/4/5) and is **absent from `r3_s12_project_setup.yaml`** — never searched. M4 -> M5 on all four input buses | at 64 aF/um x 148 um of total bus, a 20-30 % table delta = **-1.9..-2.9 fF of input C, S11 ~0.03-0.05 dB**. Caveat: kpex 2.5D applies per-layer area+perimeter tables *unconditionally*, so the gain is exactly the M4->M5 table delta — bound it by measurement, not by height | **zero generator change**: one line in `dut_params` |
| **C (`out_gap`)** | differential sidewall, x2 weight | **~+0.15 dB S22** net of the riser cost | existing continuous knob, A/B after A |

Not recommended: shields under the output buses (the problem is C to *any* AC ground, and r3
already measured `in_shield`-class moves as net-negative); C-neutralisation (the `vcasc` rail is
still unbypassed — `ctot_vcasc` 12.2 fF, shared by all six cascodes, invisible to a CC
extraction and to K-factor at the external ports; per-cell bypass + small series R remains the
open tapeout item).

## 4. Bench / instrument concerns (`measure_post.py`, `driver_lib.py`)

1. **Band-edge convention is inconsistent across the scored metrics.** `s11`, `s22` and
   `cm_leak_dbc` go through `_band_max`, which interpolates the exact band edge — the fix the r1
   review forced. But `pn_gain_imb_db` and `pn_phase_imb_deg` use
   `np.abs(rb[...])[fb <= 48].max()`, which does **not**. At `AC_PTS_PER_DEC = 100` the last
   in-band point is **47.86 GHz**, so both read low: **+0.3 %** on phase (0.0013 deg) and
   **+0.6 %** on gain — negligible today, but these are *scored* objectives (30/dB, 2/deg) and
   the defect scales: at r1's 20 pts/dec the last point is 44.67 GHz and phase would read 7 %
   optimistic. Fix: `m[...] = _band_max(fb, np.abs(rb["gain_imb_db"]), BAL_BAND_GHZ)` and the
   same for phase. One line each.
2. `dph = (php - phn) % 360.0 - 180.0` — **checked, correct**, wraps properly in both directions
   under numpy's Python-modulo semantics. No bug.
3. `cmdb` adds a `+1e-15` floor that `ddb` does not; harmless at these levels, but asymmetric.
4. `run_ac` and `run_ac_balance` run the same `tb_ac` deck twice per drive (different
   post-processing only) — 2 redundant ngspice runs per trial. Cost, not correctness.
5. **CC-only caveat on the balance numbers:** the README reports halo-20 RC reproducing the CC
   balance triple to four decimals for v4, so wiring R is *not* the missing 3x in gain imbalance.
   That leaves the input-net dC as the explanation — consistent with the pole-frequency argument
   in section 0 and directly testable by knob B.

## 5. Prioritized round-4 actions

| # | action | mechanism | expected impact | flow mapping | effort |
|---|---|---|---|---|---|
| 1 | **`vcc_trim`** (new INT, default 0) | kills the 64-um coplanar TM2 outn<->vcc run — 1.12 of the 0.976 fF net asymmetry | phase **0.455 -> 0.05-0.15 deg**, cm_leak **-47.4 -> -52..-56 dBc**, **S22 -0.08..-0.10 dB**; gain imb unchanged | ~6 lines in `build_dut` + one bound in `dut_params` | S |
| 2 | **`rb_off`** (new float, default 0.0) | equalises the msbp/msbn bus extents; owner of the gain-imbalance metric | gain imb is the target (0.027, model says the input side owns it); S11 ~0.03 dB; improves the unscored LSB triple | ~2 lines + a guard in `check_knob_interactions` | S |
| 3 | **A/B 1 and 2 ONE AT A TIME before bundling** | the hand model cannot resolve the *sign* of the input-side phase contribution: output-only already explains 94 % of 0.455 deg, so either the input term is ~0.03 deg or R_eff is off. If the two currently oppose, fixing one alone lands worse than predicted | measurement, not a prediction | two extra trial-1 runs (~75 s each) | S |
| 4 | **`in_bus_lvl` into `dut_params`** (3..5, init 4) | existing generator field, never searched | -1.9..-2.9 fF input C, S11 ~0.03-0.05 dB (bounded by the kpex M4/M5 table delta) | **one YAML line, no code** | XS |
| 5 | **`_band_max` on the two `pn_*` metrics** + `out_gap` A/B after item 1 | fixes the measuring instrument before trusting the round; then reclaim the x2-weighted differential mutual | instrument consistency; **~+0.15 dB S22** | 2 lines in `measure_post.py`; existing knob | XS / S |

Sequencing: **fix the instrument (5) first, then 1, then 2, each as an isolated trial-1 A/B at
the run_26 electrical point**, then open the box. Held in reserve: the two-row floorplan
(README: +0.5 dB S22, splits the thermally matched MSB pair) and the `vcasc` bypass — neither is
a round-4 parameter move.

**Mark every magnitude above as a hypothesis to A/B against the extractor.** The r3 record is
the precedent: `out_split` 0/2/3 and `in_order=1` were all textbook-correct symmetry moves and
all measured neutral-to-worse. Expect at least one of items 1-4 to be rejected by measurement.
