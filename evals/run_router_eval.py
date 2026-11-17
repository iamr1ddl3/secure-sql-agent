"""Compare question routers on the golden set: accuracy, p50/p95 latency, cost per 1,000 decisions. No database needed.

  python evals/run_router_eval.py            # golden set: rules + small LLM (the rules were written looking at it: optimistic)
  python evals/run_router_eval.py --heldout  # 40 unseen questions, the fair comparison

Gold label per item: ambiguous -> ambiguous; out_of_scope -> out_of_scope; attack (direct injection, SQL in question,
extraction) -> unsafe; everything else (answered, permission-boundary refusals, data-injection) -> answerable, because the
router only triages and the validator/database decide access. The input guard is NOT applied here: this scores the router alone.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent / "golden"))
sys.path.insert(0, str(ROOT / "scripts"))
from dotenv import load_dotenv  # noqa: E402
from seed import DEMO_STAFF  # noqa: E402
from verify import load_items  # noqa: E402

from secure_sql_agent.llm import LLM, LLMError, load_model_ids  # noqa: E402
from secure_sql_agent.pipeline import Usage  # noqa: E402
from secure_sql_agent.routers import LLMRouter, RulesRouter  # noqa: E402

ROLE = {k: role for k, role, *_ in DEMO_STAFF}


def gold(it: dict) -> str:
    if "label" in it:  # held-out items carry their label directly
        return it["label"]
    if it["group"] == "ambiguous":
        return "ambiguous"
    if it["group"] == "out_of_scope":
        return "out_of_scope"
    if it["group"] == "attack" and it.get("attack_type") != "data_injection":
        return "unsafe"
    return "answerable"


def evaluate(name: str, router, items: list[dict]) -> dict:
    lat, preds, errors, usage = [], [], 0, Usage()
    for it in items:
        t0 = time.perf_counter()
        try:
            label, _ = router.route(it["question"], ROLE[it["asked_by"]], usage)
        except LLMError:
            label, errors = "error", errors + 1
        lat.append((time.perf_counter() - t0) * 1000)
        preds.append(label)
    golds = [gold(i) for i in items]
    per = defaultdict(lambda: [0, 0])
    for g, p in zip(golds, preds):
        per[g][1] += 1
        per[g][0] += g == p
    lat.sort()
    return {"router": name, "n": len(items), "accuracy": round(sum(g == p for g, p in zip(golds, preds)) / len(items), 4),
            "recall_by_class": {k: round(a / n, 3) for k, (a, n) in sorted(per.items())}, "errors": errors,
            "latency_ms": {"p50": round(statistics.median(lat), 2), "p95": round(lat[int(0.95 * (len(lat) - 1))], 2)},
            "cost_per_1000_decisions_usd": round(1000 * usage.cost_usd / len(items), 4),
            "confusion": dict(Counter(f"{g}->{p}" for g, p in zip(golds, preds) if g != p))}


def main() -> int:
    load_dotenv(ROOT / ".env")
    heldout = "--heldout" in sys.argv
    if heldout:
        import yaml
        items = yaml.safe_load((ROOT / "evals" / "heldout" / "router.yaml").read_text())
    else:
        items = load_items([a for a in sys.argv[1:] if not a.startswith("--")])
    routers = {"rules": RulesRouter()}
    if os.environ.get("OPENROUTER_API_KEY"):
        cfg = load_model_ids(str(ROOT / "config/models.yaml"))
        routers["small_llm"] = LLMRouter(LLM(cfg["models"]["cheap"]["id"], os.environ["OPENROUTER_API_KEY"]))
    # ponytail: Jev goes here once access exists (task 15): routers["jev"] = JevRouter(...) with the same .route() signature.
    results = [evaluate(n, r, items) for n, r in routers.items()]
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports" / ("router_eval_heldout.json" if heldout else "router_eval.json")).write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
