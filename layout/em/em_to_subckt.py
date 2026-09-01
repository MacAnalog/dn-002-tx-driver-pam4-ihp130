#!/usr/bin/env python3
"""Touchstone N-port -> ngspice subcircuit via scikit-rf vector fitting.

Thin CLI over ``spicexplorer_layout.em.em_to_subckt`` — the passivity
guards (renormalize FDTD noise-level violations, pole ladder + enforce) and
the DC anchor live in the package.

    python3 em_to_subckt.py em.s13p --name em_outnet --out em_outnet.sub \
        [--poles 12] [--dc-from-data | --dc-r "1:2=0.8,3:4=1.2"]

Both guards matter before splicing into a bias-carrying bench (README):
the benches push BIAS CURRENT through these nets, so the fit must be right
at f=0, where FDTD data is weakest. --dc-from-data anchors with Re(Y) at
the lowest kept frequency (valid once the EM cut has a common ground
plane); --dc-r anchors with explicit port-pair resistances. Either way the
spliced deck's .op is checked against the kpex deck (em_compare.py) — a
silent DC error poisons every S-curve.
"""
from __future__ import annotations

import argparse
import logging

from spicexplorer_layout import em


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("touchstone")
    ap.add_argument("--name", default="em_net")
    ap.add_argument("--out", required=True)
    ap.add_argument("--poles", type=int, default=12)
    ap.add_argument("--dc-r", default="",
                    help='DC anchor: "1:2=0.8,3:4=1.2" port pairs (1-based) with ohms')
    ap.add_argument("--dc-from-data", action="store_true",
                    help="DC anchor from the data itself: the conductance graph "
                         "Re(Y) at the lowest kept frequency")
    a = ap.parse_args()

    dc_r = None
    if a.dc_r:
        dc_r = {}
        for term in a.dc_r.split(","):
            lhs, r = term.split("=")
            i, j = (int(x) for x in lhs.split(":"))
            dc_r[(i, j)] = float(r)
    out = em.em_to_subckt(a.touchstone, a.out, name=a.name, n_poles=a.poles,
                          dc_r=dc_r, dc_from_data=a.dc_from_data)
    print("wrote", out)


if __name__ == "__main__":
    main()
