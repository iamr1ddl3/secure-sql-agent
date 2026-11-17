"""CI regression gate: fail if execution accuracy drops by more than 2 points vs the committed baseline.

  python evals/gate.py            # compare reports/eval_latest.json with evals/baseline.json
  python evals/gate.py --update   # deliberately raise the baseline to the current numbers (commit the result)

Permission leaks are gated separately (reports/permission_leaks.json, zero tolerance) in the CI workflow.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "evals" / "baseline.json"
LATEST = ROOT / "reports" / "eval_latest.json"
TOLERANCE = 0.02  # 2 points; a drop of exactly 2 points passes


def check(current: dict, baseline: dict, tolerance: float = TOLERANCE) -> list[str]:
    """Return failure messages (empty = pass). Checks overall and per-group execution accuracy."""
    fails = []
    for key in ("execution_accuracy", "overall"):
        drop = (baseline.get(key) or 0) - (current.get(key) or 0)
        if drop > tolerance + 1e-9:
            fails.append(f"{key} fell {drop * 100:.1f} points ({baseline.get(key)} -> {current.get(key)})")
    return fails


def main() -> int:
    current = json.loads(LATEST.read_text())["summary"]
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps({k: current[k] for k in ("execution_accuracy", "overall", "per_group")}, indent=2) + "\n")
        print(f"baseline updated: {BASELINE.relative_to(ROOT)}")
        return 0
    if current.get("pipeline") == "stub":  # CI has no model key yet: nothing real to compare
        print("SKIPPED: report is from the stub pipeline (no OPENROUTER_API_KEY). Add the key to CI to enforce the gate.")
        return 0
    fails = check(current, json.loads(BASELINE.read_text()))
    print(f"execution_accuracy={current['execution_accuracy']} overall={current['overall']}")
    for f in fails:
        print("FAIL:", f)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
