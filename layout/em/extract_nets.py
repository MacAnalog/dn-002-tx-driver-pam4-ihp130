#!/usr/bin/env python3
"""Cut an EM-simulation GDS out of a signed-off layout, one net at a time.

Thin CLI over the platform package — the tracing (KLayout LayoutToNetlist,
metal-only), the mesh-robust via bars, and the common-ground scheme (ONE
SUBGND plane + Activ/Cont columns under the gnd nets' Metal1) all live in
``spicexplorer_layout.em.extract_net_gds``; the process numbers come from
the packaged tech config ``EmTech.builtin("ihp-sg13g2")``.

    .venv/bin/python extract_nets.py --gds dut.gds --nets outp outn sub vcc \
        --ports ports.yaml --out em_out.gds
    .venv/bin/python extract_nets.py --gds dut.gds --nets outp --candidates
"""
from __future__ import annotations

import argparse
import json
import os

from spicexplorer_layout import em

TECH = em.EmTech.builtin("ihp-sg13g2")


def candidates(gds: str, nets: list[str]) -> None:
    """Print per-net leaf islands (Metal1/Metal2) to pick tap ports —
    a discovery aid, so it re-traces locally with the same tech tables."""
    import klayout.db as kdb

    ly = kdb.Layout()
    ly.read(gds)
    top = ly.top_cell()
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, top, []))
    regions = {}
    for name, ln in {**TECH.metals, **TECH.vias}.items():
        regions[name] = l2n.make_polygon_layer(ly.layer(ln, 0), name)
    for name, ln in TECH.metals.items():
        t = l2n.make_text_layer(ly.layer(ln, TECH.text_datatype), name + "_txt")
        l2n.connect(regions[name])
        l2n.connect(regions[name], t)
    for via, (below, above) in TECH.via_stack.items():
        l2n.connect(regions[via])
        l2n.connect(regions[below], regions[via])
        l2n.connect(regions[via], regions[above])
    l2n.extract_netlist()
    circuit = l2n.netlist().circuit_by_name(top.name)
    for netname in nets:
        net = circuit.net_by_name(netname)
        if net is None:
            names = sorted(n.name for n in circuit.each_net() if n.name)
            raise SystemExit(f"net {netname!r} not found; labelled nets: {names}")
        layers = [n for n in list(TECH.metals) + list(TECH.vias)
                  if not l2n.shapes_of_net(net, regions[n], True).is_empty()]
        print(f"== net {netname}: layers {layers}")
        for lname in ("Metal1", "Metal2"):
            for p in l2n.shapes_of_net(net, regions[lname], True).each_merged():
                b = p.bbox()
                d = ly.dbu
                print(f"   {lname} island um "
                      f"[{b.left*d:.2f},{b.bottom*d:.2f},{b.right*d:.2f},{b.top*d:.2f}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", required=True)
    ap.add_argument("--nets", nargs="+", required=True)
    ap.add_argument("--out")
    ap.add_argument("--ports", help="ports.yaml (adds port rectangles on "
                                    f"{TECH.port_layer_base}+num)")
    ap.add_argument("--gnd-nets", nargs="*", default=["sub"],
                    help="nets whose Metal1 is contacted down to the common "
                         "SUBGND plane (Activ+Cont columns under their shapes)")
    ap.add_argument("--candidates", action="store_true",
                    help="print per-net leaf islands (Metal1/Metal2 polygons) to pick tap ports")
    a = ap.parse_args()

    if a.candidates:
        candidates(a.gds, a.nets)
        return

    ports = None
    if a.ports:
        import yaml
        ports = yaml.safe_load(open(a.ports))["ports"]
    manifest = em.extract_net_gds(a.gds, a.nets, a.out, ports,
                                  tech=TECH, gnd_nets=a.gnd_nets)
    manifest["source_gds"] = os.path.abspath(a.gds)
    with open(os.path.splitext(a.out)[0] + "_manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"wrote {a.out}: nets {sorted(manifest['nets'])}, "
          f"{len(manifest['ports'])} ports")


if __name__ == "__main__":
    main()
