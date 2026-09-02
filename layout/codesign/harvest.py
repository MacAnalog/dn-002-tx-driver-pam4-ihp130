#!/usr/bin/env python3
"""Harvest a co-design run (or several islands of one round) into a compact,
committed record: results/<round>/trials.jsonl (one line per trial: params,
scalars, status, score recomputed with the project's own scorer), best.json,
and the best trial's GDS + PNG render.

    uv run python harvest.py --round r1 runs/r1_s0 runs/r1_s1 ...
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

# name: (goal, target, range, weight, reward) — mirrors the round's project_setup.yaml.
# r1/r2 and r3 do NOT share a J (r3 rewards p/n balance and power and steepens
# s11), so scores are only comparable WITHIN a round; `--specs` picks the table.
SPECS_R2 = {
    "s11": ("min", -10.0, 5.0, 10, True), "s22": ("min", -10.0, 5.0, 10, True),
    "area_um2": ("min", 11300.0, 5000.0, 1, True),
    "msb_gain": ("max", 8.2, 1.0, 5, False), "lsb_gain": ("max", 2.2, 1.0, 5, False),
    "weight": ("max", 5.0, 1.0, 5, False), "bw": ("max", 50.0, 10.0, 5, False),
    "swing": ("max", 2.1, 0.2, 5, False), "power": ("min", 192.0, 20.0, 5, False),
    "ic_ma_per_finger": ("min", 3.0, 1.0, 50, False),
    "drc_pass": ("eq", 1, 1, 100, False), "lvs_match": ("eq", 1, 1, 100, False),
    "pex_ok": ("eq", 1, 1, 100, False),
}
SPECS_R3 = {
    "s11": ("min", -10.0, 2.0, 10, True), "s22": ("min", -10.0, 5.0, 10, True),
    "pn_gain_imb_db": ("min", 0.05, 0.1, 3, True),
    "pn_phase_imb_deg": ("min", 1.0, 2.0, 4, True),
    "cm_leak_dbc": ("min", -40.0, 10.0, 5, True),
    "power": ("min", 192.0, 20.0, 3, True),
    "area_um2": ("min", 11300.0, 5000.0, 1, True),
    "msb_gain": ("max", 8.2, 1.0, 5, False), "lsb_gain": ("max", 2.2, 1.0, 5, False),
    "weight": ("max", 5.0, 1.0, 5, False), "bw": ("max", 50.0, 10.0, 5, False),
    "swing": ("max", 2.1, 0.2, 5, False),
    "ic_ma_per_finger": ("min", 3.0, 1.0, 50, False),
    "drc_pass": ("eq", 1, 1, 100, False), "lvs_match": ("eq", 1, 1, 100, False),
    "pex_ok": ("eq", 1, 1, 100, False),
}
# r4: the r3 J with reviewer margins as hinges (swing 2.2, msb_gain 8.3, lsb_gain 2.3,
# bw 55) and a small msb_gain reward (2/dB) — see project_setup.yaml (round 4).
SPECS_R4 = dict(SPECS_R3)
SPECS_R4.update({
    "msb_gain": ("max", 8.3, 1.0, 2, True), "lsb_gain": ("max", 2.3, 1.0, 5, False),
    "bw": ("max", 55.0, 10.0, 5, False), "swing": ("max", 2.2, 0.2, 5, False),
})
SPEC_TABLES = {"r2": SPECS_R2, "r3": SPECS_R3, "r4": SPECS_R4}
SPECS = SPECS_R4
MAX_PENALTY = 1e6


def score(sc: dict) -> tuple[float, bool]:
    """feasibility_reward aggregation of project_setup.yaml's specs."""
    pen, rew = 0.0, 0.0
    for name, (goal, t, rng, w, has_reward) in SPECS.items():
        v = sc.get(name)
        if v is None or v != v:
            pen -= MAX_PENALTY
            continue
        if goal == "min":
            viol = max(0.0, v - t)
        elif goal == "max":
            viol = max(0.0, t - v)
        else:
            viol = abs(v - t)
        if viol > 0:
            pen -= w * viol / rng
        elif has_reward:
            rew += w * abs(v - t) / rng
    return (rew if pen > -1e-9 else pen), pen > -1e-9


def load_runs(dirs: list[str]) -> list[dict]:
    rows = []
    for d in dirs:
        for sj in sorted(glob.glob(os.path.join(d, "**", "summary.json"), recursive=True),
                         key=lambda p: int(os.path.basename(os.path.dirname(p)).split("_")[1])):
            s = json.load(open(sj))
            sc = {k: v for k, v in (s.get("scalars") or {}).items()
                  if not (k.startswith("c_") or k.startswith("ctot_"))}
            row = {"island": os.path.basename(os.path.normpath(d)),
                   "run": os.path.basename(os.path.dirname(sj)),
                   "status": s.get("status"), "error": s.get("error"),
                   "params": s.get("params"), "deck_params": s.get("deck_params"),
                   "scalars": sc,
                   "stage_secs": {k: round(v.get("secs", 0), 1) for k, v in (s.get("stages") or {}).items()},
                   "run_dir": os.path.dirname(sj)}
            row["score"], row["feasible"] = score(sc)
            rows.append(row)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", required=True)
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    ap.add_argument("--instrument", default="", help="how the metrics were measured (recorded in summary.json)")
    ap.add_argument("--specs", default="r3", choices=sorted(SPEC_TABLES),
                    help="which round's J to re-score the trials with (default r3)")
    ap.add_argument("--accept", default="", metavar="ISLAND/RUN",
                    help="the trial the round ACCEPTS (e.g. r3_s21/run_12_layout). argmax-J is "
                         "not automatically the accepted point: J trades reflection margin for "
                         "balance/power, while acceptance also requires 'no worse than the "
                         "previous layout of record'. Copied out as accepted.{gds,png} and "
                         "recorded in summary.json.")
    a = ap.parse_args()
    global SPECS
    SPECS = SPEC_TABLES[a.specs]
    rows = load_runs(a.dirs)
    out = os.path.join(a.out, a.round)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "trials.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps({k: v for k, v in r.items() if k != "run_dir"}) + "\n")
    ok = [r for r in rows if r["status"] == "ok"]
    feas = [r for r in rows if r["feasible"]]
    best = max(rows, key=lambda r: r["score"]) if rows else None
    acc = None
    if a.accept:
        isl, run = a.accept.split("/")
        hits = [r for r in rows if r["island"] == isl and r["run"] == run]
        if not hits:
            raise SystemExit(f"--accept {a.accept}: no such trial in {a.dirs}")
        acc = hits[0]
    summ = {"round": a.round, "instrument": a.instrument, "scored_with": a.specs, "n_trials": len(rows), "n_ok": len(ok),
            "n_feasible": len(feas),
            "n_status": {s: sum(1 for r in rows if r["status"] == s)
                         for s in sorted({r["status"] for r in rows})},
            "best": {k: v for k, v in best.items() if k != "run_dir"} if best else None,
            "accepted": {k: v for k, v in acc.items() if k != "run_dir"} if acc else None}
    json.dump(summ, open(os.path.join(out, "summary.json"), "w"), indent=1)
    for tag, r in (("best", best), ("accepted", acc)):
        if not r:
            continue
        rd = r["run_dir"]
        for fn in os.listdir(rd):
            if fn.endswith(".gds") and "nomim" not in fn:
                shutil.copy(os.path.join(rd, fn), os.path.join(out, f"{tag}.gds"))
            if fn.endswith("_post.spice"):
                shutil.copy(os.path.join(rd, fn), os.path.join(out, f"{tag}_post.spice"))
        try:
            import render
            render.render(os.path.join(out, f"{tag}.gds"), os.path.join(out, f"{tag}.png"))
        except Exception as e:  # noqa: BLE001
            print(f"render {tag} skipped:", e)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
