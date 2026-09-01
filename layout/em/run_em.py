#!/usr/bin/env python3
"""Full-wave S-parameters of an EM-cut GDS with openEMS (FDTD), through the
IHP PDK's own SG13G2 workflow (libs.tech/openems/openems_ihp_sg13g2).

Thin CLI over the platform package: the workflow driving (ports, stackup,
mesh, per-port excitations, touchstone) lives in
``spicexplorer_layout.em.em_sparams``; the process description is the
packaged ``EmTech.builtin("ihp-sg13g2")`` and every solver hyperparameter
is an ``EmSim`` field, loadable from ``--config`` YAML (CLI overrides it).

    ./run_em.sh run_em.py em_cut.gds ports.yaml --config target/em_sim.yaml
"""
from __future__ import annotations

import argparse
import sys

import yaml

from spicexplorer_layout import em


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("ports_yaml")
    ap.add_argument("--config", default="",
                    help="YAML with any of the flags below as keys (CLI overrides "
                         "it; commit it next to the results for reproducibility)")
    ap.add_argument("--stackup", default="",
                    help="stackup XML override (default: the PDK workflow's, "
                         "from the packaged tech config)")
    ap.add_argument("--out", default="em_out")
    ap.add_argument("--fstart", type=float, default=0.0)
    ap.add_argument("--fstop", type=float, default=60e9)
    ap.add_argument("--numfreq", type=int, default=241)
    ap.add_argument("--cellsize", type=float, default=0.5,
                    help="refined mesh cell (um) in conductor regions; traces here are 0.55-2 um")
    ap.add_argument("--margin", type=float, default=50.0)
    ap.add_argument("--energy-limit", type=float, default=-40.0)
    ap.add_argument("--boundary", nargs=6, default=["PEC"] * 6,
                    metavar=("XMIN", "XMAX", "YMIN", "YMAX", "ZMIN", "ZMAX"),
                    help="the six openEMS boundary conditions")
    ap.add_argument("--ports", default="", help="comma list: excite only these port numbers (default all)")
    cfg_path = ap.parse_known_args()[0].config
    cfg = {}
    if cfg_path:
        cfg = yaml.safe_load(open(cfg_path)) or {}
        unknown = set(cfg) - {a_.dest for a_ in ap._actions}
        if unknown:
            raise SystemExit(f"unknown keys in {cfg_path}: {sorted(unknown)}")
        if "ports" in cfg and isinstance(cfg["ports"], list):
            cfg["ports"] = ",".join(str(x) for x in cfg["ports"])
        ap.set_defaults(**cfg)
    a = ap.parse_args()

    # loud config resolution: every solver knob with its value and where it
    # came from (cli beats config beats default) — no silent defaults
    solver_keys = ("stackup", "fstart", "fstop", "numfreq", "cellsize",
                   "margin", "energy_limit", "boundary", "ports")
    print(f"solver setup ({cfg_path or 'no --config'}):")
    for k in solver_keys:
        flag = "--" + k.replace("_", "-")
        src = ("cli" if any(arg == flag or arg.startswith(flag + "=")
                            for arg in sys.argv[1:])
               else "config" if k in cfg else "DEFAULT")
        print(f"  {k:13} = {getattr(a, k)!r:60}  [{src}]")

    tech = em.EmTech.builtin("ihp-sg13g2")
    sim = em.EmSim(
        fstart=a.fstart, fstop=a.fstop, numfreq=a.numfreq,
        cellsize_um=a.cellsize, margin_um=a.margin,
        energy_limit_db=a.energy_limit, boundary=tuple(a.boundary),
        excite_ports=tuple(int(x) for x in a.ports.split(",") if x) or None)
    ports = yaml.safe_load(open(a.ports_yaml))["ports"]
    snp = em.em_sparams(a.gds, ports, a.out, tech=tech, sim=sim,
                        stackup_xml=a.stackup or None)
    print("wrote", snp)


if __name__ == "__main__":
    main()
