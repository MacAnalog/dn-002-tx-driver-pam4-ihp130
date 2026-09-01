#!/usr/bin/env python3
"""Full-wave S-parameters of an EM-cut GDS with openEMS (FDTD), through the
IHP PDK's own SG13G2 workflow (libs.tech/openems/openems_ihp_sg13g2).

    python3 run_em.py em_cut.gds ports.yaml --fstop 60e9 --out out_dir
        [--stackup SG13G2.xml] [--cellsize 0.5] [--preview]

Needs the openEMS python module (see README "Solver install"); everything
else (stackup, GDS reader, mesher, port builder, touchstone writer) is the
PDK's, imported from $PDK_ROOT — this script only adapts our ports.yaml to
its `simulation_port` objects and loops the per-port excitations.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import yaml

PDK_ROOT = os.environ.get("PDK_ROOT", os.path.expanduser("~/local/pdks"))
WORKFLOW = os.path.join(PDK_ROOT, "ihp-sg13g2/libs.tech/openems/openems_ihp_sg13g2/workflow")
PORT_LAYER_BASE = 300


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gds")
    ap.add_argument("ports_yaml")
    ap.add_argument("--config", default="",
                    help="YAML with any of the flags below as keys (CLI overrides "
                         "it; commit it next to the results for reproducibility)")
    ap.add_argument("--stackup", default=os.path.join(WORKFLOW, "SG13G2.xml"),
                    help="stackup XML (SG13G2.xml = lossy substrate; _nosub for smoke runs)")
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
    ap.add_argument("--preview", action="store_true", help="geometry/mesh preview only, no solve")
    ap.add_argument("--ports", default="", help="comma list: excite only these port numbers (default all)")
    cfg_path = ap.parse_known_args()[0].config
    if cfg_path:
        cfg = yaml.safe_load(open(cfg_path)) or {}
        unknown = set(cfg) - {a_.dest for a_ in ap._actions}
        if unknown:
            raise SystemExit(f"unknown keys in {cfg_path}: {sorted(unknown)}")
        if "ports" in cfg and isinstance(cfg["ports"], list):
            cfg["ports"] = ",".join(str(x) for x in cfg["ports"])
        ap.set_defaults(**cfg)
    a = ap.parse_args()

    sys.path.insert(0, WORKFLOW)
    sys.path.insert(0, os.path.join(WORKFLOW, "modules"))
    import modules.util_stackup_reader as stackup_reader
    import modules.util_gds_reader as gds_reader
    import modules.util_utilities as utilities
    import modules.util_simulation_setup as simulation_setup
    import modules.util_meshlines as util_meshlines
    from openEMS import openEMS

    # headless: the PDK module launches the AppCSXCAD GUI viewer on the first
    # excitation; replace it with a no-op (`true` ignores its argument)
    simulation_setup.AppCSXCAD_BIN = "true"
    simulation_setup.sys = sys

    sim_path = os.path.abspath(a.out)
    os.makedirs(sim_path, exist_ok=True)

    spec = yaml.safe_load(open(a.ports_yaml))["ports"]
    sim_ports = simulation_setup.all_simulation_ports()
    for p in spec:
        ln = PORT_LAYER_BASE + p["num"]
        if p["kind"] == "via":
            sp = simulation_setup.simulation_port(
                portnumber=p["num"], voltage=1, port_Z0=p.get("z0", 50),
                source_layernum=ln, from_layername=p["from_layer"],
                to_layername=p["to_layer"], direction=p.get("direction", "z"))
        else:
            sp = simulation_setup.simulation_port(
                portnumber=p["num"], voltage=1, port_Z0=p.get("z0", 50),
                source_layernum=ln, target_layername=p["layer"],
                direction=p["direction"])
        sim_ports.add_port(sp)

    materials_list, dielectrics_list, metals_list = stackup_reader.read_substrate(a.stackup)
    # the workflow treats a polygon as a port ONLY if its layer is absent from
    # the stackup; a collision (e.g. 200+10 = 210 = SUBGND) silently swallows
    # the port rect as metal and the excitation run never injects any energy
    for p in sim_ports.ports:
        clash = metals_list.getbylayernumber(p.source_layernum)
        if clash is not None:
            raise SystemExit(
                f"port {p.portnumber}: source layer {p.source_layernum} is stackup "
                f"layer {getattr(clash, 'name', clash)} — move PORT_LAYER_BASE")
    layernumbers = metals_list.getlayernumbers()
    layernumbers.extend(sim_ports.portlayers)
    allpolygons = gds_reader.read_gds(a.gds, layernumbers, purposelist=[0],
                                      metals_list=metals_list, preprocess=False,
                                      merge_polygon_size=0)

    unit = 1e-6
    wavelength_air = 3e8 / a.fstop / unit
    max_cellsize = wavelength_air / (np.sqrt(materials_list.eps_max) * 20)

    excite = ([int(x) for x in a.ports.split(",") if x] or
              [p.portnumber for p in sim_ports.ports])
    basename = os.path.splitext(os.path.basename(a.gds))[0]
    for pnum in excite:
        FDTD = openEMS(EndCriteria=np.exp(a.energy_limit / 10 * np.log(10)))
        FDTD.SetGaussExcite((a.fstart + a.fstop) / 2, (a.fstop - a.fstart) / 2)
        FDTD.SetBoundaryCond(list(a.boundary))
        simulation_setup.setupSimulation([pnum], sim_ports, FDTD, materials_list,
                                         dielectrics_list, metals_list, allpolygons,
                                         max_cellsize, a.cellsize, a.margin, unit,
                                         xy_mesh_function=util_meshlines.create_xy_mesh_from_polygons)
        simulation_setup.runSimulation([pnum], FDTD, sim_path, basename,
                                       a.preview, False)
    if a.preview:
        return

    n = sim_ports.portcount
    f = np.linspace(a.fstart, a.fstop, a.numfreq)
    s = np.empty((n, n, a.numfreq), dtype=object)
    for i in range(1, n + 1):
        for j in range(1, n + 1):
            s[i - 1, j - 1] = utilities.calculate_Sij(i, j, f, sim_path, sim_ports)
    snp = os.path.join(sim_path, f"{basename}.s{n}p")
    utilities.write_snp(s, f, snp)
    print("wrote", snp)


if __name__ == "__main__":
    main()
