#!/usr/bin/env python3
"""Build the reviewer report: every tier of the PAM-4 driver case study measured by
the SAME benches, on the SAME instrument, with the artefacts an expert needs.

Tiers (the paper's table columns):
  a  schematic, EIC-verified nominal sizing (no layout)
  b  first-pass layout: the ORIGINAL v1 floorplan (LayoutParams defaults: edge-fed
     Metal3 input buses, 1.8 um output-bus gap) with the nominal sizing
  c  layout of record v2 (gen_layout.V2_LAYOUT/V2_BIASES; block-local optimizer +
     RF review, 2026-08-09)
  d  co-design round-2 point v3 (gen_layout.V3_LAYOUT/V3_BIASES; Alg. 1 of the
     paper run through spicexplorer-optimize, round 2 island s3 run_38)
  e  co-design round-3 point v4 = the layout of record (gen_layout.FINAL_LAYOUT/
     FINAL_BIASES; round 3 island s23 run_30 — p/n balance made an objective)

For b/c/d/e: gdsfactory build -> KLayout DRC (--no_density) + LVS -> kpex 2.5D CC
(tech default halo 8 um) -> converted post-layout netlist -> the block's own
driver_lib benches (S21/S11 both paths, S22, DC transfer/swing, bias/power,
p/n balance, 48 GBd PAM-4 eye). Metrics = layout/codesign/measure_post.measure
(band-edge interpolated S-params, dec 100) + the eye figures of notebook 03.

Outputs (all under report/):
  layout/<tier>/   dut_pam4.gds, dut_pam4_lvs.spice, dut_pam4_kpex.spice, dut_pam4_post.spice
                   (converted extraction), signoff/{drc,lvs} logs, layout.png (KLayout render)
  data/            metrics.json / metrics.csv (every scalar, every tier), sparams_<tier>.csv,
                   eye_<tier>.npz, dc_<tier>.csv, balance_<tier>.csv, tables.md
  figs/            fig_layouts (b|c|d KLayout renders), fig_layout_b_vs_d, fig_layout_annotated
                   (d + every knob), fig_eye (a,b,c,d density eyes), fig_sparams, fig_dc,
                   fig_balance — PNG + PDF
  work/            scratch (git-ignored)

Run (uv env, PDK/kpex per local.mk):   make report          (~15 min on the research server)
Options: --skip-build (reuse work/), --tiers a,b,d,f, --nsym 200
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for sub in ("layout", "layout/codesign", "testbenches"):
    sys.path.insert(0, os.path.join(ROOT, sub))

import matplotlib                                                    # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                      # noqa: E402
import matplotlib.image as mpimg                                     # noqa: E402
from matplotlib.colors import LinearSegmentedColormap                # noqa: E402

import gen_layout                                                    # noqa: E402
import pex_sim                                                       # noqa: E402
import measure_post                                                  # noqa: E402
import driver_lib as dl                                              # noqa: E402
import figures as cfig                                               # noqa: E402  (codesign/figures.py: knob annotations)

WORK = os.path.join(HERE, "work")
FIGS = os.path.join(HERE, "figs")
DATA = os.path.join(HERE, "data")
LAY = os.path.join(HERE, "layout")
LYP = os.path.join(os.environ.get("PDK_ROOT", os.path.expanduser("~/local/pdks")),
                   "ihp-sg13g2/libs.tech/klayout/tech/sg13g2.lyp")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 9.5,
                     "axes.labelsize": 9, "legend.fontsize": 8, "pdf.fonttype": 42,
                     "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 110})

# ------------------------------------------------------------------ the tiers
NOM = dl.CellParams()                      # EIC-verified nominal (paper topology)
TIERS = {
    "a": dict(label="(a) schematic, nominal sizing", short="(a) schematic",
              layout=None, bias=dict(vcc=4.0, vcasc=NOM.vcasc, vcmb=NOM.vcm_in, tail_ma=NOM.tail_ma),
              elec=dict(nx=NOM.nx, re_ohm=NOM.re_ohm, cdeg_ff=NOM.cdeg_ff, rc_ohm=NOM.rc_ohm, rb_ohm=NOM.rb_ohm)),
    "b": dict(label="(b) first-pass layout (v1 floorplan, nominal sizing)", short="(b) first-pass layout",
              layout=dict(nx=NOM.nx, re_ohm=NOM.re_ohm, cdeg_ff=NOM.cdeg_ff, rc_ohm=NOM.rc_ohm, rb_ohm=NOM.rb_ohm),
              bias=dict(vcc=4.0, vcasc=NOM.vcasc, vcmb=NOM.vcm_in, tail_ma=NOM.tail_ma), elec=None),
    "c": dict(label="(c) layout of record v2 (block-local optimizer + RF review)", short="(c) v2, block-local optimizer",
              layout=dict(gen_layout.V2_LAYOUT), bias=dict(gen_layout.V2_BIASES), elec=None),
    "d": dict(label="(d) co-design round 2, v3 (Alg. 1 through SpiceXplorer)", short="(d) v3, co-designed",
              layout=dict(gen_layout.V3_LAYOUT), bias=dict(gen_layout.V3_BIASES), elec=None),
    "e": dict(label="(e) co-design round 3 accepted point v4 (p/n balance objective)", short="(e) v4, co-designed",
              layout=dict(gen_layout.V4_LAYOUT), bias=dict(gen_layout.V4_BIASES), elec=None),
    "f": dict(label="(f) co-design round 3 best-score point (r3_s12/run_26, the paper's design of record)", short="(f) record, co-designed",
              layout=dict(gen_layout.FINAL_LAYOUT), bias=dict(gen_layout.FINAL_BIASES), elec=None),
}
COL = {"a": "#7f7f7f", "b": "#1f77b4", "c": "#ff7f0e", "d": "#d62728", "e": "#2ca02c", "f": "#9467bd"}
SPEC = [("lsb_gain", "gain LSB (dB)", "≥ 2.2"), ("msb_gain", "gain MSB (dB)", "≥ 8.2"),
        ("weight", "DAC weight (dB)", "≥ 5.0"), ("bw_msb", "BW MSB (GHz)", "≥ 50"),
        ("bw_lsb", "BW LSB (GHz)", "≥ 50"), ("s11", "S11 ≤ 32 GHz (dB)", "≤ −10"),
        ("s11_edge_ghz", "−10 dB edge S11 (GHz)", "≥ 32"), ("s22", "S22 ≤ 50 GHz (dB)", "≤ −10"),
        ("s22_edge_ghz", "−10 dB edge S22 (GHz)", "≥ 50"), ("swing", "swing diff (Vpp)", "≥ 2.1"),
        ("power", "power @ 4 V (mW)", "≤ 192"), ("area_um2", "core area (µm²)", "—"),
        ("pn_gain_imb_db", "p/n gain imbalance ≤ 48 GHz (dB)", "audit"),
        ("pn_phase_imb_deg", "p/n phase imbalance ≤ 48 GHz (°)", "audit"),
        ("cm_leak_dbc", "diff→CM conversion ≤ 48 GHz (dBc)", "audit"),
        ("cm_dm_db", "CM→diff conversion ≤ 50 GHz (dB)", "audit"),
        ("ic_ma_per_finger", "I_C per emitter finger (mA)", "< 3 (model card)"),
        ("eye_rlm", "48 GBd eye RLM", "—"), ("eye_min_v", "48 GBd min eye opening (V)", "—"),
        ("eye_vpp", "48 GBd output swing (Vpp)", "—"),
        ("eye_fs_min_v", "48 GBd full-swing eye min opening (V)", "—"),
        ("eye_fs_min_width_ps", "48 GBd full-swing eye min width (ps)", "—"),
        ("eye_fs_rlm", "48 GBd full-swing eye RLM", "—")]
PAPER_MEAS = {"lsb_gain": "3.2", "msb_gain": "9.2", "weight": "6.0", "bw_msb": "51", "bw_lsb": ">67",
              "s11": "<−10", "s11_edge_ghz": "32", "s22": "<−10", "s22_edge_ghz": "50", "swing": "2.1",
              "power": "192", "area_um2": "11 300"}


def dp_of(t: dict) -> dl.DriverParams:
    e = t["elec"] or {k: t["layout"][k] for k in ("nx", "re_ohm", "cdeg_ff", "rc_ohm", "rb_ohm")}
    b = t["bias"]
    return dl.DriverParams(vcc=float(b["vcc"]), cell=dl.CellParams(
        nx=int(e["nx"]), tail_ma=float(b["tail_ma"]), re_ohm=float(e["re_ohm"]), cdeg_ff=float(e["cdeg_ff"]),
        rc_ohm=float(e["rc_ohm"]), rb_ohm=float(e["rb_ohm"]), vcasc=float(b["vcasc"]), vcm_in=float(b["vcmb"])))


# ------------------------------------------------------------------ layout tiers
def build_layout_tier(tier: str, skip: bool = False) -> dict:
    """gdsfactory -> DRC/LVS -> kpex CC -> measure_post scalars; copies artefacts to layout/<tier>/."""
    t = TIERS[tier]
    work = os.path.join(WORK, tier)
    os.makedirs(work, exist_ok=True)
    out = os.path.join(LAY, tier)
    os.makedirs(os.path.join(out, "signoff"), exist_ok=True)
    mpath = os.path.join(work, "metrics.json")
    if skip and os.path.exists(mpath):
        return json.load(open(mpath))
    cwd0 = os.getcwd()
    os.chdir(work)                                    # the ihp PyCell writes temp.gds in cwd
    try:
        p = gen_layout.LayoutParams(**t["layout"])
        info = gen_layout.generate("pam4", p, work)
        import signoff
        drc_ok, _ = signoff.run_drc(os.path.join(work, "dut_pam4.gds"), "pam4drv_pam4_lay", os.path.join(work, "signoff", "drc"))
        lvs_ok, _ = signoff.run_lvs(os.path.join(work, "dut_pam4.gds"), os.path.join(work, "dut_pam4_lvs.spice"),
                                    "pam4drv_pam4_lay", os.path.join(work, "signoff", "lvs"))
        pex_sim.OUT = work
        raw = pex_sim.run_kpex("pam4", "CC")
        req = {"params": dataclasses.asdict(p), "work_dir": work, "pex_netlist": raw,
               "deck_params": {"tail_ma": t["bias"]["tail_ma"], "vcasc": t["bias"]["vcasc"], "vcc": t["bias"]["vcc"]}}
        m = measure_post.measure(req)
    finally:
        os.chdir(cwd0)
    import klayout.db as kdb
    ly = kdb.Layout(); ly.read(os.path.join(work, "dut_pam4.gds")); bb = ly.top_cell().dbbox()
    m.update(dict(area_um2=info["area_um2"], drc_pass=float(drc_ok), lvs_match=float(lvs_ok),
                  width_um=float(bb.width()), height_um=float(bb.height())))
    # artefacts a reviewer wants next to the numbers
    for f in ("dut_pam4.gds", "dut_pam4_lvs.spice", "dut_pam4_kpex.spice", "dut_pam4_sim.spice", "dut_pam4_post.spice"):
        if os.path.exists(os.path.join(work, f)):
            shutil.copy(os.path.join(work, f), os.path.join(out, f))
    for sub in ("drc", "lvs"):
        d = os.path.join(work, "signoff", sub)
        if os.path.isdir(d):
            dst = os.path.join(out, "signoff", sub)
            # the run logs are timestamp-named: clear the destination so a
            # rebuild replaces the evidence generation instead of appending
            shutil.rmtree(dst, ignore_errors=True)
            os.makedirs(dst, exist_ok=True)
            for f in os.listdir(d):
                if f.endswith(".log") or f.endswith("_extracted.cir"):
                    shutil.copy(os.path.join(d, f), os.path.join(dst, f))
    json.dump(dataclasses.asdict(p), open(os.path.join(out, "layout_params.json"), "w"), indent=1)
    json.dump(t["bias"], open(os.path.join(out, "bench_biases.json"), "w"), indent=1)
    json.dump(m, open(mpath, "w"), indent=1)
    return m


def klayout_render(gds: str, png: str, w: int = 3000, h: int = 2000, white: bool = False) -> tuple:
    """KLayout's own renderer (sg13g2.lyp colours), headless; returns the µm extent
    (left, right, bottom, top) of the saved image so annotations can be placed in µm."""
    import klayout.db as kdb
    import klayout.lay as klay
    lv = klay.LayoutView()
    lv.load_layout(gds, 0)
    if os.path.exists(LYP):
        lv.load_layer_props(LYP)
    lv.max_hier_levels = 10
    lv.set_config("background-color", "#ffffff" if white else "#000000")
    lv.set_config("grid-visible", "false")
    lv.set_config("text-visible", "false")
    lv.zoom_fit()
    lv.save_image(png, w, h)
    # µm <-> pixel mapping from the drawn extent (the guard ring IS the layout bbox)
    ly = kdb.Layout(); ly.read(gds); b = ly.top_cell().dbbox()
    img = mpimg.imread(png)
    bg = 1.0 if white else 0.0
    mask = np.any(np.abs(img[:, :, :3] - bg) > 0.06, axis=2)
    ys, xs = np.where(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    sx = (b.right - b.left) / max(x1 - x0, 1)
    sy = (b.top - b.bottom) / max(y1 - y0, 1)
    s = (sx + sy) / 2
    left = b.left - x0 * s
    right = left + img.shape[1] * s
    top = b.top + y0 * s
    bottom = top - img.shape[0] * s
    return (left, right, bottom, top)


# ------------------------------------------------------------------ benches
def run_sparams(tier: str, ref: str | None, dp: dl.DriverParams) -> dict:
    out = {}
    for drv in ("lsb", "msb"):
        r = dl.run_ac("pam4", drive=drv, dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900)
        assert r["ok"], r.get("log", "")[-1500:]
        out[drv] = dict(f=r["f_ghz"], s21=r["s21_db"], s11=r["s11_db"])
    r22 = dl.run_ac_s22("pam4", dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900)
    assert r22["ok"], r22.get("log", "")[-1500:]
    out["s22"] = dict(f=r22["f_ghz"], s22=r22["s22_db"])
    rb = dl.run_ac_balance("pam4", drive="msb", dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900)
    assert rb["ok"], rb.get("log", "")[-1500:]
    out["bal"] = dict(f=rb["f_ghz"], g=rb["gain_imb_db"], ph=rb["phase_imb_deg"], cm=rb["cm_leak_dbc"],
                      acd=rb.get("cm_dm_db"))
    d = dl.run_dc("pam4", drive="both", vd_max_mv=900.0, step_mv=15.0, dp=dp, dut_ref=ref, timeout_s=900)
    assert d["ok"], d.get("log", "")[-1500:]
    out["dc"] = dict(vd=d["vd_v"], vo=d["vout_diff_v"])
    return out


def _eye_job(args):
    tier, ref, dp_dict, bits, nsym = args
    dp = dl.DriverParams(vcc=dp_dict["vcc"], cell=dl.CellParams(**dp_dict["cell"]))
    t, v, t0, baud, log = dl.run_eye(msb_bits=bits[0], lsb_bits=bits[1], dp=dp, dut_ref=ref,
                                     baud_hz=48e9, vswing_mv=200.0, timeout_s=7200)
    assert t is not None, log[-2000:]
    return tier, t, v, t0, baud


def _levels_at(phase, vv, T, centre, halfwin=0.08):
    win = (np.abs(((phase - centre) + T) % (2 * T) - T) < halfwin * T)
    samp = np.sort(vv[win])
    if samp.size < 8:
        return None
    cut = np.sort(np.argsort(np.diff(samp))[-3:])
    groups = np.split(samp, cut + 1)
    levels = [float(np.mean(g)) for g in groups]
    eyes = [float(groups[i + 1].min() - groups[i].max()) for i in range(3)]
    return levels, eyes


def eye_metrics(t, v, t0_ns, baud):
    """Fold into 2 UI, locate the eye centre (phase of maximum minimum-opening,
    scanned over one UI), cluster the samples in a ±8 % UI window at that
    centre into 4 levels -> levels, eye openings, RLM (notebook 03 definitions).
    Returns (phase, vv, metrics); metrics['centre_s'] is the phase of the eye
    centre so the display can put the crossings at the UI boundaries."""
    T = 1.0 / baud
    t_an0 = t0_ns * 1e-9 + 6 * T
    m = t >= t_an0
    tt, vv = t[m], v[m]
    phase = (tt - t_an0) % (2 * T)
    # eye centre = circular mean (period T) of the phases where the minimum
    # opening is within 50 % of its maximum, i.e. the middle of the open span
    # between the two crossings; the metrics are then read at that centre
    cs = np.linspace(0, T, 120, endpoint=False)
    ops = np.array([min(r[1]) if (r := _levels_at(phase, vv, T, c)) is not None else -np.inf for c in cs])
    good = ops > 0.5 * ops.max()
    ang = 2 * np.pi * cs[good] / T
    best_c = float((np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * np.pi)) / (2 * np.pi) * T)
    levels, eyes = _levels_at(phase, vv, T, best_c)
    amps = np.diff(levels)
    return phase, vv, dict(levels=levels, eyes=eyes, vpp=float(vv.max() - vv.min()),
                           rlm=float(3 * amps.min() / amps.sum()), centre_s=best_c)


# ------------------------------------------------------------------ figures
def fig_eyes(EYE: dict, out: str) -> dict:
    tiers = [k for k in "abcdef" if k in EYE]
    n = len(tiers)
    fig, axs = plt.subplots(1, n, figsize=(3.6 * n, 3.4), sharey=True, squeeze=False)
    cmap = LinearSegmentedColormap.from_list("eye", ["#ffffff", "#c6dbef", "#4292c6", "#08306b", "#000000"])
    met = {}
    for ax, k in zip(axs[0], tiers):
        t, v, t0, baud = EYE[k]
        _, _, m = eye_metrics(t, v, t0, baud)
        met[k] = m
        T = 1.0 / baud
        # persistence display: resample the (variable-step) ngspice trace onto a
        # 20 fs grid so every trace is a continuous line, then fold into 2 UI
        t_an0 = t0 * 1e-9 + 6 * T
        tg = np.arange(t_an0, t.max(), 20e-15)
        vg = np.interp(tg, t, v)
        # shift so the eye centre sits at 0.5 UI (crossings at the UI boundaries)
        phase = (tg - t_an0 - m["centre_s"] + T / 2) % (2 * T)
        H, xe, ye = np.histogram2d(phase * 1e12, vg, bins=[400, 300],
                                   range=[[0, 2 * T * 1e12], [vg.min() - 0.02, vg.max() + 0.02]])
        H = np.log1p(H.T)
        ax.pcolormesh(xe, ye, H, cmap=cmap, vmin=0, vmax=H.max() * 0.85, rasterized=True, shading="flat")
        ax.set_facecolor("white")
        for lv in m["levels"]:
            ax.axhline(lv, color="#999", lw=0.5, ls=":")
        for i, e in enumerate(m["eyes"]):
            yc = (m["levels"][i] + m["levels"][i + 1]) / 2
            xc = 0.5 * T * 1e12
            ax.annotate("", xy=(xc, yc + e / 2), xytext=(xc, yc - e / 2),
                        arrowprops=dict(arrowstyle="<->", color="#d62728", lw=0.9))
            ax.text(xc + 0.6, yc, f"{e * 1e3:.0f} mV", color="#d62728", fontsize=7, va="center")
        ax.set_title(f"{TIERS[k]['short']}\nRLM {m['rlm']:.3f}   swing {m['vpp']:.2f} V$_{{pp}}$", fontsize=8.5)
        ax.set_xlabel("time (ps) — 2 UI, eye centred at 0.5 UI")
        ax.set_xlim(0, 2 * T * 1e12)
        for xb in (0, T * 1e12, 2 * T * 1e12):
            ax.axvline(xb, color="#bbb", lw=0.5, ls=":")
        ax.grid(False)
    axs[0][0].set_ylabel("differential output (V)")
    fig.tight_layout()
    fig.savefig(out + "_paper.pdf", bbox_inches="tight")          # no suptitle: the caption says it
    fig.suptitle("48 GBd PAM-4 eye — 200 mV$_{pp}$ input, 4 ps edges, seed-7 MSB/LSB streams; "
                 "post-layout tiers on the kpex 2.5D CC extraction", fontsize=8.5, y=1.02)
    fig.savefig(out + ".png", dpi=220, bbox_inches="tight")
    fig.savefig(out + ".pdf", bbox_inches="tight")
    plt.close(fig)
    return met


def fig_sparams(SP: dict, out: str) -> None:
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.3))
    for k in "abcdef":
        if k not in SP:
            continue
        s = SP[k]
        axs[0].semilogx(s["msb"]["f"], s["msb"]["s21"], color=COL[k], lw=1.3, label=TIERS[k]["short"])
        axs[0].semilogx(s["lsb"]["f"], s["lsb"]["s21"], color=COL[k], lw=1.0, ls="--")
        axs[1].plot(s["msb"]["f"], s["msb"]["s11"], color=COL[k], lw=1.3, label=TIERS[k]["short"])
        axs[2].plot(s["s22"]["f"], s["s22"]["s22"], color=COL[k], lw=1.3, label=TIERS[k]["short"])
    axs[0].set_title("S21 (solid MSB, dashed LSB)"); axs[0].set_ylabel("dB"); axs[0].set_ylim(-4, 12)
    axs[1].set_title("S11, MSB drive"); axs[1].set_ylim(-25, -4)
    axs[2].set_title("S22, differential"); axs[2].set_ylim(-25, -4)
    for ax, fe in ((axs[1], 32), (axs[2], 50)):
        ax.axhline(-10, color="k", lw=0.8)
        ax.axvline(fe, color="k", lw=0.6, ls=":")
        ax.text(fe, -4.4, f"{fe} GHz", ha="center", va="top", fontsize=7)
    for ax in axs:
        ax.set_xlabel("frequency (GHz)")
    axs[0].set_xlim(0.1, 100); axs[1].set_xlim(0, 70); axs[2].set_xlim(0, 70)
    axs[0].legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(out + ".png", dpi=220); fig.savefig(out + ".pdf")
    plt.close(fig)


def fig_dc_balance(SP: dict, out_dc: str, out_bal: str) -> None:
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    for k in "abcdef":
        if k in SP:
            ax.plot(SP[k]["dc"]["vd"], SP[k]["dc"]["vo"], color=COL[k], lw=1.3, label=TIERS[k]["short"])
    ax.axhline(1.05, color="k", lw=0.5, ls=":"); ax.axhline(-1.05, color="k", lw=0.5, ls=":")
    ax.set_xlabel("differential source EMF, both ports (V)"); ax.set_ylabel("V$_{out}$ differential (V)")
    ax.set_title("DC transfer (swing spec ≥ 2.1 V$_{pp}$ = ±1.05 V)"); ax.legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out_dc + ".png", dpi=220); fig.savefig(out_dc + ".pdf"); plt.close(fig)
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.0))
    for k in "abcdef":
        if k not in SP:
            continue
        b = SP[k]["bal"]
        axs[0].semilogx(b["f"], b["g"], color=COL[k], label=TIERS[k]["short"])
        axs[1].semilogx(b["f"], b["ph"], color=COL[k])
        axs[2].semilogx(b["f"], b["cm"], color=COL[k])
    axs[0].set_title("|V$_p$| − |V$_n$| (dB), MSB drive"); axs[1].set_title("phase(V$_p$/V$_n$) − 180° (°)")
    axs[2].set_title("diff→CM conversion 20log|V$_p$+V$_n$|/|V$_p$−V$_n$| (dBc)")
    axs[2].set_ylim(-120, -20)
    axs[2].text(0.12, -115, "(a) schematic: ideal symmetry, < −150 dBc (below axis)", fontsize=6.5, color=COL["a"])
    for ax in axs:
        ax.set_xlabel("frequency (GHz)"); ax.set_xlim(0.1, 100); ax.axvline(48, color="k", lw=0.6, ls=":")
    axs[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(out_bal + ".png", dpi=220); fig.savefig(out_bal + ".pdf"); plt.close(fig)


def fig_layouts(tiers: list[str], M: dict, out: str, annotate_d: bool = False) -> None:
    n = len(tiers)
    fig, axs = plt.subplots(1, n, figsize=(6.2 * n, 4.6), squeeze=False)
    exts = {}
    for ax, k in zip(axs[0], tiers):
        png = os.path.join(LAY, k, "layout.png")
        ext = klayout_render(os.path.join(LAY, k, "dut_pam4.gds"), png)
        exts[k] = ext
        img = mpimg.imread(png)
        ax.imshow(img, extent=ext, interpolation="lanczos")
        ax.set_facecolor("black")
        ax.set_xlabel("x (µm)"); ax.set_ylabel("y (µm)"); ax.grid(False)
        m = M[k]
        ax.set_title(f"{TIERS[k]['label']}\n{m['width_um']:.1f} × {m['height_um']:.1f} µm = {m['area_um2']:.0f} µm²   "
                     f"S11 {m['s11']:.2f} / S22 {m['s22']:.2f} dB   {m['power']:.0f} mW", fontsize=8.5)
    # common frame
    L = min(e[0] for e in exts.values()); R = max(e[1] for e in exts.values())
    B = min(e[2] for e in exts.values()); T = max(e[3] for e in exts.values())
    for ax in axs[0]:
        ax.set_xlim(L, R); ax.set_ylim(B, T)
    fig.tight_layout()
    fig.savefig(out + ".png", dpi=200); fig.savefig(out + ".pdf")
    plt.close(fig)


def fig_layout_annotated(out: str, tier: str = "f") -> None:
    """The accepted layout on KLayout's own render, every optimizer knob drawn
    from the generator's geometry record."""
    p = gen_layout.LayoutParams(**TIERS[tier]["layout"])
    work = os.path.join(WORK, f"{tier}_annot")
    os.makedirs(work, exist_ok=True)
    cwd0 = os.getcwd(); os.chdir(work)
    try:
        gds, geo, _ = cfig.build_to(p, work)
    finally:
        os.chdir(cwd0)
    png = os.path.join(work, "render.png")
    ext = klayout_render(gds, png, w=3600, h=2400)
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.imshow(mpimg.imread(png), extent=ext, interpolation="lanczos")
    ax.set_facecolor("black")
    ax.grid(False)
    cfig.use_dark_palette(True)
    try:
        cfig.annotate_knobs(ax, p, geo)
    finally:
        cfig.use_dark_palette(False)
    ax.set_xlim(ext[0], ext[1]); ax.set_ylim(ext[2], ext[3])
    ax.set_xlabel("x (µm)"); ax.set_ylabel("y (µm)")
    fig.tight_layout()
    fig.savefig(out + "_paper.pdf", bbox_inches="tight")          # no title: the caption says it
    ax.set_title("PAM-4 driver DAC, accepted co-design point (v3) — every optimizer knob of project_setup.yaml on KLayout's own render\n"
                 "white: layout knobs (µm) · red: electrical sizing that draws geometry · blue: structural options",
                 fontsize=9.5, pad=22)
    fig.tight_layout()
    fig.savefig(out + ".png", dpi=200); fig.savefig(out + ".pdf")
    plt.close(fig)


# ------------------------------------------------------------------ tables
def fmt(v, key):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    if key in ("area_um2",):
        return f"{v:.0f}"
    if key in ("power", "bw_msb", "bw_lsb", "s11_edge_ghz", "s22_edge_ghz"):
        return f"{v:.1f}"
    if key in ("cm_leak_dbc", "cm_dm_db") and v < -150:
        return "< −150 (ideal symmetry)"
    if key in ("eye_rlm", "pn_phase_imb_deg", "cm_leak_dbc", "cm_dm_db"):
        return f"{v:.3f}" if key == "eye_rlm" else f"{v:.1f}"
    return f"{v:.2f}"


def write_tables(M: dict, out_md: str) -> None:
    tiers = [k for k in "abcdef" if k in M]
    lines = ["| metric | spec | paper meas. | " + " | ".join(TIERS[k]["short"] for k in tiers) + " |",
             "|---|---|---|" + "---|" * len(tiers)]
    for key, name, spec in SPEC:
        lines.append(f"| {name} | {spec} | {PAPER_MEAS.get(key, '—')} | " +
                     " | ".join(fmt(M[k].get(key), key) for k in tiers) + " |")
    lines += ["", "| tier | DRC (KLayout, --no_density) | LVS (KLayout) | kpex 2.5D | extracted elements (C / R) | wiring C outp / outn to gnd (fF) |",
              "|---|---|---|---|---|---|"]
    for k in tiers:
        m = M[k]
        if TIERS[k]["layout"] is None:
            lines.append(f"| {TIERS[k]['short']} | — (schematic) | — | — | — | — |")
        else:
            lines.append(f"| {TIERS[k]['short']} | {'PASS' if m.get('drc_pass') else 'FAIL'} | {'PASS' if m.get('lvs_match') else 'FAIL'} | "
                         f"CC, halo 8 µm | {int(m.get('pex_n_c', 0))} / {int(m.get('pex_n_r', 0))} | "
                         f"{m.get('c_outp_gnd_ff', float('nan')):.1f} / {m.get('c_outn_gnd_ff', float('nan')):.1f} |")
    open(out_md, "w").write("\n".join(lines) + "\n")


def wiring_c(post: str) -> dict:
    import re
    SI = {"a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3}
    GND = ("sub", "gnd", "0", "vcc", "vcasc", "vcmb")
    tot = {"outp": 0.0, "outn": 0.0}
    nC = nR = 0
    for line in open(post):
        if line[:1] == "R":
            nR += 1
        if line[:1] != "C":
            continue
        nC += 1
        t = line.split()
        a, b = t[1].lower(), t[2].lower()
        mm = re.match(r"([-\d.eE+]+)([afpnum]?)", t[3])
        v = float(mm.group(1)) * SI.get(mm.group(2), 1)
        for n, o in ((a, b), (b, a)):
            if n in tot and o in GND:
                tot[n] += v
    return dict(c_outp_gnd_ff=tot["outp"] * 1e15, c_outn_gnd_ff=tot["outn"] * 1e15, pex_n_c=nC, pex_n_r=nR)


# ------------------------------------------------------------------ main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiers", default="a,b,c,d,e,f")
    ap.add_argument("--skip-build", action="store_true", help="reuse work/<tier>/metrics.json + netlists")
    ap.add_argument("--nsym", type=int, default=200)
    ap.add_argument("--fullswing-nsym", type=int, default=10000)
    ap.add_argument("--no-eye", action="store_true")
    ap.add_argument("--reuse-eye", action="store_true", help="re-plot eyes from data/eye_<tier>.npz")
    a = ap.parse_args()
    tiers = a.tiers.split(",")
    for d in (WORK, FIGS, DATA, LAY):
        os.makedirs(d, exist_ok=True)
    t0 = time.time()
    M: dict = {}
    REF: dict = {}
    for k in tiers:
        if TIERS[k]["layout"] is None:
            M[k] = {}
            REF[k] = None
        else:
            print(f"== tier {k}: build / DRC / LVS / kpex / measure", flush=True)
            M[k] = build_layout_tier(k, skip=a.skip_build)
            post = os.path.join(WORK, k, "dut_pam4_post.spice")
            REF[k] = pex_sim.wrap_layout_dut("pam4", post)
            M[k].update(wiring_c(post))
            print(f"   {k}: S11 {M[k]['s11']:.2f} S22 {M[k]['s22']:.2f} gain {M[k]['msb_gain']:.2f} "
                  f"area {M[k]['area_um2']:.0f} DRC {M[k]['drc_pass']} LVS {M[k]['lvs_match']}  ({time.time() - t0:.0f} s)", flush=True)
    # schematic-tier scalars through the same hook math (no layout): use the benches directly
    if "a" in tiers:
        dp = dp_of(TIERS["a"])
        m = {}
        for drv in ("lsb", "msb"):
            r = dl.run_ac("pam4", drive=drv, dp=dp, dut_ref=None, pts_per_dec=100, timeout_s=900)
            f, s21, s11 = r["f_ghz"], r["s21_db"], r["s11_db"]
            lf = float(s21[np.argmin(np.abs(f - 1.0))])
            m[f"{drv}_gain"] = lf; m[f"bw_{drv}"] = measure_post._f3db(f, s21, lf)
            m[f"s11_{drv}"] = measure_post._band_max(f, s11, 32.0); m[f"s11_edge_{drv}"] = measure_post._edge(f, s11)
        m["weight"] = m["msb_gain"] - m["lsb_gain"]; m["bw"] = min(m["bw_lsb"], m["bw_msb"])
        m["s11"] = max(m["s11_lsb"], m["s11_msb"]); m["s11_edge_ghz"] = min(m["s11_edge_lsb"], m["s11_edge_msb"])
        r22 = dl.run_ac_s22("pam4", dp=dp, dut_ref=None, pts_per_dec=100, timeout_s=900)
        m["s22"] = measure_post._band_max(r22["f_ghz"], r22["s22_db"], 50.0); m["s22_edge_ghz"] = measure_post._edge(r22["f_ghz"], r22["s22_db"])
        rb = dl.run_ac_balance("pam4", drive="msb", dp=dp, dut_ref=None, pts_per_dec=100, timeout_s=900)
        inb = rb["f_ghz"] <= 48.0
        m["pn_gain_imb_db"] = float(np.abs(rb["gain_imb_db"][inb]).max()); m["pn_phase_imb_deg"] = float(np.abs(rb["phase_imb_deg"][inb]).max())
        m["cm_leak_dbc"] = measure_post._band_max(rb["f_ghz"], rb["cm_leak_dbc"], 48.0)
        if rb.get("cm_dm_db") is not None:
            m["cm_dm_db"] = measure_post._band_max(rb["f_ghz"], rb["cm_dm_db"], 50.0)
        d = dl.run_dc("pam4", drive="both", vd_max_mv=900.0, step_mv=15.0, dp=dp, dut_ref=None, timeout_s=900)
        m["swing"] = float(d["vout_diff_v"].max() - d["vout_diff_v"].min())
        deck_txt, hold0, _ = dl.tb_bias("pam4", dl._resolve_dut_ref("pam4", dp, None), dp=dp, probes=["v(outp)", "i(Vcc)"])
        out, log = dl.run_deck(deck_txt, ["bias.csv"], timeout_s=600)
        data = out["bias.csv"]; icc = float(np.mean(np.abs(data[data[:, 0] >= hold0 * 1e-9, 3])))
        m["power"] = icc * dp.vcc * 1e3; m["ic_ma_per_finger"] = dp.cell.tail_ma / 2.0 / dp.cell.nx
        M["a"] = m
        print(f"   a: S11 {m['s11']:.2f} S22 {m['s22']:.2f} gain {m['msb_gain']:.2f}  ({time.time() - t0:.0f} s)", flush=True)
    # sweeps for the figures
    SP = {}
    for k in tiers:
        print(f"== tier {k}: S-parameter / balance / DC sweeps", flush=True)
        SP[k] = run_sparams(k, REF[k], dp_of(TIERS[k]))
        s = SP[k]
        np.savetxt(os.path.join(DATA, f"sparams_{k}.csv"),
                   np.column_stack([s["msb"]["f"], s["msb"]["s21"], s["lsb"]["s21"], s["msb"]["s11"], s["lsb"]["s11"],
                                    np.interp(s["msb"]["f"], s["s22"]["f"], s["s22"]["s22"])]),
                   delimiter=",", header="f_ghz,s21_msb_db,s21_lsb_db,s11_msb_db,s11_lsb_db,s22_db", comments="")
        bal_cols = [s["bal"]["f"], s["bal"]["g"], s["bal"]["ph"], s["bal"]["cm"]]
        bal_hdr = "f_ghz,gain_imb_db,phase_imb_deg,cm_leak_dbc"
        if s["bal"]["acd"] is not None:
            bal_cols.append(s["bal"]["acd"]); bal_hdr += ",cm_dm_db"
            if k in M:
                M[k]["cm_dm_db"] = measure_post._band_max(s["bal"]["f"], s["bal"]["acd"], 50.0)
        np.savetxt(os.path.join(DATA, f"balance_{k}.csv"), np.column_stack(bal_cols),
                   delimiter=",", header=bal_hdr, comments="")
        np.savetxt(os.path.join(DATA, f"dc_{k}.csv"), np.column_stack([s["dc"]["vd"], s["dc"]["vo"]]),
                   delimiter=",", header="vd_source_v,vout_diff_v", comments="")
    fig_sparams(SP, os.path.join(FIGS, "fig_sparams"))
    fig_dc_balance(SP, os.path.join(FIGS, "fig_dc"), os.path.join(FIGS, "fig_balance"))
    # eyes (parallel — one ngspice per tier)
    if not a.no_eye and a.reuse_eye:
        EYE = {}
        for k in tiers:
            z = np.load(os.path.join(DATA, f"eye_{k}.npz"))
            EYE[k] = (z["t"], z["v"], float(z["t0_ns"]), float(z["baud"]))
        met = fig_eyes(EYE, os.path.join(FIGS, "fig_eye"))
        for k, m in met.items():
            M[k].update(eye_rlm=m["rlm"], eye_min_v=min(m["eyes"]), eye_vpp=m["vpp"], eye_levels_v=m["levels"], eye_openings_v=m["eyes"])
    elif not a.no_eye:
        random.seed(7)
        msb = [random.randint(0, 1) for _ in range(a.nsym)]
        lsb = [random.randint(0, 1) for _ in range(a.nsym)]
        jobs = []
        for k in tiers:
            dp = dp_of(TIERS[k])
            jobs.append((k, REF[k], dict(vcc=dp.vcc, cell=dataclasses.asdict(dp.cell)), (msb, lsb), a.nsym))
        print(f"== eyes: {len(jobs)} × {a.nsym} symbols at 48 GBd (parallel)", flush=True)
        EYE = {}
        with ProcessPoolExecutor(max_workers=len(jobs)) as ex:
            for k, t, v, t0e, baud in ex.map(_eye_job, jobs):
                EYE[k] = (t, v, t0e, baud)
                np.savez_compressed(os.path.join(DATA, f"eye_{k}.npz"), t=t, v=v, t0_ns=t0e, baud=baud)
        met = fig_eyes(EYE, os.path.join(FIGS, "fig_eye"))
        for k, m in met.items():
            M[k].update(eye_rlm=m["rlm"], eye_min_v=min(m["eyes"]), eye_vpp=m["vpp"], eye_levels_v=m["levels"], eye_openings_v=m["eyes"])
        print(f"   eyes done ({time.time() - t0:.0f} s)", flush=True)
    # full-swing eye for the record tier (paper Fig.: 900 mVpp in, 10k symbols)
    fs_tier = "f" if "f" in tiers else None
    if fs_tier and not a.no_eye:
        fs_npz = os.path.join(DATA, f"eye_{fs_tier}_fullswing.npz")
        if a.reuse_eye and os.path.exists(fs_npz):
            z = np.load(fs_npz)
            t, v, t0e, baud = z["t"], z["v"], float(z["t0_ns"]), float(z["baud"])
        else:
            random.seed(7)
            msbf = [random.randint(0, 1) for _ in range(a.fullswing_nsym)]
            lsbf = [random.randint(0, 1) for _ in range(a.fullswing_nsym)]
            print(f"== full-swing eye: tier {fs_tier}, {a.fullswing_nsym} symbols at 900 mVpp", flush=True)
            dp = dp_of(TIERS[fs_tier])
            t, v, t0e, baud, log = dl.run_eye(msb_bits=msbf, lsb_bits=lsbf, dp=dp, dut_ref=REF[fs_tier],
                                              baud_hz=48e9, vswing_mv=900.0, timeout_s=4 * 3600)
            assert t is not None, log[-2000:]
            np.savez_compressed(fs_npz, t=t, v=v, t0_ns=t0e, baud=baud)
        _, _, em = eye_metrics(t, v, t0e, baud)
        # eye WIDTH (paper definition): per eye, the horizontal span between the
        # last threshold crossing left of the eye centre and the first right of
        # it, thresholds midway between adjacent levels, folded to one UI
        T = 1.0 / baud
        t_an0 = t0e * 1e-9
        win = t >= t_an0 + 2 * T
        tg, vg = t[win], v[win]
        dtp = float(np.median(np.diff(tg)))
        ph = (tg - t_an0 - em["centre_s"] + T / 2) % T
        widths = []
        for i in range(3):
            thr = (em["levels"][i] + em["levels"][i + 1]) / 2
            sg = np.sign(vg - thr)
            idx = np.nonzero(sg[:-1] * sg[1:] < 0)[0]
            frac = (thr - vg[idx]) / (vg[idx + 1] - vg[idx])
            pc = (ph[idx] + frac * dtp) % T
            widths.append(float(pc[pc > T / 2].min() - pc[pc < T / 2].max()))
        M[fs_tier].update(eye_fs_rlm=em["rlm"], eye_fs_min_v=min(em["eyes"]),
                          eye_fs_vpp=em["vpp"], eye_fs_openings_v=em["eyes"],
                          eye_fs_width_ps=[w * 1e12 for w in widths],
                          eye_fs_min_width_ps=min(widths) * 1e12,
                          eye_fs_nsym=a.fullswing_nsym)
        print(f"   full-swing eye: openings {[f'{e*1e3:.0f}' for e in em['eyes']]} mV, "
              f"min width {min(widths)*1e12:.1f} ps, RLM {em['rlm']:.4f}", flush=True)
    # layout figures (KLayout renders)
    lay_tiers = [k for k in tiers if TIERS[k]["layout"] is not None]
    if lay_tiers:
        fig_layouts(lay_tiers, M, os.path.join(FIGS, "fig_layouts"))
        last = ("f" if "f" in lay_tiers else "e" if "e" in lay_tiers else "d")
        if "b" in lay_tiers and last in lay_tiers:
            fig_layouts(["b", last], M, os.path.join(FIGS, "fig_layout_b_vs_d"))
        if last in lay_tiers:
            fig_layout_annotated(os.path.join(FIGS, "fig_layout_annotated"), tier=last)
    # tables + data
    for k in tiers:
        M[k]["tier"] = TIERS[k]["label"]
    json.dump(M, open(os.path.join(DATA, "metrics.json"), "w"), indent=1, default=float)
    keys = sorted({kk for m in M.values() for kk in m if not isinstance(m[kk], (list, dict))})
    with open(os.path.join(DATA, "metrics.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["metric"] + tiers)
        for kk in keys:
            w.writerow([kk] + [M[k].get(kk, "") for k in tiers])
    write_tables(M, os.path.join(DATA, "tables.md"))
    print(open(os.path.join(DATA, "tables.md")).read())
    print(f"report built in {time.time() - t0:.0f} s -> {HERE}")


if __name__ == "__main__":
    main()
