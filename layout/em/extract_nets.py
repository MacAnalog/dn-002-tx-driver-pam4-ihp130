#!/usr/bin/env python3
"""Cut an EM-simulation GDS out of a signed-off layout, one net at a time.

Traces METAL-ONLY connectivity (Metal1..TopMetal2 through Via1..TopVia2 —
contacts and devices excluded, so a net's shapes stop at the device pads)
with KLayout's LayoutToNetlist, names the nets from the generator's text
labels, and writes the selected nets' polygons to a new GDS on their native
SG13G2 layer numbers (the numbers the PDK openEMS stackup XML expects).
Port rectangles from ports.yaml are added on GDS layer (300+portnum, 0).

    .venv/bin/python extract_nets.py --gds dut.gds --nets outp outn sub vcc \
        --ports ports.yaml --out em_out.gds
    .venv/bin/python extract_nets.py --gds dut.gds --nets outp --candidates
"""
from __future__ import annotations

import argparse
import json
import os

import klayout.db as kdb

# SG13G2 GDS layer numbers (= the PDK openEMS stackup XML "Layer" numbers).
METALS = {"Metal1": 8, "Metal2": 10, "Metal3": 30, "Metal4": 50, "Metal5": 67,
          "TopMetal1": 126, "TopMetal2": 134}
VIAS = {"Via1": 19, "Via2": 29, "Via3": 49, "Via4": 66,
        "TopVia1": 125, "TopVia2": 133}
# via -> (metal below, metal above)
VIA_STACK = {"Via1": ("Metal1", "Metal2"), "Via2": ("Metal2", "Metal3"),
             "Via3": ("Metal3", "Metal4"), "Via4": ("Metal4", "Metal5"),
             "TopVia1": ("Metal5", "TopMetal1"), "TopVia2": ("TopMetal1", "TopMetal2")}
TEXT_DT = 25  # net-label datatype on the metal layer number
PORT_LAYER_BASE = 300  # must stay clear of every SG13G2 stackup layer (SUBGND is 210!)


def trace(gds: str) -> tuple[kdb.Layout, kdb.LayoutToNetlist, dict]:
    ly = kdb.Layout()
    ly.read(gds)
    top = ly.top_cell()
    l2n = kdb.LayoutToNetlist(kdb.RecursiveShapeIterator(ly, top, []))
    regions: dict[str, object] = {}
    for name, ln in {**METALS, **VIAS}.items():
        regions[name] = l2n.make_polygon_layer(ly.layer(ln, 0), name)
    texts = {}
    for name, ln in METALS.items():
        texts[name] = l2n.make_text_layer(ly.layer(ln, TEXT_DT), name + "_txt")
    for name in METALS:
        l2n.connect(regions[name])
        l2n.connect(regions[name], texts[name])
    for via, (below, above) in VIA_STACK.items():
        l2n.connect(regions[via])
        l2n.connect(regions[below], regions[via])
        l2n.connect(regions[via], regions[above])
    l2n.extract_netlist()
    return ly, l2n, regions


def net_shapes(ly, l2n, regions, netname: str) -> dict[str, kdb.Region]:
    circuit = l2n.netlist().circuit_by_name(ly.top_cell().name)
    net = circuit.net_by_name(netname)
    if net is None:
        names = sorted(n.name for n in circuit.each_net() if n.name)
        raise SystemExit(f"net {netname!r} not found; labelled nets: {names}")
    out = {}
    for name in list(METALS) + list(VIAS):
        r = l2n.shapes_of_net(net, regions[name], True)
        if not r.is_empty():
            out[name] = r
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", required=True)
    ap.add_argument("--nets", nargs="+", required=True)
    ap.add_argument("--out")
    ap.add_argument("--ports", help="ports.yaml (adds port rectangles on 300+num)")
    ap.add_argument("--candidates", action="store_true",
                    help="print per-net leaf islands (Metal1/Metal2 polygons) to pick tap ports")
    a = ap.parse_args()

    ly, l2n, regions = trace(a.gds)
    dbu = ly.dbu

    if a.candidates:
        for netname in a.nets:
            shp = net_shapes(ly, l2n, regions, netname)
            print(f"== net {netname}: layers {sorted(shp)}")
            for lname in ("Metal1", "Metal2"):
                for p in shp.get(lname, kdb.Region()).each_merged():
                    b = p.bbox()
                    print(f"   {lname} island um "
                          f"[{b.left*dbu:.2f},{b.bottom*dbu:.2f},{b.right*dbu:.2f},{b.top*dbu:.2f}]")
        return

    out_ly = kdb.Layout()
    out_ly.dbu = dbu
    out_top = out_ly.create_cell("em_cut")
    manifest = {"source_gds": os.path.abspath(a.gds), "nets": {}, "ports": []}
    for netname in a.nets:
        shp = net_shapes(ly, l2n, regions, netname)
        manifest["nets"][netname] = sorted(shp)
        for lname, region in shp.items():
            ln = (METALS | VIAS)[lname]
            out_top.shapes(out_ly.layer(ln, 0)).insert(region)

    if a.ports:
        import yaml
        ports = yaml.safe_load(open(a.ports))["ports"]
        for p in ports:
            x1, y1, x2, y2 = p["rect"]
            box = kdb.DBox(x1, y1, x2, y2)
            out_top.shapes(out_ly.layer(PORT_LAYER_BASE + p["num"], 0)).insert(box)
            if p.get("subgnd"):
                # idealized local substrate contact under the port (stackup
                # layer SUBGND = GDS 210, LOWLOSS column through the EPI)
                out_top.shapes(out_ly.layer(210, 0)).insert(box)
            manifest["ports"].append(p)

    out_ly.write(a.out)
    with open(os.path.splitext(a.out)[0] + "_manifest.json", "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"wrote {a.out}: nets {sorted(manifest['nets'])}, {len(manifest['ports'])} ports")


if __name__ == "__main__":
    main()
