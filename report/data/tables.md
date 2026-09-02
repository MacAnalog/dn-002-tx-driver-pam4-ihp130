| metric | spec | paper meas. | (a) schematic | (b) first-pass layout | (c) v2, block-local optimizer | (d) v3, co-designed | (e) v4, co-designed | (f) record, co-designed | (g) round 4, co-designed |
|---|---|---|---|---|---|---|---|---|---|
| gain LSB (dB) | ≥ 2.2 | 3.2 | 3.09 | 2.95 | 2.27 | 2.23 | 2.27 | 2.38 | 2.39 |
| gain MSB (dB) | ≥ 8.2 | 9.2 | 9.06 | 8.92 | 8.25 | 8.20 | 8.24 | 8.36 | 8.37 |
| DAC weight (dB) | ≥ 5.0 | 6.0 | 5.97 | 5.97 | 5.98 | 5.97 | 5.97 | 5.98 | 5.98 |
| BW MSB (GHz) | ≥ 50 | 51 | 66.6 | 51.6 | 58.8 | 61.1 | 61.1 | 61.1 | 61.5 |
| BW LSB (GHz) | ≥ 50 | >67 | 92.7 | 67.6 | 78.9 | 82.4 | 82.5 | 81.4 | 81.2 |
| S11 ≤ 32 GHz (dB) | ≤ −10 | <−10 | -10.87 | -8.90 | -9.94 | -10.05 | -10.03 | -10.16 | -10.24 |
| −10 dB edge S11 (GHz) | ≥ 32 | 32 | 36.1 | 27.4 | 31.7 | 32.2 | 32.1 | 32.7 | 33.1 |
| S22 ≤ 50 GHz (dB) | ≤ −10 | <−10 | -14.75 | -7.97 | -9.24 | -10.72 | -10.71 | -10.28 | -10.25 |
| −10 dB edge S22 (GHz) | ≥ 50 | 50 | 88.7 | 38.5 | 45.5 | 54.7 | 54.6 | 51.8 | 51.6 |
| swing diff (Vpp) | ≥ 2.1 | 2.1 | 2.37 | 2.36 | 2.21 | 2.26 | 2.24 | 2.11 | 2.21 |
| power @ 4 V (mW) | ≤ 192 | 192 | 191.0 | 191.0 | 179.1 | 190.2 | 185.0 | 167.2 | 175.0 |
| core area (µm²) | — | 11 300 | — | 7374 | 7552 | 6880 | 7055 | 7268 | 7166 |
| p/n gain imbalance ≤ 48 GHz (dB) | audit | — | 0.00 | 0.02 | 0.03 | 0.05 | 0.05 | 0.02 | 0.02 |
| p/n phase imbalance ≤ 48 GHz (°) | audit | — | 0.0 | 0.2 | 0.5 | 1.2 | 1.0 | 0.2 | 0.2 |
| diff→CM conversion ≤ 48 GHz (dBc) | audit | — | < −150 (ideal symmetry) | -52.8 | -46.5 | -39.5 | -40.9 | -52.7 | -52.5 |
| CM→diff conversion ≤ 50 GHz (dB) | audit | — | < −150 (ideal symmetry) | -30.6 | -50.6 | -62.8 | -65.8 | -72.8 | -47.6 |
| I_C per emitter finger (mA) | < 3 (model card) | — | 2.67 | 2.67 | 2.50 | 2.65 | 2.58 | 2.33 | 2.44 |
| 48 GBd eye RLM | — | — | 0.995 | 0.990 | 0.995 | 0.995 | 0.994 | 0.996 | 0.996 |
| 48 GBd min eye opening (V) | — | — | 0.25 | 0.24 | 0.23 | 0.23 | 0.23 | 0.23 | 0.23 |
| 48 GBd output swing (Vpp) | — | — | 0.87 | 0.86 | 0.80 | 0.79 | 0.79 | 0.81 | 0.81 |
| 48 GBd full-swing eye min opening (V) | — | — | — | — | — | — | — | 0.68 | 0.68 |
| 48 GBd full-swing eye min width (ps) | — | — | — | — | — | — | — | 17.11 | 16.85 |
| 48 GBd full-swing eye RLM | — | — | — | — | — | — | — | 1.00 | 0.99 |

| tier | DRC (KLayout, --no_density) | LVS (KLayout) | kpex 2.5D | extracted elements (C / R) | wiring C outp / outn to gnd (fF) |
|---|---|---|---|---|---|
| (a) schematic | — (schematic) | — | — | — | — |
| (b) first-pass layout | PASS | PASS | CC, halo 8 µm | 135 / 0 | 14.8 / 15.5 |
| (c) v2, block-local optimizer | PASS | PASS | CC, halo 8 µm | 131 / 0 | 16.4 / 17.8 |
| (d) v3, co-designed | PASS | PASS | CC, halo 8 µm | 126 / 0 | 11.8 / 15.0 |
| (e) v4, co-designed | PASS | PASS | CC, halo 8 µm | 127 / 0 | 11.4 / 14.1 |
| (f) record, co-designed | PASS | PASS | CC, halo 8 µm | 126 / 0 | 11.7 / 12.4 |
| (g) round 4, co-designed | PASS | PASS | CC, halo 8 µm | 126 / 0 | 11.5 / 12.2 |
