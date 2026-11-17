"""Run the golden set through the service and report the stage-1 numbers.

  python evals/run_eval.py             # everything
  python evals/run_eval.py st am       # only ids starting with these prefixes

Calls QueryService.handle in-process with HS256 tokens minted for the demo identities, so the real
identity check runs. Expected rows come from the golden set's reference SQL (see golden/verify.py).
Writes reports/eval_latest.json (+ a timestamped copy). Reports numbers only: the CI gate is separate.
If a response carries `usage.cost_usd` (the pipeline will add it), cost per 1,000 queries is reported.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import jwt

sys.path.insert(0, str(Path(__file__).parent / "golden"))
from score import score, summarize  # noqa: E402
from verify import KEY_ID, ROOT, connections, load_items, reference_rows  # noqa: E402

from secure_sql_agent.contracts import QueryRequest  # noqa: E402
from secure_sql_agent.identity import IdentityVerifier  # noqa: E402
from secure_sql_agent.service import QueryService  # noqa: E402
from seed import demo_user_id  # noqa: E402

ISS, SECRET = "https://eval.local/auth/v1", "eval-secret-" + "x" * 40  # local only; never a real project's key


def token(asked_by: str) -> str:
    claims = {"sub": str(demo_user_id(asked_by)), "aud": "authenticated", "iss": ISS, "role": "authenticated",
              "exp": int(time.time()) + 300}
    return jwt.encode(claims, SECRET, algorithm="HS256")


def main() -> int:
    args = sys.argv[1:]
    guards = "--guards-off" not in args  # ablation: input guard + scope guard + router off (validator and DB stay on)
    items = load_items([a for a in args if not a.startswith("--")])
    results, latencies, costs = [], [], []
    with connections() as (admin, agent, secret):
        live = bool(os.environ.get("OPENROUTER_API_KEY"))
        if live:  # real pipeline: shared agent connection, the eval's temporary signing key
            from secure_sql_agent.service import build_pipeline
            pipeline = build_pipeline(lambda: agent, owns_conn=False, key_id=KEY_ID, secret=secret, guards=guards)
        else:
            print("WARNING: OPENROUTER_API_KEY not set; scoring the stub pipeline (every item will fail)")
            pipeline = None
        svc = QueryService(IdentityVerifier(issuer=ISS, hs256_secret=SECRET), pipeline)
        for it in items:
            truth = reference_rows(it, admin, agent, secret)[0] if it["expect"] == "answered" else None
            t0 = time.perf_counter()
            res = svc.handle(QueryRequest(question=it["question"], identity=token(it["asked_by"])))
            latencies.append((time.perf_counter() - t0) * 1000)
            d = res.model_dump(mode="json")
            results.append(score(it, d, truth))
            usage = (res.model_extra or {}).get("usage") or {}
            if "cost_usd" in usage:
                costs.append(usage["cost_usd"])
    summary = summarize(results, latencies, costs)
    summary["pipeline"] = "live" if live else "stub"
    summary["guards"] = "on" if guards else "off"
    report = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "summary": summary, "results": results}
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    text = json.dumps(report, indent=2)
    stamp = report["at"].replace(":", "").replace("-", "")
    if guards:  # eval_latest.json is what the CI gate reads; the ablation run must not overwrite it
        (out / "eval_latest.json").write_text(text)
    else:
        (out / "eval_guards_off.json").write_text(text)
    (out / f"eval_{stamp}{'' if guards else '_guards_off'}.json").write_text(text)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
