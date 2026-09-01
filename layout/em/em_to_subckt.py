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


F_DC = 1e6  # DC stand-in (Hz): well below the first real FDTD point, but
            # close enough in log-f that the fit stays well-conditioned


def dc_sample(nw: skrf.Network, pairs: dict[tuple[int, int], float]) -> skrf.Network:
    """Replace the (energy-starved) f→0 FDTD points with an f=F_DC sample:
    Y-matrix of the given DC resistive graph (ports in no pair are DC-open).
    The Gauss excitation has ~no DC content, so raw points below F_DC are
    numerically meaningless and are dropped."""
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
    keep = nw.f > F_DC
    f = np.concatenate([[F_DC], nw.f[keep]])
    s = np.concatenate([s0[None, :, :], nw.s[keep]], axis=0)
    return skrf.Network(f=f, s=s, z0=z0, f_unit="hz")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("touchstone")
    ap.add_argument("--name", default="em_net")
    ap.add_argument("--out", required=True)
    ap.add_argument("--poles", type=int, default=12)
    ap.add_argument("--dc-r", default="",
                    help='DC anchor: "1:2=0.8,3:4=1.2" port pairs (1-based) with ohms')
    ap.add_argument("--dc-from-data", action="store_true",
                    help="DC anchor from the data itself: the conductance graph "
                         "Re(Y) at the lowest kept frequency (valid once the EM "
                         "cut has a common ground plane, so its low-f limit IS "
                         "resistive; em_compare --step op stays the real gate)")
    a = ap.parse_args()

    nw = skrf.Network(a.touchstone)
    # FDTD numerical noise leaves ~1e-4 passivity violations scattered over
    # the band; renormalize those points onto the unit sphere so the fit
    # starts from passive data (passivity_enforce cannot always absorb them)
    sv = np.linalg.svd(nw.s, compute_uv=False).max(axis=1)
    hot = sv > 1.0
    if hot.any():
        nw.s[hot] *= (1.0 / sv[hot])[:, None, None]
        print(f"renormalized {hot.sum()}/{len(sv)} non-passive points "
              f"(worst sv {sv.max():.6f})")
    if a.dc_from_data:
        keep = nw.f > F_DC
        k = int(np.argmax(keep))
        g = nw.y[k].real                    # conductance graph at f_min
        eye = np.eye(nw.nports)
        z0 = nw.z0[0, 0].real
        s0 = np.linalg.solve(eye + z0 * g, eye - z0 * g)
        f = np.concatenate([[F_DC], nw.f[keep]])
        s = np.concatenate([s0[None], nw.s[keep]], axis=0)
        nw = skrf.Network(f=f, s=s, z0=z0, f_unit="hz")
        print(f"DC anchor from Re(Y) at {nw.f[1]/1e9:.2f} GHz")
    elif a.dc_r:
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
        rms = cand.get_rms_error()
        if not cand.is_passive():
            try:
                cand.passivity_enforce()
            except Exception as e:
                print(f"  ({nr},{ncx}): rms {rms:.3e}, enforce failed: {e}")
                continue
        if cand.is_passive():
            vf = cand
            print(f"vector fit: {nr} real + {ncx} cplx poles, passive, rms {cand.get_rms_error():.3e}")
            break
        print(f"  ({nr},{ncx}): rms {rms:.3e}, still non-passive after enforce")
    assert vf is not None, "no passive fit at any tried pole count"
    vf.write_spice_subcircuit_s(a.out, fitted_model_name=a.name)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
