"""The committed C++ cross-check vectors must match the current Python envelope."""
import io
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "vectors"))

import gen_envelope_vectors as gen  # noqa: E402


def test_vectors_up_to_date():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        gen.main()
    finally:
        sys.stdout = old
    committed = (ROOT / "tests" / "vectors" / "envelope_vectors.txt").read_text()
    assert buf.getvalue() == committed, "regenerate: PYTHONPATH=src python tests/vectors/gen_envelope_vectors.py > tests/vectors/envelope_vectors.txt"


def test_vectors_cover_every_reason_the_envelope_can_emit():
    text = (ROOT / "tests" / "vectors" / "envelope_vectors.txt").read_text()
    for reason in ["none", "fuel_delta_exceeded", "spark_delta_exceeded", "spark_limit", "afr_floor", "afr_ceiling",
                   "ve_limit", "rate_limited", "insufficient_samples", "stage_locked", "invalid_value", "off_table",
                   "wrong_engine", "stale_timestamp", "stale_basis", "learning_frozen"]:
        assert f" {reason} " in text, reason
