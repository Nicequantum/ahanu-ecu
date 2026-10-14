import copy
import gzip
import json
import threading
import urllib.request

import pytest

from grok_pilot.ingest import Store
from grok_pilot.ingest.cli import main as cli_main, parse_time
from grok_pilot.ingest.http import serve
from grok_pilot.synth import T0_US, generate


@pytest.fixture(scope="module")
def recs():
    return list(generate(seed=2, max_samples=2000))


@pytest.fixture
def st(recs):
    s = Store()
    s.ingest_records(recs, source="synthetic")
    return s


def sample(recs, engine=0, i=0):
    return copy.deepcopy([r for r in recs if r["record_type"] == "sample" and r["engine_id"] == engine][i])


def test_ingest_counts(recs):
    s = Store()
    rep = s.ingest_records(recs)
    assert rep.read == len(recs) and rep.inserted == len(recs) and rep.quarantined == 0
    assert rep.by_type["sample"] == 4000
    assert s.time_range()["samples"] == 4000


def test_reimport_is_idempotent(recs, st):
    rep = st.ingest_records(recs)
    assert rep.inserted == 0 and rep.duplicates == len(recs) and rep.quarantined == 0
    assert st.time_range()["samples"] == 4000


def test_conflicting_duplicate_quarantined_original_kept(recs, st):
    r = sample(recs)
    orig_rpm = r["rpm"]
    r["rpm"] = orig_rpm + 1000
    rep = st.ingest_records([r])
    assert rep.quarantined == 1 and rep.quarantine_reasons == {"duplicate_conflict": 1}
    assert st.state_at(0, r["timestamp_us"])["rpm"] == orig_rpm


def test_key_unique_across_record_types(recs, st):
    ev = copy.deepcopy(next(x for x in recs if x["record_type"] == "event"))
    s = sample(recs, engine=ev["engine_id"])
    for k in ("boot_id", "seq"):
        s[k] = ev[k]
    rep = st.ingest_records([s])
    assert rep.quarantine_reasons == {"duplicate_conflict": 1}


@pytest.mark.parametrize("mut,frag", [
    (lambda r: r.update(rpm=-5), "rpm"), (lambda r: r.update(engine_id=3), "engine_id"),
    (lambda r: r.pop("afr_target"), "missing"), (lambda r: r.update(map_kpa=float("nan")), "non-finite"),
    (lambda r: r.update(record_type="bogus"), "record_type"), (lambda r: r.update(schema_version="9.9"), "schema_version")])
def test_invalid_records_quarantined(recs, mut, frag):
    s = Store()
    r = sample(recs, i=5)
    r["seq"] = 10**9
    mut(r)
    rep = s.ingest_records([r])
    assert rep.inserted == 0 and rep.quarantine_reasons == {"schema_invalid": 1}
    q = s.quarantine()
    assert len(q) == 1 and frag in q[0]["errors"] and q[0]["raw"]


def test_file_import_jsonl_gz_with_bad_lines(recs, tmp_path):
    p = tmp_path / "e0_b1_1.jsonl.gz"
    good = [r for r in recs if r["engine_id"] == 0][:100]
    with gzip.open(p, "wt", encoding="utf-8") as f:
        f.write("# header comment\n\n")
        for r in good:
            f.write(json.dumps(r) + "\n")
        f.write("{not json\n")
        f.write("[1,2,3]\n")
        f.write('{"rpm": NaN}\n')
    s = Store(str(tmp_path / "s.db"))
    rep = s.ingest_file(str(p))
    assert rep.inserted == 100
    assert rep.quarantine_reasons == {"parse_error": 2, "schema_invalid": 1}
    assert {q["line_no"] for q in s.quarantine()} == {103, 104, 105}
    assert s.db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_v01_records_ingest(recs):
    s = Store()
    rep = s.ingest_records(list(generate(seed=2, max_samples=300, version="0.1")))
    # Known generator quirk: in v0.1 mode synth still emits the v0.2-only 'status_change' event,
    # which v0.1 validation rejects -> those land in quarantine (exactly what quarantine is for).
    assert rep.by_type["sample"] == 600
    bad = s.quarantine()
    assert all("status_change" in q["errors"] for q in bad)


def test_query_window_half_open_edges(recs, st):
    e0 = sorted(r["timestamp_us"] for r in recs if r["record_type"] == "sample" and r["engine_id"] == 0)
    a, b = e0[10], e0[20]
    rows = st.query_samples(0, a, b, ["rpm"])
    assert [r["timestamp_us"] for r in rows] == e0[10:20]       # includes start, excludes end
    assert st.query_samples(0, a, a, ["rpm"]) == []              # empty window
    assert len(st.query_samples(0, a, a + 1, ["rpm"])) == 1      # single-µs window
    assert st.query_samples(0, e0[-1] + 1, e0[-1] + 10**9) == []  # after data
    with pytest.raises(ValueError):
        st.query_samples(0, b, a)


def test_query_matches_source_values(recs, st):
    src = {r["timestamp_us"]: r for r in recs if r["record_type"] == "sample" and r["engine_id"] == 1}
    rows = st.query_samples(1, T0_US, T0_US + 10**12, ["rpm", "afr_a", "inj_pw_us", "status", "oil_alarm"])
    assert len(rows) == len(src)
    for r in rows[::97]:
        s = src[r["timestamp_us"]]
        assert r["rpm"] == s["rpm"] and r["afr_a"] == s["afr_a"] and r["inj_pw_us"] == s["inj_pw_us"]
        assert r["status"] == s["status"] and r["oil_alarm"] == int(s["oil_alarm"])


def test_query_both_engines_and_field_validation(st):
    rows = st.query_samples(None, T0_US, T0_US + 10**7, ["rpm"])
    assert {r["engine_id"] for r in rows} == {0, 1}
    with pytest.raises(ValueError):
        st.query_samples(0, 0, 1, ["rpm; DROP TABLE samples"])


def test_bucketed_downsampling(recs, st):
    start = T0_US
    end = T0_US + 10_000_000
    rows = st.query_samples(0, start, end, ["rpm", "coolant_c"], bucket_s=2.0)
    raw = st.query_samples(0, start, end, ["rpm"])
    assert sum(r["n"] for r in rows) == len(raw)
    assert [r["bucket_start_us"] for r in rows] == [start + k * 2_000_000 for k in range(5)]
    first = [x["rpm"] for x in raw if x["timestamp_us"] < start + 2_000_000]
    assert rows[0]["rpm"] == pytest.approx(sum(first) / len(first))
    mx = st.query_samples(0, start, end, ["rpm"], bucket_s=2.0, agg="max")
    assert mx[0]["rpm"] == max(first)


def test_state_at(recs, st):
    e0 = sorted((r for r in recs if r["record_type"] == "sample" and r["engine_id"] == 0), key=lambda r: r["timestamp_us"])
    assert st.state_at(0, e0[0]["timestamp_us"] - 1) is None
    assert st.state_at(0, e0[5]["timestamp_us"])["seq"] == e0[5]["seq"]
    assert st.state_at(0, e0[5]["timestamp_us"] + 1)["seq"] == e0[5]["seq"]


def test_cell_writes_events_dashboard(st):
    cw = st.query_cell_writes(None, 0, 2**62)
    assert cw and all("decision" in c for c in cw)
    rej = st.query_cell_writes(None, 0, 2**62, decision="rejected")
    assert all(c["decision"] == "rejected" for c in rej)
    ev = st.query_events(None, 0, 2**62, event="stage_transition")
    assert ev and all(e["event"] == "stage_transition" for e in ev)
    d = st.dashboard()
    assert d["stages"] and {s["engine_id"] for s in d["stages"]} == {0, 1}


def test_cli_roundtrip(tmp_path, capsys):
    db = str(tmp_path / "c.db")
    cli_main(["import-synthetic", "--db", db, "--samples", "300"])
    out = json.loads(capsys.readouterr().out)
    assert out["inserted"] > 600
    cli_main(["query", "--db", db, "--engine", "0", "--start", str(T0_US), "--end", str(T0_US + 5_000_000), "--fields", "rpm"])
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 49  # samples at +0.1 s .. +4.9 s


def test_parse_time():
    assert parse_time("1791000000000000") == 1791000000000000
    assert parse_time("2026-10-14T00:00:00Z") == parse_time("2026-10-13T20:00:00-04:00")
    with pytest.raises(ValueError):
        parse_time("2026-10-14T00:00:00")


def test_http_endpoint(tmp_path, recs):
    db = str(tmp_path / "h.db")
    Store(db).ingest_records(recs)
    srv = serve(db, port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        rows = json.load(urllib.request.urlopen(f"{base}/samples?engine=0&start_us={T0_US}&end_us={T0_US + 2_000_000}&fields=rpm"))
        assert len(rows) == 19
        b = json.load(urllib.request.urlopen(f"{base}/samples?engine=1&start_us={T0_US}&end_us={T0_US + 10_000_000}&fields=rpm&bucket_s=5"))
        assert len(b) == 2
        assert json.load(urllib.request.urlopen(f"{base}/range"))["samples"] == 4000
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(f"{base}/samples?engine=0&start_us=10&end_us=1")
        assert e.value.code == 400
    finally:
        srv.shutdown()
