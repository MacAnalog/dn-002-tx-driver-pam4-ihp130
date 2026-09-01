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
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_nets import trace, net_shapes

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
