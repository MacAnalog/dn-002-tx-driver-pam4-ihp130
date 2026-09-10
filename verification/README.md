# Verification — re-run every number of the final results yourself

Everything in the final pre/post-layout results (`report/data/tables.md`,
root `README.md` results table, paper Table I) is reproducible with plain
`ngspice -b` on static decks in this folder, plus a KLayout DRC/LVS run on
the shipped GDS. Two ways to do it:

* **automatic** — `make verify-report` (= `uv run python verification/verify.py`,
  ~10 min for tiers a–d incl. eyes (tier f adds the 10 000-symbol full-swing
  eye, ~30 min on its own — `--no-eye` skips all eyes); `--tier f`, `--step sim|layout|regen`,
  `--no-eye`): runs every deck, extracts every number, prints PASS/FAIL against
  `expected.json` (the values on record, frozen from `report/data/metrics.json`),
  and exits non-zero on any miss — on a number out of tolerance, on a deck ngspice
  failed to run, on a number of the record the run did not produce (`MISSING`), and
  (exit 2) on a selection that verifies nothing at all. The deck `.csv` files are
  committed, so a deck that does not re-run leaves the *previous* run's numbers on
  disk: that is why a failed deck fails the run instead of being noted in passing.
  Last run on the research server:
  **all checks pass** — every number of the record for all five tiers, plus the independent-method
  cross-checks (legacy `.ac` algebra vs the `sp` decks, see below and `last_run.json`).
* **manual** — the recipe below, one deck at a time, then `extract.py` prints
  each number next to its definition. Only numpy is needed for the extraction.

## Tiers

| tier | column | what the deck includes |
|---|---|---|
| `a` | (a) schematic | the DUT subckt inline (`dut/dut_pam4.spice` convention, nominal sizing nx=3 / 16 mA / R_C=R_B=50 Ω / R_E=2.5 Ω / C_deg=20 fF / V_casc 3.25 V) |
| `b` | (b) first-pass layout | `../../../report/layout/b/dut_pam4_post.spice` — kpex 2.5D CC post-layout netlist of the v1 floorplan (`LayoutParams()` defaults) at the nominal sizing |
| `c` | v2 layout of record | `report/layout/c/dut_pam4_post.spice` (`gen_layout.V2_LAYOUT` / `V2_BIASES`) |
| `d` | "Round 2" in the paper / v3 in the README | `report/layout/d/dut_pam4_post.spice` (`gen_layout.V3_LAYOUT` / `V3_BIASES`) |
| `f` | **"Round 3" in the paper — the layout of record** | `report/layout/f/dut_pam4_post.spice` (`gen_layout.FINAL_LAYOUT` / `FINAL_BIASES` = co-design `r3_s12/run_26`, the round-3 best-score point) |

The layout tiers reach the post-layout netlist through the same adapter subckt
the Python benches use (`layout/pex_sim.wrap_layout_dut`: schematic port order,
1 mA/V tail VCCS from the bias ports, substrate grounded, RES/CAP corner libs),
so a deck differs from the schematic one **only** in the DUT it includes. Every
deck was written by the testbench builders in `testbenches/driver_lib.py`
(`tb_ac`, `tb_ac_s22`, `tb_ac_balance`, `tb_dc`, `tb_bias`, `tb_eye`) with the
tier's sizing (`decks/<tier>/meta.json` lists it) — regenerate with
`uv run python verification/dump_decks.py` after `make report`.

## Manual recipe

```sh
export PDK_ROOT=<dir containing ihp-sg13g2> PDK=ihp-sg13g2     # IHP-Open-PDK; ngspice-45 on PATH
cd verification/decks/f                                        # tier: a | b | c | d | f
ngspice -b ac_msb.spice      # -> ac_msb.csv   (Sdd21/Sdd11 vs f, MSB drive; .op + sp dec 100 0.1..100 GHz, 4 ports)
ngspice -b ac_lsb.spice      # -> ac_lsb.csv   (idem, LSB drive)
ngspice -b s22.spice         # -> s22.csv      (Sdd22 vs f; 2 output ports)
ngspice -b balance.spice     # -> balance.csv  (|Vp|,|Vn| dB, phases, |Vp+Vn|, |Vp−Vn| dB vs f from the 4-port S-matrix; MSB drive)
ngspice -b dc.spice          # -> dc.csv       (Vout,diff vs source EMF, both ports, ±0.9 V)
ngspice -b bias.spice        # -> bias.csv     (ramp-and-hold transient: v(outp), i(Vcc))
ngspice -b eye.spice         # -> eye.csv      (48 GBd PAM-4, 200 symbols, ~25 s post-layout)
python ../../extract.py d    # every number, with its formula, from the CSVs present
```

The `.spiceinit` in each deck directory is mandatory (`ngbehavior=hsa` — without
it the HBT conducts 0 A silently; it also loads the OSDI resistor model the
layout netlists need). ngspice reads it from the run directory, so run the
decks from inside `decks/<tier>/`.

### S-parameter method, and the independent cross-check

All S-parameter numbers come from **ngspice's built-in S-parameter analysis**
(`sp dec 100 1e8 1e11`, ngspice ≥ 42): the driven input pair and the output pair
are port sources (`portnum n z0 50`, i.e. source + series 50 Ω = the VNA
reference) and the differential quantities are the mixed-mode combinations of
the single-ended matrix over each p/n pair, `Sdd = ½(S11 − S12 − S21 + S22)`
(`ac_msb.spice`: 4 ports msbp/msbn/outp/outn → Sdd21, Sdd11; `s22.spice`: 2 ports
outp/outn → Sdd22; `balance.spice`: the two output waves under differential
drive, `2·Vp = ½(S31 − S32)`, `2·Vn = ½(S41 − S42)`, → gain/phase imbalance and
diff→CM conversion).

Each tier also carries `*_alg.spice` twins that compute the same quantities
with the legacy in-deck power-wave algebra (`.ac`, unit differential EMF
through 2×50 Ω, `zin = vdiff·100/(1−vdiff)`, `S = (z−100)/(z+100)`,
`S21 = 2·Vout/Vsrc`; balance from the node voltages `v(outp)`, `v(outn)`):

```sh
ngspice -b ac_msb_alg.spice   ; ngspice -b s22_alg.spice   ; ngspice -b balance_alg.spice
python ../../extract.py d     # prints the [alg] lines next to the sp numbers
```

`verify.py` requires the two methods to agree to 0.01 dB / 0.05 GHz on gain,
BW, S11, S22 and both −10 dB edges and to 0.002 dB / 0.02° / 0.5 dBc on the
balance scalars; `cmdm_alg.spice` is the CM-drive twin (the ONE sign flip
`Vsmsbn AC -0.5 → +0.5` turns the differential stimulus common-mode) whose
`dB(2·(Vp−Vn))` must match the primary deck's mixed-mode `dB|Sdc21|` column —
the CM→diff number through two different stimuli. On record they agree to all
printed digits for every tier
(e.g. v3: S11 −10.046 / S22 −10.720 dB, edges 32.20 / 54.73 GHz, balance
0.053 dB / 1.166° / −39.45 dBc by both methods).

Layout-side numbers (no ngspice):

```sh
uv run python verification/verify.py --tier d --step layout   # DRC + LVS on report/layout/d/dut_pam4.gds, area, C/R counts
uv run python verification/verify.py --tier d --step regen    # rebuild the GDS from layout_params.json; XOR vs the shipped GDS = 0
```

## Every number, where it comes from, and the value on record

| number | deck (`decks/<tier>/`) | definition | (a) schematic | (b) first-pass | (c) v2 | (d) v3 | (f) record | tol |
|---|---|---|---|---|---|---|---|
| Gain, LSB (dB) | `ac_lsb` | S21 at 1 GHz, LSB drive | 3.09 | 2.95 | 2.27 | 2.23 | 2.38 | 0.02 |
| Gain, MSB (dB) | `ac_msb` | S21 at 1 GHz, MSB drive | 9.06 | 8.92 | 8.25 | 8.20 | 8.36 | 0.02 |
| DAC weight (dB) | `ac_lsb + ac_msb` | msb_gain − lsb_gain | 5.97 | 5.97 | 5.98 | 5.97 | 5.98 | 0.02 |
| Bandwidth, MSB (GHz) | `ac_msb` | first −3 dB crossing of S21 vs its 1 GHz value (interp.) | 66.6 | 51.6 | 58.8 | 61.1 | 61.1 | 0.3 |
| Bandwidth, LSB (GHz) | `ac_lsb` | idem, LSB drive | 92.7 | 67.6 | 78.9 | 82.4 | 81.4 | 0.3 |
| S11 at 32 GHz (dB) | `ac_msb (+ac_lsb)` | worst S11 over f ≤ 32 GHz incl. the interpolated 32 GHz point, worse of the two drives | -10.87 | -8.90 | -9.94 | -10.05 | -10.16 | 0.03 |
| −10 dB edge S11 (GHz) | `ac_msb (+ac_lsb)` | first upward −10 dB crossing (interp.), min over drives | 36.1 | 27.4 | 31.7 | 32.2 | 32.7 | 0.3 |
| S22 at 50 GHz (dB) | `s22` | worst S22 over f ≤ 50 GHz incl. the interpolated 50 GHz point | -14.75 | -7.97 | -9.24 | -10.72 | -10.28 | 0.03 |
| −10 dB edge S22 (GHz) | `s22` | first upward −10 dB crossing (interp.) | 88.7 | 38.5 | 45.5 | 54.7 | 51.8 | 0.5 |
| Swing, differential (Vpp) | `dc` | max − min of Vout,diff over the ±0.9 V .dc sweep, both ports driven | 2.37 | 2.36 | 2.21 | 2.26 | 2.11 | 0.01 |
| Power at 4 V (mW) | `bias` | mean |I(Vcc)| over the hold window (t ≥ 11 ns) × 4 V | 191.0 | 191.0 | 179.1 | 190.2 | 167.2 | 0.5 |
| p/n gain imbalance (dB) | `balance` | max |dB(Vp) − dB(Vn)|, f ≤ 48 GHz, MSB drive | 0.00 | 0.02 | 0.03 | 0.05 | 0.02 | 0.005 |
| p/n phase imbalance (°) | `balance` | max |((ph(Vp) − ph(Vn)) mod 360) − 180|, f ≤ 48 GHz | 0.0 | 0.2 | 0.5 | 1.2 | 0.2 | 0.05 |
| Diff→CM conversion (dBc) | `balance` | worst 20 log|Vp+Vn|/|Vp−Vn| over f ≤ 48 GHz incl. edge | < −150 | -52.8 | -46.5 | -39.5 | -52.7 | 0.5 |
| CM→diff conversion (dB) | `balance` (col 14) | worst dB\|Sdc21\| = ½(S31+S32−S41−S42), f ≤ 50 GHz | < −150 | -30.6 | -50.6 | -62.8 | -72.8 | 0.5 |
| 48 GBd eye, min opening (V) | `eye` | smallest of the three eye openings at the eye centre | 0.25 | 0.24 | 0.23 | 0.23 | 0.23 | 0.005 |
| 48 GBd eye RLM | `eye` | 3·min(level spacing)/Σ(level spacings) at the eye centre | 0.995 | 0.990 | 0.995 | 0.995 | 0.995 | 0.005 |
| 48 GBd eye swing (Vpp) | `eye` | max − min of the eye trace | 0.87 | 0.86 | 0.80 | 0.79 | 0.81 | 0.01 |
| Full-swing eye min opening (V) | `eye_fs` (tier f) | 900 mVpp in, 10 000 seed-7 symbols; smallest opening at the eye centre | — | — | — | — | 0.675 | 0.005 |
| Full-swing eye min width (ps) | `eye_fs` (tier f) | narrowest of the three eyes between threshold crossings at the centre | — | — | — | — | 17.11 | 0.1 |
| Full-swing eye RLM | `eye_fs` (tier f) | as eye RLM | — | — | — | — | 0.996 | 0.005 |
| Core area (µm²) | `GDS` | top-cell bbox width × height (`verify.py --step layout`) | — | 7374 | 7552 | 6880 | 7268 | 0.5 |
| DRC | `GDS` | KLayout sg13g2_maximal, --no_density (`--step layout`) | — | PASS | PASS | PASS | PASS | exact |
| LVS | `GDS` | KLayout LVS vs dut_pam4_lvs.spice (`--step layout`) | — | PASS | PASS | PASS | PASS | exact |

Instrument facts that matter when comparing to older numbers in the repo: the
S-parameter decks sweep `sp dec 100` and the band-edge values are read
**including the interpolated 32 / 50 GHz point** (an `ac dec 20` grid never
samples them — its last in-band points are 31.62 / 44.67 GHz, which is where the
repo's older "−10.03 / −10.14" for v2 came from); post-layout tiers are kpex 2.5D
**CC** with the tech default 8 µm sidewall halo (`report/README.md` "Instrument").
Eye levels/openings/RLM are read at the eye centre (the notebooks read at a fixed
phase, ≈0.97 RLM). Tolerances are in `expected.json` — set at the last printed
digit; ngspice is deterministic on one machine, so a re-run here reproduces to
all printed digits.

## Files

```
verification/
  README.md        this file
  dump_decks.py    writes decks/<tier>/*.spice + .spiceinit + meta.json from driver_lib's builders
  extract.py       CSVs -> numbers (formulas inline; numpy only)
  verify.py        automatic: ngspice on every deck + extract + compare with expected.json; DRC/LVS/area; regen XOR
  expected.json    the values on record (frozen report/data/metrics.json) + tolerances + units
  last_run.json    result of the last verify.py run
  decks/<tier>/    ac_lsb, ac_msb, s22, balance, dc, bias, eye .spice (+ ac_msb_alg, s22_alg, balance_alg legacy-algebra twins);
                   .spiceinit; meta.json  (the .csv outputs of the last run are committed too, the .log files are not)
  work/            DRC/LVS/regen scratch (git-ignored)
```
