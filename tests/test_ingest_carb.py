import sqlite3

from grok_pilot.ingest import Store
from test_schema_v03 import BASE, EVAL


def test_jet_change_ingest_query_and_idempotency(tmp_path):
    st = Store(str(tmp_path / "j.db"))
    rep = st.ingest_records([BASE, EVAL])
    assert rep.inserted == 2 and rep.by_type == {"jet_change": 2}
    assert st.ingest_records([BASE, EVAL]).duplicates == 2
    rows = st.query_jet_changes(0, 0, 2**63 - 1, proposal_id=1)
    assert [r["phase"] for r in rows] == ["proposed", "evaluated"] and rows[1]["moved_toward_target"] is True
    assert st.query_jet_changes(0, EVAL["timestamp_us"], EVAL["timestamp_us"]) == []  # half-open
    d = st.dashboard(0, 2**62)  # default window follows samples; none here
    assert {(j["phase"], j["n"]) for j in d["jet_changes"]} == {("proposed", 1), ("evaluated", 1)}
    assert st.db.execute("SELECT value FROM meta WHERE key='store_schema_version'").fetchone()[0] == "2"


def test_invalid_jet_change_quarantined():
    st = Store()
    rep = st.ingest_records([{**BASE, "jet_proposed": 0.5}, {**EVAL, "afr_delta": 3.0, "seq": 300}])
    assert rep.inserted == 0 and rep.quarantine_reasons == {"schema_invalid": 2}


def test_v1_store_upgrades_in_place(tmp_path):
    p = str(tmp_path / "old.db")
    db = sqlite3.connect(p)
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("INSERT INTO meta VALUES ('store_schema_version','1')")
    db.commit()
    db.close()
    st = Store(p)
    assert st.db.execute("SELECT value FROM meta WHERE key='store_schema_version'").fetchone()[0] == "2"
    assert st.ingest_records([BASE]).inserted == 1
