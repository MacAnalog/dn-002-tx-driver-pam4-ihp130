#!/usr/bin/env python3
"""Write the STATIC ngspice decks behind every number of the final results
(report/data/tables.md, paper Table I) so each one can be re-run by hand:

    cd verification/decks/<tier> && ngspice -b ac_msb.spice     # etc.
    python ../../extract.py <tier>                               # -> the numbers

Tiers:  a = schematic (nominal sizing)      b = first-pass layout (v1 floorplan, nominal sizing)
        c = v2 (2026-08-09 record)          d = v3 co-designed (paper "Round 2")
        f = r3_s12/run_26, the layout of record (paper "Round 3")

Each layout tier's deck includes the converted kpex post-layout netlist that
`make report` produced (report/layout/<tier>/dut_pam4_post.spice) through the
same adapter subckt the Python benches use (layout/pex_sim.wrap_layout_dut),
with a RELATIVE include so the decks run from their own directory. The
schematic tier inlines the DUT subckt (dut/dut_pam4.spice convention).

The decks are produced by the very testbench builders of testbenches/driver_lib.py
(tb_ac, tb_ac_s22, tb_ac_balance, tb_dc, tb_bias, tb_eye) with the tier's
sizing/bias — nothing is hand-edited. Regenerate:  uv run python verification/dump_decks.py
"""
from __future__ import annotations

import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("layout", "layout/codesign", "testbenches", "report"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import driver_lib as dl                                              # noqa: E402
import pex_sim                                                       # noqa: E402
from build_report import TIERS, dp_of                                # noqa: E402  (imports gen_layout -> gdsfactory, ~10 s)

DECKS = os.path.join(HERE, "decks")
NSYM = 200          # == report/build_report.py --nsym default
BAUD = 48e9

# Portable .spiceinit (same text as netlists/.spiceinit): resolved through $PDK_ROOT/$PDK
SPICEINIT = (
    "* IHP SG13G2 HBT decks — REQUIRED: without ngbehavior=hsa the HBT\n"
    "* conducts 0 current (silently). Export PDK_ROOT and PDK first, e.g.\n"
    "*   export PDK_ROOT=$HOME/local/pdks   PDK=ihp-sg13g2\n"
    "setcs sourcepath = ( $sourcepath $PDK_ROOT/$PDK/libs.tech/ngspice/models )\n"
    "set ngbehavior=hsa\n"
    "* PDK resistors (rsil/rppd in the layout netlists) are OSDI r3_cmc devices\n"
    "osdi $PDK_ROOT/$PDK/libs.tech/ngspice/osdi/r3_cmc.osdi\n"
)


def dut_ref_for(tier: str, deck_dir: str) -> str:
    """The DUT the deck instantiates: schematic subckt text (a) or the post-layout
    adapter with a relative include (b/c/d)."""
    t = TIERS[tier]
    dp = dp_of(t)
    if t["layout"] is None:
        _, sub, _ = dl.dut_subckt("pam4", dp)
        return sub
    post = os.path.join(ROOT, "report", "layout", tier, "dut_pam4_post.spice")
    if not os.path.exists(post):
        raise FileNotFoundError(f"{post} missing — run `make report` first (it writes report/layout/<tier>/)")
    ref = pex_sim.wrap_layout_dut("pam4", post)
    rel = os.path.relpath(post, deck_dir)
    return ref.replace(f'.include "{os.path.abspath(post)}"', f'.include "{rel}"')


def write_alg_twins(d: str, ref: str, dp, meta: dict) -> None:
    """ac_msb_alg.spice / s22_alg.spice / balance_alg.spice: the same benches with
    method="algebra" — the legacy in-deck power-wave math (.ac + unit differential
    EMF through 2x50 ohm, zin = vdiff*100/(1-vdiff), S = (z-100)/(z+100),
    S21 = 2*Vout/Vsrc; balance from node voltages) instead of ngspice's `sp`
    S-parameter analysis. Independent-method cross-check of S21, S11, S22, BW,
    the band-edge reads and the balance scalars."""
    open(os.path.join(d, "ac_msb_alg.spice"), "w").write(
        dl.tb_ac("pam4", ref, drive="msb", dp=dp, pts_per_dec=100, method="algebra", out_csv="ac_msb_alg.csv"))
    open(os.path.join(d, "s22_alg.spice"), "w").write(
        dl.tb_ac_s22("pam4", ref, dp=dp, pts_per_dec=100, method="algebra", out_csv="s22_alg.csv"))
    open(os.path.join(d, "balance_alg.spice"), "w").write(
        dl.tb_ac_balance("pam4", ref, drive="msb", dp=dp, pts_per_dec=100, method="algebra", out_csv="balance_alg.csv"))
    meta["decks"]["ac_msb_alg"] = dict(out="ac_msb_alg.csv", cols="f, s21_db, f, s11_db",
                                       gives=["cross-check (legacy .ac algebra): msb_gain, bw_msb, s11_msb, s11_edge"])
    meta["decks"]["s22_alg"] = dict(out="s22_alg.csv", cols="f, s22_db", gives=["cross-check (legacy .ac algebra): s22, s22_edge_ghz"])
    meta["decks"]["balance_alg"] = dict(out="balance_alg.csv", cols="as balance.csv (no acd col)",
                                        gives=["cross-check (legacy .ac node voltages): pn_gain_imb_db, pn_phase_imb_deg, cm_leak_dbc"])
    # CM-drive twin of balance_alg: the ONE sign flip Vs<drv>n AC -0.5 -> +0.5
    # turns the differential stimulus into a common-mode one; the CM->DM
    # conversion gain is then A_cd = dB(2*(Vp - Vn)) (same 0.5 V EMF per side
    # through 50 ohm as the DM deck). Independent cross-check of the primary
    # deck's acd_db = dB|Sdc21| mixed-mode column.
    bal_alg = dl.tb_ac_balance("pam4", ref, drive="msb", dp=dp, pts_per_dec=100,
                               method="algebra", out_csv="cmdm_alg.csv")
    flip = "Vsmsbn"
    assert bal_alg.count(" AC -0.5") == 1
    cmdm = bal_alg.replace(" AC -0.5", " AC 0.5")
    cmdm = cmdm.replace("let ddb = db(v(outp)-v(outn))",
                        "let ddb = db(mag(v(outp)-v(outn))+1e-15)")
    open(os.path.join(d, "cmdm_alg.spice"), "w").write(cmdm)
    meta["decks"]["cmdm_alg"] = dict(out="cmdm_alg.csv", cols="as balance_alg.csv; A_cd = ddb + 6.02 dB",
                                     gives=["cross-check (CM drive, .ac node voltages): cm_dm_db"])


def main() -> None:
    random.seed(7)                                   # == report/build_report.py
    msb = [random.randint(0, 1) for _ in range(NSYM)]
    lsb = [random.randint(0, 1) for _ in range(NSYM)]
    for tier in "abcdf":
        t = TIERS[tier]
        dp = dp_of(t)
        d = os.path.join(DECKS, tier)
        os.makedirs(d, exist_ok=True)
        ref = dut_ref_for(tier, d)
        open(os.path.join(d, ".spiceinit"), "w").write(SPICEINIT)
        open(os.path.join(d, "spiceinit.txt"), "w").write("# copy of .spiceinit (ngspice reads the dotfile)\n" + SPICEINIT)
        meta = dict(tier=tier, label=t["label"], vcc=dp.vcc, cell=dp.cell.__dict__, baud_hz=BAUD, nsym=NSYM,
                    decks={})
        # S21/S11, both drive paths  (gain, weight, BW, S11, S11 edge) — ngspice `sp` analysis, 4 ports
        for drv in ("lsb", "msb"):
            deck = dl.tb_ac("pam4", ref, drive=drv, dp=dp, pts_per_dec=100, out_csv=f"ac_{drv}.csv")
            open(os.path.join(d, f"ac_{drv}.spice"), "w").write(deck)
            meta["decks"][f"ac_{drv}"] = dict(out=f"ac_{drv}.csv", cols="f, sdd21_db, f, sdd11_db",
                                             gives=[f"{drv}_gain", f"bw_{drv}", f"s11_{drv}", "s11", "s11_edge_ghz", "weight", "bw"])
        # S22
        deck = dl.tb_ac_s22("pam4", ref, dp=dp, pts_per_dec=100, out_csv="s22.csv")
        open(os.path.join(d, "s22.spice"), "w").write(deck)
        meta["decks"]["s22"] = dict(out="s22.csv", cols="f, sdd22_db", gives=["s22", "s22_edge_ghz"])
        # p/n balance (MSB drive)
        deck = dl.tb_ac_balance("pam4", ref, drive="msb", dp=dp, pts_per_dec=100, out_csv="balance.csv")
        open(os.path.join(d, "balance.spice"), "w").write(deck)
        meta["decks"]["balance"] = dict(out="balance.csv", cols="f, gp_db, f, gn_db, f, php_deg, f, phn_deg, f, cm_db, f, dd_db, f, acd_db",
                                        gives=["pn_gain_imb_db", "pn_phase_imb_deg", "cm_leak_dbc", "cm_dm_db"])
        # DC transfer (swing)
        deck = dl.tb_dc("pam4", ref, drive="both", vd_max_mv=900.0, step_mv=15.0, dp=dp, out_csv="dc.csv")
        open(os.path.join(d, "dc.spice"), "w").write(deck)
        meta["decks"]["dc"] = dict(out="dc.csv", cols="vd, vout_diff, vd, i_vcc", gives=["swing"])
        # bias / power
        deck, hold0, t_end = dl.tb_bias("pam4", ref, dp=dp, probes=["v(outp)", "i(Vcc)"], out_csv="bias.csv")
        open(os.path.join(d, "bias.spice"), "w").write(deck)
        meta["decks"]["bias"] = dict(out="bias.csv", cols="t, v(outp), t, i(Vcc)", hold0_ns=hold0, t_end_ns=t_end,
                                     gives=["power", "ic_ma_per_finger"])
        # 48 GBd PAM-4 eye
        deck, t0, t_end = dl.tb_eye(ref, msb_bits=msb, lsb_bits=lsb, dp=dp, baud_hz=BAUD, vswing_mv=200.0, out_csv="eye.csv")
        open(os.path.join(d, "eye.spice"), "w").write(deck)
        meta["decks"]["eye"] = dict(out="eye.csv", cols="t, vout_diff", data_start_ns=t0, t_end_ns=t_end,
                                    gives=["eye_rlm", "eye_min_v", "eye_vpp", "eye_levels_v", "eye_openings_v"])
        if tier == "f":
            # full-swing eye of the record (paper eye figure): 900 mVpp input,
            # 10 000 seed-7 symbols. ~10x the runtime of eye.spice.
            random.seed(7)
            msbf = [random.randint(0, 1) for _ in range(10000)]
            lsbf = [random.randint(0, 1) for _ in range(10000)]
            deck, t0f, t_endf = dl.tb_eye(ref, msb_bits=msbf, lsb_bits=lsbf, dp=dp,
                                          baud_hz=BAUD, vswing_mv=900.0, out_csv="eye_fs.csv")
            open(os.path.join(d, "eye_fs.spice"), "w").write(deck)
            meta["decks"]["eye_fs"] = dict(out="eye_fs.csv", cols="t, vout_diff", data_start_ns=t0f,
                                           t_end_ns=t_endf, nsym=10000, vswing_mv=900.0,
                                           gives=["eye_fs_min_v", "eye_fs_min_width_ps", "eye_fs_rlm"])
        # independent-method twins: the legacy in-deck .ac power-wave algebra
        # (the primary decks use ngspice's built-in `sp` S-parameter analysis)
        write_alg_twins(d, ref, dp, meta)
        json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
        print(f"{tier}: {len(meta['decks'])} decks -> {os.path.relpath(d, ROOT)}")


if __name__ == "__main__":
    main()
