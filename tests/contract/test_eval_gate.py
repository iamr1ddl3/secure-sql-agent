import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "evals"))
from gate import check  # noqa: E402

BASE = {"execution_accuracy": 0.80, "overall": 0.70}


def test_small_or_exact_two_point_drop_passes():
    assert check({"execution_accuracy": 0.78, "overall": 0.68}, BASE) == []


def test_more_than_two_points_fails():
    assert len(check({"execution_accuracy": 0.77, "overall": 0.70}, BASE)) == 1


def test_improvement_and_both_metrics():
    assert check({"execution_accuracy": 0.9, "overall": 0.9}, BASE) == []
    assert len(check({"execution_accuracy": 0.5, "overall": 0.4}, BASE)) == 2
