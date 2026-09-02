#!/usr/bin/env python3
"""Compare the openEMS output-network model against the kpex instrument.

    python3 em_compare.py --step lowfreq   # rung 2: wiring C, EM vs kpex
    python3 em_compare.py --step splice    # rung 3: build the spliced subckt
    python3 em_compare.py --step op        # DC operating point, spliced vs kpex
    python3 em_compare.py --step s22       # band-edge S22, spliced vs kpex

All steps run from layout/em/, expect target/ populated (extract_nets +
gen_ports + run_em outputs) and the repo venv for the ngspice benches.

Why the OP step is load-bearing: the benches push the BIAS current through
the very nets the EM subckt replaces. A vector-fitted S-model with a wrong
DC point silently shifts every operating point and every S-curve looks
plausible — so the spliced deck's .op is checked against the kpex deck
before any S-parameter from the splice is believed.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TGT = os.environ.get("PAM4_EM_TARGET") or os.path.join(HERE, "target")   # r4: target_r4/
sys.path.insert(0, os.path.join(HERE, "..", "..", "testbenches"))
sys.path.insert(0, os.path.join(HERE, ".."))

NETS = ("outp", "outn", "vcc")          # sub = reference
CELLS = ["M0", "M1", "L0"]


def load_ports():
    import yaml
    return yaml.safe_load(open(os.path.join(TGT, "ports.yaml")))["ports"]


# ---------------------------------------------------------------- lowfreq
def step_lowfreq(touchstone: str, f_ghz: float = 1.0) -> None:
    """Net-to-net wiring C: EM (same-net ports tied, Im(Y)/w at f_ghz) vs the
    kpex netlist's C sums for the same three nets. This isolates extractor
    error: same geometry, quasi-static vs full-wave."""
    import skrf
    ports = load_ports()
    nw = skrf.Network(touchstone)
    k = int(np.argmin(np.abs(nw.f - f_ghz * 1e9)))
    y = nw.y[k]
    n = nw.nports
    groups = {net: [p["num"] - 1 for p in ports if p["net"] == net] for net in NETS}
    a = np.zeros((len(NETS), n))
    for i, net in enumerate(NETS):
        a[i, groups[net]] = 1.0
    yn = a @ y @ a.T
    w = 2 * np.pi * nw.f[k]
    print(f"EM wiring C at {nw.f[k]/1e9:.1f} GHz (same-net ports tied, ref = sub):")
    em = {}
    for i, ni in enumerate(NETS):
        cg = yn[i].sum().imag / w
        em[(ni, "sub")] = cg * 1e15
        print(f"  C({ni:>4} - sub ) {cg*1e15:8.2f} fF")
        for j in range(i + 1, len(NETS)):
            c = -yn[i, j].imag / w
            em[(ni, NETS[j])] = c * 1e15
            print(f"  C({ni:>4} - {NETS[j]:<4}) {c*1e15:8.2f} fF")

    tot = {}
    SI = {"a": 1e-18, "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6}
    for line in open(os.path.join(TGT, "pam4drv_pam4_lay_pex_cc.sp")):
        if line[:1].upper() != "C":
            continue
        t = line.split()
        pair = tuple(sorted(x.lower() for x in t[1:3]))
        mm = re.match(r"([-\d.eE+]+)([afpnum]?)", t[3])
        v = float(mm.group(1)) * SI.get(mm.group(2), 1)
        tot[pair] = tot.get(pair, 0.0) + v
    print("kpex wiring C (all nets of the cut):")
    for pair, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if any(n in pair for n in NETS) and v > 0.2e-15:
            print(f"  C({pair[0]:>5} - {pair[1]:<5}) {v*1e15:8.2f} fF")


# ---------------------------------------------------------------- splice
def splice_subckt(em_sub: str, out_path: str) -> str:
    """Rebuild the DUT subckt with per-tap collector/R_C nodes wired through
    the EM N-port; devices and input nets stay the ideal LVS netlist."""
    ports = load_ports()
    lvs = open(os.path.join(TGT, "pam4drv_pam4_lay_lvs.sp")).read().splitlines()
    node_of = {}
    for p in ports:
        if p["role"] == "edge":
            node_of[p["num"]] = {"outp": "outp", "outn": "outn", "vcc": "vcc"}[p["net"]]
        elif p["role"] == "coll_tap":
            node_of[p["num"]] = f'{p["net"]}_t{p["cell"]}'
        elif p["role"] == "rc_tap":
            node_of[p["num"]] = f'{p["net"]}_trc'
        elif p["role"] == "rc_vcc_tap":
            node_of[p["num"]] = f'vcc_trc{len([q for q in ports if q["num"] < p["num"] and q["role"] == "rc_vcc_tap"])}'
    def sim_card(t):
        """LVS device card -> simulation X-card on the PDK subckt models
        (npn13G2 / rsil / cap_cmim are .subckt, not .model, in SG13G2 —
        same target forms as pex_sim.convert_pex_netlist)."""
        low = " ".join(t).lower()
        kv = {k.lower(): v for k, v in
              (x.split("=", 1) for x in t if "=" in x)}
        if t[0].startswith("Q") and "npn13g2" in low:
            nx = int(float(kv.get("m", 1)))
            return f"X{t[0][1:]} {' '.join(t[1:5])} npn13G2 Nx={nx}"
        if t[0].startswith("R") and "rsil" in low:
            return (f"X{t[0][1:]} {t[1]} {t[2]} sub rsil "
                    f"w={kv['w']} l={kv['l']} m={kv.get('m', '1')}")
        if t[0].startswith("C") and "cap_cmim" in low:
            return f"X{t[0][1:]} {t[1]} {t[2]} cap_cmim w={kv['w']} l={kv['l']}"
        return None

    out = []
    rc_seen = 0
    for line in lvs:
        t = line.split()
        if t and t[0].startswith("QQ") and t[0][2] in "34":
            # cascode: QQ3<cell> collector outp, QQ4<cell> collector outn
            cell = t[0][3:]
            net = "outp" if t[0][2] == "3" else "outn"
            assert t[1] == net, line
            t[1] = f"{net}_t{cell}"
            out.append(sim_card(t))
        elif t and t[0].startswith("RR") and ("outp" in t[1:3] or "outn" in t[1:3]) and "vcc" in t[1:3]:
            # collector load resistor between out net and vcc rail
            net = t[1] if t[1] in ("outp", "outn") else t[2]
            i, j = (1, 2) if t[1] == net else (2, 1)
            t[i] = f"{net}_trc"
            t[j] = f"vcc_trc{rc_seen}"
            rc_seen += 1
            out.append(sim_card(t))
        elif t and sim_card(t):
            out.append(sim_card(t))
        else:
            out.append(line)
    assert rc_seen == 2, f"expected 2 R_C devices, spliced {rc_seen}"
    # EM N-port instance: node per port + per-port reference pins tied to sub
    em_name = None
    for l in open(em_sub):
        if l.lower().startswith(".subckt"):
            em_name = l.split()[1]
            break
    n_ports = len(ports)
    pins = []
    for p in sorted(ports, key=lambda q: q["num"]):
        pins += [node_of[p["num"]], "sub"]      # create_reference_pins=True order: p1 r1 p2 r2 ...
    xline = f"XEM {' '.join(pins)} {em_name}"
    ins = next(i for i, l in enumerate(out) if l.upper().startswith(".ENDS"))
    out.insert(ins, xline)
    out.insert(0, f'.include {os.path.abspath(em_sub)}')
    with open(out_path, "w") as f:
        f.write("\n".join(out) + "\n")
    print("wrote", out_path)
    return out_path


# ---------------------------------------------------------------- op / s22
def _dut_refs():
    import pex_sim
    kpex_ref = pex_sim.wrap_layout_dut("pam4", os.path.join(TGT, "dut_pam4_post.spice"))
    em_ref = pex_sim.wrap_layout_dut("pam4", os.path.join(TGT, "dut_pam4_em.spice"))
    return kpex_ref, em_ref


def _dp():
    import json
    import driver_lib as dl
    s = __import__("json").load(open(os.path.join(TGT, "summary.json")))
    cp = dl.CellParams(nx=int(s["params"]["nx"]), re_ohm=s["params"]["re_ohm"],
                       cdeg_ff=s["params"]["cdeg_ff"], rc_ohm=s["params"]["rc_ohm"],
                       rb_ohm=s["params"]["rb_ohm"], tail_ma=s["deck_params"]["tail_ma"],
                       vcasc=s["deck_params"]["vcasc"])
    return dl.DriverParams(vcc=4.0, cell=cp)


def step_op() -> None:
    import driver_lib as dl
    dp = _dp()
    kref, eref = _dut_refs()
    for tag, ref in (("kpex", kref), ("EM-spliced", eref)):
        deck, hold0, _ = dl.tb_bias("pam4", ref, dp=dp, probes=["v(outp)", "i(Vcc)"])
        out, log = dl.run_deck(deck, ["bias.csv"], timeout_s=600)
        d = out["bias.csv"]
        icc = float(np.mean(np.abs(d[d[:, 0] >= hold0 * 1e-9, 3])))
        print(f"{tag:>11}: Icc {icc*1e3:.3f} mA  power {icc*4*1e3:.1f} mW")


def step_s22() -> None:
    import driver_lib as dl
    sys.path.insert(0, os.path.join(HERE, "..", "codesign"))
    import measure_post
    dp = _dp()
    kref, eref = _dut_refs()
    for tag, ref in (("kpex", kref), ("EM-spliced", eref)):
        r = dl.run_ac_s22("pam4", dp=dp, dut_ref=ref, pts_per_dec=100, timeout_s=900)
        s22 = measure_post._band_max(r["f_ghz"], r["s22_db"], 50.0)
        edge = measure_post._edge(r["f_ghz"], r["s22_db"])
        print(f"{tag:>11}: S22 {s22:.3f} dB (worst <= 50 GHz), -10 dB holds to {edge:.2f} GHz")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True, choices=["lowfreq", "splice", "op", "s22"])
    ap.add_argument("--touchstone", default=os.path.join(TGT, "em_out", "em_outnet.s13p"))
    ap.add_argument("--em-sub", default=os.path.join(TGT, "em_outnet.sub"))
    a = ap.parse_args()
    if a.step == "lowfreq":
        step_lowfreq(a.touchstone)
    elif a.step == "splice":
        splice_subckt(a.em_sub, os.path.join(TGT, "dut_pam4_em.spice"))
    elif a.step == "op":
        step_op()
    elif a.step == "s22":
        step_s22()


if __name__ == "__main__":
    main()
