#!/usr/bin/env python3
"""Re-measure ONE trial of a co-design round at a different kpex halo.

The search runs at `pex.halo_um: 20` (flow.yaml) so the gap knobs cannot buy
fake coupling steps; the block's report instrument is the SG13G2 tech default
halo 8 (flow_halo8.yaml, = layout/pex_sim.py with no KPEX_HALO_UM). Before any
candidate is accepted it is re-built and re-measured at halo 8, because the
eight signoff specs are the ones the block reports there.

    python3 remeasure.py runs/r3_s18/layout/run_12_layout --tag cand1
    python3 remeasure.py <trial_dir> --flow flow.yaml --tag foo   # halo 20 re-run

Writes runs/rm_<tag>/ (one trial) and prints its scorecard.
"""
from __future__ import annotations
import argparse, glob, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM = os.environ.get("SPX_PLATFORM") or os.path.abspath(
    os.path.join(HERE, "..", "..", "..", "..", "spicexplorer-platform"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trial_dir", help="run_<n>_layout dir (or its summary.json)")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--flow", default="flow_halo8.yaml")
    ap.add_argument("--setup", default="project_setup.yaml")
    ap.add_argument("--set", action="append", default=[], metavar="KNOB=VAL",
                    help="override one knob of the trial (one-knob A/B of an accepted point)")
    a = ap.parse_args()
    sj = a.trial_dir if a.trial_dir.endswith(".json") else os.path.join(a.trial_dir, "summary.json")
    s = json.load(open(sj))
    pt = dict(s["params"]); pt.update(s.get("deck_params") or {})
    for kv in a.set:
        k, v = kv.split("=", 1)
        pt[k] = float(v)
    import yaml
    cfg = yaml.safe_load(open(os.path.join(HERE, a.setup)))
    ps = cfg.get("project") or cfg.get("project_setup") or cfg
    ps["netlist"] = a.flow
    for tb in ps.get("testbenches", []):
        tb["netlist"] = a.flow
    miss = []
    for d in ps["dut_params"]:
        if d["name"] in pt:
            v = pt[d["name"]]
            d["init"] = int(v) if d.get("is_integer") else float(v)
            # bounds stay as they are (the platform refuses min == max); with
            # budget 1 + seed_from_init, trial 1 IS the init point.
            d["min_val"] = min(d["min_val"], d["init"])
            d["max_val"] = max(d["max_val"], d["init"])
        else:
            # knob added to G AFTER this trial ran: the trial used the
            # generator default, which is what the setup's init carries.
            miss.append(f'{d["name"]}={d["init"]}')
    if miss:
        print("knobs taken from the setup init (absent from the trial):", ", ".join(miss))
    ps["optimizer_config"]["budget"] = 1
    ps["optimizer_config"]["seed_from_init"] = True
    ps["optimizer_config"]["optimizer_kwargs"] = {"num_workers": 1}
    tmp = os.path.join(HERE, f"_rm_{a.tag}_project_setup.yaml")
    yaml.safe_dump(cfg, open(tmp, "w"), sort_keys=False)
    out = os.path.join(HERE, f"runs/rm_{a.tag}")
    cmd = ["uv", "run", "--project", PLATFORM, "spicexplorer-optimize", tmp,
           "--budget", "1", "--workers", "1", "--outdir", out, "--no-timestamp", "--quiet"]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=HERE, check=False)
    for f in sorted(glob.glob(f"{out}/**/summary.json", recursive=True)):
        r = json.load(open(f))
        sc = {k: v for k, v in r["scalars"].items() if not k.startswith(("c_", "ctot_"))}
        print(json.dumps({"status": r["status"], "scalars": sc}, indent=1))


if __name__ == "__main__":
    main()
