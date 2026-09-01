#!/usr/bin/env python3
"""Before/after layout comparison figure (PDK render, annotated callouts).

BEFORE is always the ORIGINAL layout — the notebook-02 v1 point (nx=2, R_C=70
on the original edge-fed floorplan, reconstructed via the LayoutParams
defaults). AFTER is selectable:

    --after v4   (default) the layout of record `gen_layout.FINAL_LAYOUT`
                 (since the round-3 close-out: r3_s12/run_26, the paper's point)
                 (co-design round 3)                  -> before_after.png
    --after v3   the co-design round-2 point `gen_layout.V3_LAYOUT`
                                                      -> before_after_v3.png
    --after v2   the 2026-08-09 block-local point `gen_layout.V2_LAYOUT`
                 -> before_after_v2.png

(The v2 -> v3 and v3 -> v4 comparisons with the changed regions boxed are
codesign/figures.py before-after.)

    PDK_ROOT=~/local/pdks python compare_layouts.py [--after v2|v3|v4]
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import gen_layout                                                  # noqa: E402
from render import render                                          # noqa: E402

# v1 winner: electrical knobs of the first co-optimization; every layout
# field at its (original) default -> edge-fed M3 input, M1 drops, 1.8 um
# out_gap, rc_sep 8, stack_w 2.0, gap_x 7, cell_gap 6.
V1 = dict(nx=2, rc_ohm=70.0, rb_ohm=58.0, re_ohm=1.5, re_w=9.0, cdeg_ff=20.0)

ANNOT = {
    "before": [
        ("edge-fed input:\nR_B block far left,\nfar MSB cell sees ~80 um stub",
         (0.11, 0.82), (0.16, 0.985)),
        ("4 x Metal3 buses full-width,\n0.8 um gaps -> 3.5 fF\nLSB<->MSB crosstalk",
         (0.45, 0.78), (0.52, 0.955)),
        ("outp/outn only 1.8 um apart:\n7 fF sidewall C (x2 differential)\n"
         "+ 2.0 um-wide TM1, +/-3 um overhang",
         (0.30, 0.36), (0.045, 0.20)),
        ("nx=2 HBTs\n(tail capped at 12 mA\n-> swing needs R_C=70\n-> S22 mismatch)",
         (0.475, 0.52), (0.62, 0.62)),
    ],
    "after_v3": [
        ("center-fed H-tree (v2), MSB rows\ninnermost; cell order M0|M1|L0:\n"
         "the MSB input bus spans 2 cells,\nnot 3 (S11 −0.2 dB)",
         (0.50, 0.69), (0.05, 0.94)),
        ("outn on TopMetal2, outp on TopMetal1;\nper-net bus extents (bus_trim): each\n"
         "bus covers only its own risers + R_C\n(−16 um TM1, shorter outp||outn run)",
         (0.60, 0.235), (0.035, 0.115)),
        ("substrate taps on Metal1 straight\nto the ring — no Metal3 sub bus\n"
         "under the output risers",
         (0.628, 0.30), (0.70, 0.13)),
        ("nx=3 @ 15.9 mA, R_C 46.5, R_E 3.24,\nC_deg 18.5 fF, V_casc 3.31:\n"
         "found by the platform search\n(160 trials, 4 islands, round 2)",
         (0.83, 0.55), (0.66, 0.60)),
        ("cascode-collector tab (c_strip=2)\nkept off the PyCell's M2 emitter\n"
         "plate; out_gap 6.37 (halo-honest)",
         (0.285, 0.395), (0.045, 0.50)),
    ],
    "after_v2": [
        ("center-fed H-tree:\nR_B on centreline, LSB buses\nshrink to short stubs,\n"
         "zero M0/M1 skew", (0.50, 0.885), (0.06, 0.94)),
        ("Metal4 buses, MSB rows innermost,\n3 um pair gap, Metal2 base drops",
         (0.62, 0.71), (0.66, 0.90)),
        ("out_gap 8 um, min-width (1.64) TM1,\nslim risers/stacks, +/-1.5 um "
         "overhang:\noutput C -7 fF/side -> S22 passes at R_C=50",
         (0.30, 0.31), (0.035, 0.16)),
        ("nx=3 HBTs @ 15 mA\n(swing 2.21 ok; S11 closed by\nR_E 3.2 + input fixes)",
         (0.47, 0.485), (0.63, 0.585)),
        ("row compacted:\ngap_x 7->6, cell_gap 6->5\n(shorter summing bus)",
         (0.35, 0.55), (0.045, 0.62)),
    ],
    "after_v4": [
        ("center-fed H-tree (v2), MSB rows\ninnermost; cell order M0|M1|L0:\n"
         "the MSB input bus spans 2 cells,\nnot 3 (S11 −0.2 dB)",
         (0.50, 0.69), (0.05, 0.94)),
        ("outn on TopMetal2, outp on TopMetal1;\nper-net bus extents (bus_trim): each\n"
         "bus covers only its own risers + R_C\n(−16 um TM1, shorter outp||outn run)",
         (0.60, 0.235), (0.035, 0.115)),
        ("substrate taps on Metal1 straight\nto the ring — no Metal3 sub bus\n"
         "under the output risers",
         (0.628, 0.30), (0.70, 0.13)),
        ("nx=3 @ 15.9 mA, R_C 46.5, R_E 3.24,\nC_deg 18.5 fF, V_casc 3.31:\n"
         "found by the platform search\n(160 trials, 4 islands, round 2)",
         (0.83, 0.55), (0.66, 0.60)),
        ("cascode-collector tab (c_strip=2)\nkept off the PyCell's M2 emitter\n"
         "plate; out_gap 6.37 (halo-honest)",
         (0.285, 0.395), (0.045, 0.50)),
    ],
    "after_v2": [
        ("center-fed H-tree:\nR_B on centreline, LSB buses\nshrink to short stubs,\n"
         "zero M0/M1 skew", (0.50, 0.885), (0.06, 0.94)),
        ("Metal4 buses, MSB rows innermost,\n3 um pair gap, Metal2 base drops",
         (0.62, 0.71), (0.66, 0.90)),
        ("out_gap 8 um, min-width (1.64) TM1,\nslim risers/stacks, +/-1.5 um "
         "overhang:\noutput C -7 fF/side -> S22 passes at R_C=50",
         (0.30, 0.31), (0.035, 0.16)),
        ("nx=3 HBTs @ 15 mA\n(swing 2.21 ok; S11 closed by\nR_E 3.2 + input fixes)",
         (0.47, 0.485), (0.63, 0.585)),
        ("row compacted:\ngap_x 7->6, cell_gap 6->5\n(shorter summing bus)",
         (0.35, 0.55), (0.045, 0.62)),
    ],
}

TITLES = {
    "before": ("BEFORE — notebook-02 v1 point",
               "nx=2, R_C=70 $\\Omega$, 12 mA  |  107.8 x 67.6 um\n"
               "S22 −8.3 dB ✗   swing 2.07 Vpp ✗   S11 −10.2 ✓"),
    "after_v2": ("AFTER — v2, block-local optimizer + RF review (2026-08-09)",
                 "nx=3, R_C=50 $\\Omega$, 15 mA  |  99.6 x 75.8 um\n"
                 "8 specs on the dec-20 grid: S22 −10.14  swing 2.21  S11 −10.03"
                 "  (band edges: −9.24 / −9.94 ✗)"),
    "after_v3": ("AFTER — v3, co-designed through the SpiceXplorer platform (Alg. 1, round 2)",
                 "nx=3, R_C=46.5 $\\Omega$, 15.9 mA  |  97.6 x 70.5 um (6880 um2)\n"
                 "ALL 8 SPECS at the band edges:  S11 −10.05   S22 −10.72   swing 2.26   190 mW"),
    "after_v4": ("AFTER — v4, co-designed through the SpiceXplorer platform (Alg. 1, round 3)",
                 "nx=3, R_C=47.9 $\\Omega$, 15.5 mA  |  102.0 x 69.2 um (7055 um2)\n"
                 "ALL 8 SPECS at the band edges:  S11 −10.03   S22 −10.71   swing 2.24   185 mW"
                 "   |  p/n balance 0.047 dB / 0.99 deg / −40.9 dBc"),
}
SUPTITLE = {
    "after_v2": "PAM-4 driver layout — original v1 point vs the v2 full-spec resize + RF layout fixes (IHP SG13G2, pam4 DUT)",
    "after_v3": "PAM-4 driver layout — original v1 point vs the round-2 co-design point (IHP SG13G2, pam4 DUT)",
    "after_v4": "PAM-4 driver layout — original v1 point vs the layout/schematic co-design accepted point (IHP SG13G2, pam4 DUT)",
}
AFTER_PARAMS = {"after_v2": lambda: gen_layout.V2_LAYOUT,
                "after_v3": lambda: gen_layout.V3_LAYOUT,
                "after_v4": lambda: gen_layout.FINAL_LAYOUT}
OUTNAME = {"after_v2": "before_after_v2.png", "after_v3": "before_after_v3.png",
           "after_v4": "before_after.png"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--after", choices=["v2", "v3", "v4"], default="v4")
    a = ap.parse_args()
    after = f"after_{a.after}"
    with tempfile.TemporaryDirectory() as tmp:
        pngs = {}
        for tag, params in (("before", V1),
                            (after, AFTER_PARAMS[after]())):
            gen_layout.generate("pam4", gen_layout.LayoutParams(**params),
                                os.path.join(tmp, tag))
            pngs[tag] = os.path.join(tmp, f"{tag}.png")
            render(os.path.join(tmp, tag, "dut_pam4.gds"), pngs[tag])

        fig, axes = plt.subplots(1, 2, figsize=(19, 7.4),
                                 facecolor="#101014")
        kw_box = dict(boxstyle="round,pad=0.35", fc="#ffe9a8",
                      ec="#c8a03c", alpha=0.95)
        kw_arr = dict(arrowstyle="->", color="#ffd75e", lw=1.8)
        for ax, tag in zip(axes, ("before", after)):
            img = mpimg.imread(pngs[tag])
            H, W = img.shape[0], img.shape[1]
            ax.imshow(img)
            ax.set_xticks([]); ax.set_yticks([])
            for s in ax.spines.values():
                s.set_color("#666")
            t, sub = TITLES[tag]
            ax.set_title(t + "\n" + sub, color="w", fontsize=12, pad=8)
            for text, (xa, ya), (xt, yt) in ANNOT[tag]:
                ax.annotate(text, xy=(xa * W, ya * H),
                            xytext=(xt * W, yt * H), fontsize=8.5,
                            bbox=kw_box, arrowprops=kw_arr)
        fig.suptitle(SUPTITLE[after], color="w", fontsize=14, y=0.995)
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        out = os.path.join(HERE, OUTNAME[after])
        fig.savefig(out, dpi=110, facecolor=fig.get_facecolor(),
                    bbox_inches="tight")
        # palette-quantize: flat-colour layout render, ~4x smaller in git
        from PIL import Image
        im = Image.open(out).convert("RGB")
        im.quantize(colors=256,
                    method=Image.Quantize.MEDIANCUT).save(out, optimize=True)
        print("wrote", out)


if __name__ == "__main__":
    main()
