#!/usr/bin/env python3
"""Touchstone N-port -> ngspice subcircuit via scikit-rf vector fitting.

    python3 em_to_subckt.py em.s13p --name em_outnet --out em_outnet.sub \
        [--poles 12] [--dc-r "1:2=0.8,3:4=1.2"]

Guards (both matter before splicing into a bias-carrying bench — see README):
  * passivity: `passivity_enforce` after the fit, and the result re-tested;
  * DC anchor: the benches push BIAS CURRENT through these nets, so the fit
    must be right at f=0, where FDTD data is weakest. --dc-r prepends an
    f=0 sample built from the given port-to-port DC resistances (ohms,
    from the metal sheet resistance of the traced net) before fitting.
The fitted model's .op currents must then be checked against the kpex deck
(em_compare.py does this); a silent DC error poisons every S-curve.
"""
from __future__ import annotations

import argparse

import numpy as np
import skrf
from skrf.vectorFitting import VectorFitting


def dc_sample(nw: skrf.Network, pairs: dict[tuple[int, int], float]) -> skrf.Network:
    """Prepend an f=0 point: Y-matrix of the given DC resistive graph
    (ports not named in any pair are DC-open)."""
    n = nw.nports
    z0 = nw.z0[0, 0].real
    g = np.zeros((n, n))
    for (i, j), r in pairs.items():
        gij = 1.0 / max(r, 1e-3)
        g[i, i] += gij
        g[j, j] += gij
        g[i, j] -= gij
        g[j, i] -= gij
    eye = np.eye(n)
    s0 = np.linalg.solve(eye + z0 * g, eye - z0 * g)
    f = np.concatenate([[1e3], nw.f])          # 1 kHz stands in for DC
    s = np.concatenate([s0[None, :, :], nw.s], axis=0)
    return skrf.Network(f=f, s=s, z0=z0, f_unit="hz")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("touchstone")
    ap.add_argument("--name", default="em_net")
    ap.add_argument("--out", required=True)
    ap.add_argument("--poles", type=int, default=12)
    ap.add_argument("--dc-r", default="",
                    help='DC anchor: "1:2=0.8,3:4=1.2" port pairs (1-based) with ohms')
    a = ap.parse_args()

    nw = skrf.Network(a.touchstone)
    if a.dc_r:
        pairs = {}
        for term in a.dc_r.split(","):
            lhs, r = term.split("=")
            i, j = (int(x) - 1 for x in lhs.split(":"))
            pairs[(i, j)] = float(r)
        nw = dc_sample(nw, pairs)

    vf = None
    for nr, ncx in ((2, a.poles), (1, a.poles), (2, a.poles + 2), (1, max(1, a.poles - 1))):
        cand = VectorFitting(nw)
        cand.vector_fit(n_poles_real=nr, n_poles_cmplx=ncx)
        if not cand.is_passive():
            try:
                cand.passivity_enforce()
            except Exception:
                continue
        if cand.is_passive():
            vf = cand
            print(f"vector fit: {nr} real + {ncx} cplx poles, passive, rms {cand.get_rms_error():.3e}")
            break
    assert vf is not None, "no passive fit at any tried pole count"
    vf.write_spice_subcircuit_s(a.out, fitted_model_name=a.name)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
