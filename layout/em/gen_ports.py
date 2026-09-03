#!/usr/bin/env python3
"""Generate ports.yaml for the OUTPUT-NETWORK EM cut of the PAM-4 driver.

Port scheme (rationale + approximations in README.md):
  * edge ports (bench side): vertical via-ports Metal1(sub column) -> bus
    metal, placed where the outp/outn/vcc bus crosses over a `sub` Metal1
    column — the PDK examples' M1-ground-to-signal pattern (rfcmim).
  * tap ports (device side): short vertical via-ports SUBGND -> Metal1
    under each device-facing pad. extract_nets.py draws the matching SUBGND
    (GDS 210) patch, an idealized local substrate contact ~ the lumped
    bench's ground reference at the device.
Cell mapping (cell_order=1: M0 | M1 | L0 left to right) is recorded per tap
so em_compare.py can splice the fitted N-port against the LVS netlist
(QQ3<cell> collector = outp tap, QQ4<cell> = outn tap).
"""
from __future__ import annotations
import os, sys
import yaml
import klayout.db as kdb
from spicexplorer_layout.em import EmTech

TECH = EmTech.builtin("ihp-sg13g2")


def trace(gds: str):
    """Metal-only connectivity of `gds` (labels name the nets) — the same
    LayoutToNetlist recipe `spicexplorer_layout.em.extract_net_gds` uses,
    kept here because the port generator needs the per-net REGIONS, which
    the extractor does not return."""
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
    return ly, l2n, regions


def net_shapes(ly, l2n, regions, netname: str) -> dict:
    """{layer: Region} of one labelled net (empty Regions for absent layers)."""
    circuit = l2n.netlist().circuit_by_name(ly.top_cell().name)
    net = circuit.net_by_name(netname)
    if net is None:
        names = sorted(n.name for n in circuit.each_net() if n.name)
        raise ValueError(f"net {netname!r} not found; labelled nets: {names}")
    return {lname: l2n.shapes_of_net(net, regions[lname], True) for lname in regions}

CELLS = ["M0", "M1", "L0"]   # left-to-right for cell_order=1

def main() -> None:
    gds, out_yaml = sys.argv[1], sys.argv[2]
    ly, l2n, regions = trace(gds)
    dbu = ly.dbu
    S = {n: net_shapes(ly, l2n, regions, n) for n in ("outp", "outn", "vcc", "sub")}
    sub_m1 = S["sub"]["Metal1"]
    ports = []

    def dbox(b):
        return [round(b.left*dbu,3), round(b.bottom*dbu,3), round(b.right*dbu,3), round(b.top*dbu,3)]

    def add(**kw):
        kw["num"] = len(ports) + 1
        kw.setdefault("z0", 50)
        ports.append(kw)
        print(f"P{kw['num']:>2} {kw['role']:<11} {kw.get('net','')}: {kw['rect']}")

    # edge ports: leftmost overlap of the top-layer bus with a sub Metal1 column
    for net, top_l in (("outp", "TopMetal1"), ("outn", "TopMetal2"), ("vcc", "TopMetal2")):
        ov = S[net][top_l] & sub_m1
        if ov.is_empty() and net == "vcc":
            # co-design r4 `vcc_trim`: the rail spans only the two R_C stacks and
            # crosses no substrate column -> reference the feed to the common
            # SUBGND plane instead (a vertical port at the rail's left end, the
            # rail's own width, 1 um long)
            rail = min(S[net][top_l].each_merged(), key=lambda p: p.bbox().left).bbox()
            um = int(1.0 / dbu)
            patch_box = kdb.Box(rail.left, rail.bottom, rail.left + um, rail.top)
            add(kind="via", rect=dbox(patch_box), net=net, role="edge",
                from_layer="SUBGND", to_layer=top_l, direction="z", subgnd=True)
            continue
        assert not ov.is_empty(), f"{net}: no {top_l}/sub-M1 crossing for the edge port"
        patch = min(ov.each_merged(), key=lambda p: p.bbox().left)
        add(kind="via", rect=dbox(patch.bbox()), net=net, role="edge",
            from_layer="Metal1", to_layer=top_l, direction="z")

    # tap ports: SUBGND -> Metal1 under each device-facing island
    for net in ("outp", "outn"):
        isl = sorted(S[net]["Metal1"].each_merged(), key=lambda p: p.bbox().left)
        coll = [p for p in isl if p.bbox().top*dbu < 17]      # collector pads
        rc   = [p for p in isl if p.bbox().top*dbu >= 17]     # R_C riser pad
        assert len(coll) == 3 and len(rc) == 1, (net, len(coll), len(rc))
        for cell, p in zip(CELLS, coll):
            add(kind="via", rect=dbox(p.bbox()), net=net, role="coll_tap", cell=cell,
                from_layer="SUBGND", to_layer="Metal1", direction="z", subgnd=True)
        add(kind="via", rect=dbox(rc[0].bbox()), net=net, role="rc_tap",
            from_layer="SUBGND", to_layer="Metal1", direction="z", subgnd=True)
    for p in sorted(S["vcc"]["Metal1"].each_merged(), key=lambda q: q.bbox().left):
        add(kind="via", rect=dbox(p.bbox()), net="vcc", role="rc_vcc_tap",
            from_layer="SUBGND", to_layer="Metal1", direction="z", subgnd=True)

    yaml.safe_dump({"ports": ports}, open(out_yaml, "w"), sort_keys=False)
    print(f"wrote {out_yaml}: {len(ports)} ports")

if __name__ == "__main__":
    main()
