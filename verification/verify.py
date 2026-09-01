#!/usr/bin/env python3
"""Re-run every number of the final pre/post-layout results and compare it with
the value on record (verification/expected.json = report/data/metrics.json frozen
at the time of the report). One PASS/FAIL line per number, per tier.

    uv run python verification/verify.py                     # all tiers, all steps (~10 min)
    uv run python verification/verify.py --tier d            # one tier
    uv run python verification/verify.py --step sim          # ngspice decks + extraction only
    uv run python verification/verify.py --step layout       # GDS: DRC, LVS, area, element counts
    uv run python verification/verify.py --step regen        # regenerate the GDS from layout_params.json, XOR vs the report GDS
    uv run python verification/verify.py --no-eye            # skip the (slowest) eye transient

sim   : runs the static decks in verification/decks/<tier>/ with plain `ngspice -b`
        (exactly what you would type by hand), then verification/extract.py; the
        S-parameter decks use ngspice's built-in `sp` analysis, and the *_alg twins
        (legacy in-deck .ac algebra) must agree with them
layout: KLayout DRC (sg13g2_maximal, --no_density) + LVS on report/layout/<tier>/dut_pam4.gds
        against report/layout/<tier>/dut_pam4_lvs.spice; area = top-cell bbox;
        C/R element counts of the post-layout netlist the decks include
regen : gen_layout.generate(LayoutParams(**layout_params.json)) -> XOR against the
        report GDS must be empty (the layout is a pure function of its parameters)

Tolerances (verification/expected.json "tol"): the ngspice results are
deterministic on one machine; across ngspice builds/CPUs expect differences at
the last printed digit — the tolerances are set at about that level.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import extract  # noqa: E402

DECKS = os.path.join(HERE, "decks")
EXPECTED = json.load(open(os.path.join(HERE, "expected.json")))
TOL = EXPECTED["tol"]
ORDER = ["ac_lsb", "ac_msb", "s22", "balance", "dc", "bias", "ac_msb_alg", "s22_alg", "balance_alg", "cmdm_alg", "eye"]

RESULTS: list[tuple[str, str, str, object, object, bool]] = []   # tier, key, unit, got, exp, ok


def check(tier: str, key: str, got, exp, tol=None, unit=""):
    if exp is None:
        return
    if isinstance(exp, (list, tuple)):
        ok = all(abs(g - e) <= (tol or 0) for g, e in zip(got, exp)) and len(got) == len(exp)
    elif isinstance(exp, bool) or tol is None:
        ok = got == exp
    else:
        ok = abs(got - exp) <= tol
    RESULTS.append((tier, key, unit, got, exp, ok))
    def fmt(v):
        if isinstance(v, float):
            return f"{v:.4g}"
        if isinstance(v, (list, tuple)):
            return "[" + ", ".join(f"{x:.3f}" for x in v) + "]"
        return str(v)
    print(f"   {'PASS' if ok else 'FAIL'}  {key:18s} got {fmt(got):>10}  expected {fmt(exp):>10}"
          f"{'' if tol is None else f'  (±{tol:g})'} {unit}")


def run_ngspice(deck_dir: str, deck: str, timeout: float) -> bool:
    log = os.path.join(deck_dir, deck.replace(".spice", ".log"))
    with open(log, "w") as f:
        r = subprocess.run(["ngspice", "-b", deck], cwd=deck_dir, stdout=f, stderr=subprocess.STDOUT, timeout=timeout)
    return r.returncode == 0


def step_sim(tier: str, no_eye: bool) -> None:
    d = os.path.join(DECKS, tier)
    if shutil.which("ngspice") is None:
        raise SystemExit("ngspice not on PATH")
    for env in ("PDK_ROOT",):
        if not os.environ.get(env):
            raise SystemExit(f"{env} not set (the decks' .spiceinit resolves the IHP models through $PDK_ROOT/$PDK)")
    os.environ.setdefault("PDK", "ihp-sg13g2")
    order = ORDER + (["eye_fs"] if os.path.exists(os.path.join(d, "eye_fs.spice")) else [])
    for name in order:
        if name.startswith("eye") and no_eye:
            continue
        t0 = time.time()
        ok = run_ngspice(d, name + ".spice", timeout=3600)
        print(f"   ngspice -b {name}.spice  -> {'ok' if ok else 'FAILED'} ({time.time() - t0:.0f} s)")
    got = extract.extract(tier, d, verbose=False)
    exp = EXPECTED["tiers"][tier]
    for key in ("lsb_gain", "msb_gain", "weight", "bw_lsb", "bw_msb", "bw", "s11_lsb", "s11_msb", "s11", "s11_edge_ghz",
                "s22", "s22_edge_ghz", "pn_gain_imb_db", "pn_phase_imb_deg", "cm_leak_dbc", "cm_dm_db", "swing", "power",
                "ic_ma_per_finger", "eye_rlm", "eye_min_v", "eye_vpp", "eye_fs_min_v", "eye_fs_min_width_ps", "eye_fs_rlm"):
        if key in got and key in exp:
            check(tier, key, got[key], exp[key], TOL.get(key, TOL["default"]), EXPECTED["units"].get(key, ""))
    # independent method (legacy .ac algebra) must agree with the primary `sp` decks
    for a_, b_, tol_, unit in (("alg_msb_gain", "msb_gain", 0.01, "dB"), ("alg_bw_msb", "bw_msb", 0.05, "GHz"),
                               ("alg_s11_msb", "s11_msb", 0.01, "dB"), ("alg_s11_edge_msb", "s11_edge_ghz", 0.05, "GHz"),
                               ("alg_s22", "s22", 0.01, "dB"), ("alg_s22_edge_ghz", "s22_edge_ghz", 0.05, "GHz"),
                               ("alg_pn_gain_imb_db", "pn_gain_imb_db", 0.002, "dB"),
                               ("alg_pn_phase_imb_deg", "pn_phase_imb_deg", 0.02, "deg"),
                               ("alg_cm_leak_dbc", "cm_leak_dbc", 0.5, "dBc"),
                               ("alg_cm_dm_db", "cm_dm_db", 0.5, "dB")):
        if b_ in ("cm_leak_dbc", "cm_dm_db") and got.get(b_, 0) < -150:
            continue          # ideal-symmetry noise floor: both methods read < -150, exact value is numerical
        if a_ in got and b_ in got and (b_ != "s11_edge_ghz" or got["s11_msb"] >= got.get("s11_lsb", -1e9)):
            check(tier, f"{a_} == {b_}", got[a_], got[b_], tol_, unit + "  (legacy .ac algebra vs ngspice sp)")
    if "eye_openings_v" in got and "eye_openings_v" in exp:
        check(tier, "eye_openings_v", got["eye_openings_v"], exp["eye_openings_v"], TOL["eye_min_v"], "V")


def step_layout(tier: str) -> None:
    if tier == "a":
        return
    sys.path.insert(0, os.path.join(ROOT, "layout"))
    import signoff                                                     # vendored KLayout DRC/LVS runner
    import klayout.db as kdb
    lay = os.path.join(ROOT, "report", "layout", tier)
    gds = os.path.join(lay, "dut_pam4.gds")
    net = os.path.join(lay, "dut_pam4_lvs.spice")
    run = os.path.join(HERE, "work", tier)
    os.makedirs(run, exist_ok=True)
    cwd0 = os.getcwd(); os.chdir(run)
    try:
        drc_ok, dlog = signoff.run_drc(gds, "pam4drv_pam4_lay", os.path.join(run, "drc"))
        lvs_ok, _ = signoff.run_lvs(gds, net, "pam4drv_pam4_lay", os.path.join(run, "lvs"))
    finally:
        os.chdir(cwd0)
    exp = EXPECTED["tiers"][tier]
    check(tier, "drc_pass", bool(drc_ok), bool(exp["drc_pass"]))
    if not drc_ok:
        print("      " + "\n      ".join(l for l in dlog.splitlines() if "Violated" in l))
    check(tier, "lvs_match", bool(lvs_ok), bool(exp["lvs_match"]))
    ly = kdb.Layout(); ly.read(gds); bb = ly.top_cell().dbbox()
    check(tier, "width_um", float(bb.width()), exp["width_um"], 0.01, "µm")
    check(tier, "height_um", float(bb.height()), exp["height_um"], 0.01, "µm")
    check(tier, "area_um2", float(bb.width() * bb.height()), exp["area_um2"], 0.5, "µm²")
    post = os.path.join(lay, "dut_pam4_post.spice")
    n_c = sum(1 for l in open(post) if l[:1] == "C"); n_r = sum(1 for l in open(post) if l[:1] == "R")
    check(tier, "pex_n_c", n_c, int(exp["pex_n_c"]))
    check(tier, "pex_n_r", n_r, int(exp["pex_n_r"]))


def step_regen(tier: str) -> None:
    if tier == "a":
        return
    sys.path.insert(0, os.path.join(ROOT, "layout"))
    import gen_layout
    import klayout.db as kdb
    lay = os.path.join(ROOT, "report", "layout", tier)
    p = gen_layout.LayoutParams(**json.load(open(os.path.join(lay, "layout_params.json"))))
    run = os.path.join(HERE, "work", tier, "regen")
    os.makedirs(run, exist_ok=True)
    cwd0 = os.getcwd(); os.chdir(run)                                # the ihp PyCell writes temp.gds in cwd
    try:
        info = gen_layout.generate("pam4", p, run)
    finally:
        os.chdir(cwd0)
    a = kdb.Layout(); a.read(info["gds"]); b = kdb.Layout(); b.read(os.path.join(lay, "dut_pam4.gds"))
    ta, tb = a.top_cell(), b.top_cell()
    diff_area = 0.0
    layers = {(a.get_info(i).layer, a.get_info(i).datatype) for i in a.layer_indexes()} | \
             {(b.get_info(i).layer, b.get_info(i).datatype) for i in b.layer_indexes()}
    for (l, dt) in sorted(layers):
        ra = kdb.Region(ta.begin_shapes_rec(a.layer(l, dt))) if a.find_layer(l, dt) is not None else kdb.Region()
        rb = kdb.Region(tb.begin_shapes_rec(b.layer(l, dt))) if b.find_layer(l, dt) is not None else kdb.Region()
        diff_area += (ra ^ rb).area()
    check(tier, "regen_xor_area", float(diff_area) * (a.dbu ** 2), 0.0, 1e-6, "µm² (regenerated GDS XOR report GDS)")
    check(tier, "regen_area_um2", float(info["area_um2"]), EXPECTED["tiers"][tier]["area_um2"], 0.5, "µm²")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="a,b,c,d,f")
    ap.add_argument("--step", default="sim,layout,regen", help="comma list of sim,layout,regen")
    ap.add_argument("--no-eye", action="store_true")
    a = ap.parse_args()
    steps = a.step.split(",")
    for tier in a.tier.split(","):
        print(f"== tier {tier}: {EXPECTED['tiers'][tier]['tier']}")
        if "sim" in steps:
            step_sim(tier, a.no_eye)
        if "layout" in steps:
            step_layout(tier)
        if "regen" in steps:
            step_regen(tier)
    n_ok = sum(1 for r in RESULTS if r[5]); n = len(RESULTS)
    print(f"\n{n_ok}/{n} numbers reproduce within tolerance" + ("" if n_ok == n else "  — FAILURES:"))
    for t, k, u, g, e, ok in RESULTS:
        if not ok:
            print(f"   {t} {k}: got {g} expected {e}")
    json.dump([dict(tier=t, key=k, got=g, expected=e, ok=ok) for t, k, u, g, e, ok in RESULTS],
              open(os.path.join(HERE, "last_run.json"), "w"), indent=1, default=float)
    raise SystemExit(0 if n_ok == n else 1)


if __name__ == "__main__":
    main()
