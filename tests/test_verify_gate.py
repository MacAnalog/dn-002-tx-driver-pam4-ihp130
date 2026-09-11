"""verification/verify.py must fail loudly when it verifies nothing.

The three holes these tests pin down (all of them make a broken run look like a
clean one, which is the worst failure mode a verification script has):

1. the return code of every `ngspice -b` was printed and then dropped — and the
   deck CSVs are TRACKED files, so a run in which every deck failed re-scores the
   previous run's numbers and reports "all reproduce";
2. `if key in got and key in exp` skipped a number that the run failed to
   produce, so a measurement that vanished was not a FAIL, it was nothing;
3. `SystemExit(0 if n_ok == n else 1)` exits 0 when n == 0 — "0/0 numbers
   reproduce" is a green run that verified nothing;
4. a deck that failed still lent its numbers to the run: the deck's own row
   FAILED, but the numbers extracted from the CSV it did NOT write this run were
   still printed `PASS <metric> got X expected X` and recorded ok:true in
   last_run.json — the per-row record asserted a reproduction that never
   happened. Those rows must read STALE and fail, and ONLY the rows whose deck
   failed (a failed s22 deck must not invalidate lsb_gain).

Plus a coverage guard: every key of expected.json is accounted for by the
manifest in verify.py, so a number of the record cannot be added and then be
silently checked by nothing.

No simulator, no PDK: `ngspice` is a stub script on PATH.
"""
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERIFICATION = os.path.join(ROOT, "verification")
sys.path.insert(0, VERIFICATION)

# the numbers step_sim compares, in the order it compares them
CHECKED = ("lsb_gain", "msb_gain", "weight", "bw_lsb", "bw_msb", "bw", "s11_lsb", "s11_msb", "s11",
           "s11_edge_ghz", "s22", "s22_edge_ghz", "pn_gain_imb_db", "pn_phase_imb_deg", "cm_leak_dbc",
           "cm_dm_db", "swing", "power", "ic_ma_per_finger")


@pytest.fixture()
def verify(monkeypatch):
    import verify as v

    monkeypatch.setattr(v, "RESULTS", [])
    return v


def _stub_ngspice(tmp_path, monkeypatch, rc, fail_decks=()):
    """put an `ngspice` on PATH that does nothing and exits with `rc`

    fail_decks: deck file names (`ngspice -b <name>`) that exit 1 instead, so a
    test can fail one deck out of ten and check that only ITS numbers go stale.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "ngspice"
    cases = "".join(f'  {d}) exit 1 ;;\n' for d in fail_decks)
    exe.write_text(f"#!/bin/sh\ncase \"$2\" in\n{cases}esac\nexit {rc}\n")
    exe.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("PDK_ROOT", str(tmp_path / "pdk"))


def _deck_dir(tmp_path, monkeypatch, verify, tier="a", with_csvs=False, with_eye=False):
    d = tmp_path / "decks" / tier
    d.mkdir(parents=True)
    if with_csvs:                       # the previous run's output, as a fresh clone has it
        for f in os.listdir(os.path.join(VERIFICATION, "decks", tier)):
            if (f.endswith(".csv") and (with_eye or not f.startswith("eye"))) or f == "meta.json":
                shutil.copy(os.path.join(VERIFICATION, "decks", tier, f), d / f)
    monkeypatch.setattr(verify, "DECKS", str(tmp_path / "decks"))
    return d


def test_failed_deck_cannot_report_all_pass(tmp_path, monkeypatch, verify):
    """every deck fails to run, the CSVs on disk are the previous run's -> must NOT be all-pass"""
    _stub_ngspice(tmp_path, monkeypatch, rc=1)
    _deck_dir(tmp_path, monkeypatch, verify, with_csvs=True)

    verify.step_sim("a", no_eye=True)

    assert verify.RESULTS, "a run of ten failing decks recorded no result at all"
    deck_rows = {r[1]: r for r in verify.RESULTS if r[1].startswith("ngspice ")}
    assert deck_rows, "the ngspice runs themselves were not recorded as checks"
    assert all(r[3] == "FAILED" and not r[5] for r in deck_rows.values()), (
        f"a deck whose ngspice exited 1 was not recorded as FAILED: "
        f"{[(k, v[3], v[5]) for k, v in deck_rows.items() if v[5]]}")


def test_numbers_of_a_failed_deck_are_reported_stale_not_reproduced(tmp_path, monkeypatch, verify):
    """THE defect: with every deck failed, the numbers extracted from the PREVIOUS run's
    committed CSVs were printed `PASS lsb_gain got 3.09 expected 3.09` and written to
    last_run.json with ok:true. A number this run never simulated is not a reproduction."""
    _stub_ngspice(tmp_path, monkeypatch, rc=1)
    _deck_dir(tmp_path, monkeypatch, verify, with_csvs=True)

    verify.step_sim("a", no_eye=True)

    rows = {r[1]: r for r in verify.RESULTS}
    exp = verify.EXPECTED["tiers"]["a"]
    stale = getattr(verify, "STALE", "STALE")     # value assertions first: no mechanism needed to fail
    for key in ("lsb_gain", "msb_gain", "weight", "s22", "swing", "power"):
        assert key in rows, f"{key} is on record but the run produced no line for it"
        got, ok = rows[key][3], rows[key][5]
        assert not ok, (
            f"{key} got {got!r} scored as reproducing {exp[key]} on a run in which every deck failed "
            f"— that number came out of the PREVIOUS run's committed CSV")
        assert not isinstance(got, (int, float)), (
            f"{key}: the run reported the number {got!r} it never simulated (stale CSV re-scored)")
        assert got == stale, f"{key}: a number whose deck failed should read STALE, got {got!r}"
    scored = [r for r in verify.RESULTS if not r[1].startswith("ngspice ")]
    assert scored and not any(r[5] for r in scored), (
        f"numbers still passed on a run in which every deck failed: {[r[1] for r in scored if r[5]]}")


def test_only_the_numbers_of_the_failed_deck_go_stale(tmp_path, monkeypatch, verify):
    """the converse: one broken deck must not invalidate the nine that ran. s22.spice fails,
    so s22 / s22_edge_ghz are STALE — and lsb_gain, which comes from ac_lsb.csv, still passes."""
    _stub_ngspice(tmp_path, monkeypatch, rc=0, fail_decks=("s22.spice",))
    _deck_dir(tmp_path, monkeypatch, verify, with_csvs=True)

    verify.step_sim("a", no_eye=True)

    rows = {r[1]: r for r in verify.RESULTS}
    stale = getattr(verify, "STALE", "STALE")
    for key in ("s22", "s22_edge_ghz"):
        got, ok = rows[key][3], rows[key][5]
        assert not ok, f"{key} came from the failed s22 deck's stale CSV yet reported got {got!r} as reproducing"
        assert got == stale, f"{key} should read STALE, got {got!r}"
    for key in ("lsb_gain", "msb_gain", "swing", "power"):
        assert rows[key][5], f"{key} should still reproduce when only the s22 deck failed"
        assert rows[key][3] != stale, f"{key}'s deck ran fine; marking it stale fails the whole run for nothing"
    assert not rows["ngspice s22"][5] and rows["ngspice ac_lsb"][5]


def test_eye_levels_of_the_record_are_checked(tmp_path, monkeypatch, verify):
    """eye_levels_v is on record for every tier and was checked by no step at all —
    a simulated number of the record that verify.py passed over in silence."""
    _stub_ngspice(tmp_path, monkeypatch, rc=0)
    _deck_dir(tmp_path, monkeypatch, verify, with_csvs=True, with_eye=True)

    verify.step_sim("a", no_eye=False)

    rows = {r[1]: r for r in verify.RESULTS}
    assert "eye_levels_v" in rows, "eye_levels_v is a number of the record that no check ever looked at"
    assert rows["eye_levels_v"][5], f"eye_levels_v did not reproduce: {rows['eye_levels_v']}"


def test_extract_cli_takes_every_tier_of_the_record(monkeypatch, verify, capsys):
    """extract.py's tier choices were hard-coded "abcd", so the CLI rejected tier f —
    the layout of record, which has decks of its own and is what the README tells a
    reviewer to run by hand."""
    import extract

    for tier in verify.EXPECTED["tiers"]:
        monkeypatch.setattr(sys, "argv",
                            ["extract.py", tier, "--json", "--dir", os.path.join(VERIFICATION, "decks", tier)])
        try:
            extract.main()
        except SystemExit as e:                      # argparse: exit 2 with "invalid choice"
            pytest.fail(f"extract.py rejects tier {tier}, which is on record: {e}")
        capsys.readouterr()


def test_coverage_manifest_accounts_for_every_key_of_the_record(tmp_path, monkeypatch, verify):
    """forward guard: a key added to expected.json must be checked by a step or listed as
    unverified — it may not become a number of the record that nothing looks at."""
    known = set(verify.SIM_KEYS) | set(verify.SIM_LIST_KEYS) | set(verify.LAYOUT_KEYS) \
        | set(verify.LABEL_KEYS) | set(verify.UNVERIFIED_KEYS)
    for tier, exp in verify.EXPECTED["tiers"].items():
        unaccounted = set(exp) - known
        assert not unaccounted, (
            f"tier {tier}: {sorted(unaccounted)} on record but in no coverage list of verify.py "
            f"— add them to a *_KEYS tuple (checked) or to UNVERIFIED_KEYS (documented gap)")


def test_missing_number_is_a_failure(tmp_path, monkeypatch, verify):
    """a number the run did not produce must be a FAIL, not a silent skip"""
    _stub_ngspice(tmp_path, monkeypatch, rc=0)
    _deck_dir(tmp_path, monkeypatch, verify)
    exp = verify.EXPECTED["tiers"]["a"]
    got = {k: exp[k] for k in CHECKED if k in exp and k != "msb_gain"}   # msb_gain went missing
    monkeypatch.setattr(verify.extract, "extract", lambda *a, **k: dict(got))

    verify.step_sim("a", no_eye=True)

    rows = {r[1]: r for r in verify.RESULTS}
    assert "msb_gain" in rows, "an expected number absent from the run produced no line at all"
    assert not rows["msb_gain"][5], "a number the run never produced was reported as reproducing"


def test_eye_numbers_are_not_scored_when_the_eye_deck_is_skipped(tmp_path, monkeypatch, verify):
    """--no-eye skips the eye decks, so the eye CSV on disk belongs to the PREVIOUS run:
    extraction still yields eye numbers, and reporting them as reproduced is a false claim"""
    _stub_ngspice(tmp_path, monkeypatch, rc=0)
    _deck_dir(tmp_path, monkeypatch, verify)
    exp = verify.EXPECTED["tiers"]["a"]
    got = {k: exp[k] for k in CHECKED if k in exp}
    got.update({k: exp[k] for k in ("eye_rlm", "eye_min_v", "eye_vpp", "eye_openings_v")})   # stale eye.csv
    monkeypatch.setattr(verify.extract, "extract", lambda *a, **k: dict(got))

    verify.step_sim("a", no_eye=True)

    assert not [r for r in verify.RESULTS if r[1].startswith("eye")], \
        "--no-eye reported eye numbers that this run never simulated"


def test_zero_checks_exits_non_zero(tmp_path, monkeypatch, verify):
    """tier a has no layout/regen step: no check runs, and that is not a pass"""
    monkeypatch.setattr(verify, "HERE", str(tmp_path))            # last_run.json
    monkeypatch.setattr(sys, "argv", ["verify.py", "--tier", "a", "--step", "layout,regen"])
    (tmp_path / "last_run.json").write_text("[1]")             # the record of a real run

    with pytest.raises(SystemExit) as e:
        verify.main()

    assert e.value.code == 2, f"0/0 numbers reproduce should be exit 2, got {e.value.code!r}"
    assert (tmp_path / "last_run.json").read_text() == "[1]", (
        "a run that verified nothing must not clobber the committed record")


def test_unknown_step_exits_non_zero(tmp_path, monkeypatch, verify):
    """a mistyped --step silently ran nothing and exited 0"""
    monkeypatch.setattr(verify, "HERE", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["verify.py", "--tier", "a", "--step", "nostep"])

    with pytest.raises(SystemExit) as e:
        verify.main()

    assert e.value.code == 2, (
        f"an unknown --step verified nothing; the documented code for that is 2, got {e.value.code!r}")
    assert not os.path.exists(tmp_path / "last_run.json"), (
        "no run happened for an unusable --step, so it must not leave a run record")
