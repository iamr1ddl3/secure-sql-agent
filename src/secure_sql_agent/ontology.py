"""Load ontology/bank.yaml: one source for role allowlists, the model's schema text, and (via scripts/gen_from_ontology.py)
the grants/RLS SQL. Edit the YAML, not the derived copies."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

PATH = Path(os.environ.get("ONTOLOGY_FILE", Path(__file__).resolve().parents[2] / "ontology" / "bank.yaml"))
SCOPE_TEXT = {"own_branch": "rows: your own branch only", "all": "rows: all branches", "aggregate_only": "aggregates only"}


@lru_cache
def load() -> dict:
    return yaml.safe_load(PATH.read_text())


def tables_by_role() -> dict[str, set[str]]:
    o = load()
    return {role: {o["entities"][e]["table"] for e in ents} for role, ents in o["permissions"].items()}


def denied_columns() -> dict[str, set[str]]:
    """Per role, raw columns withheld anywhere (names only; the validator checks by column name)."""
    out: dict[str, set[str]] = {}
    for role, ents in load()["permissions"].items():
        cols = {c for p in ents.values() for c in p.get("deny_columns", [])}
        if cols:
            out[role] = cols
    return out


def _decl(c: dict) -> str:
    s = f"{c['name']} {c['type']}"
    if c.get("values"):
        s += ": " + "|".join(c["values"])
    if c.get("pii") == "raw":
        s += " (PII)"
    return s


def schema_for(role: str, semantic: bool = False) -> str:
    """Schema text for the model: only what `role` may use. semantic=True adds synonyms, joins, row scope and business terms."""
    o = load()
    ents = o["entities"]
    lines = []
    for ent_name, perm in sorted(o["permissions"][role].items(), key=lambda kv: ents[kv[0]]["table"]):
        e, hidden = ents[ent_name], set(perm.get("deny_columns", []))
        cols = [_decl(c) for c in e["columns"] if c["name"] not in hidden]
        lines.append(f"{e['table']} -- {e['note']}\n  ({', '.join(cols)})")
        if semantic:
            extra = [SCOPE_TEXT[perm["rows"]]]
            if e.get("synonyms"):
                extra.append("also called: " + ", ".join(e["synonyms"]))
            for j in e.get("joins", []):
                t = ents[j["to"]]["table"]
                if j["to"] in o["permissions"][role]:
                    extra.append(f"join: {e['table']}.{j['via'][0]} = {t}.{j['via'][1]}")
            lines.append("  " + "; ".join(extra))
    if semantic:
        lines.append("Business terms:\n" + "\n".join(f"- {k}: {v}" for k, v in o["terms"].items()))
    return "\n".join(lines)
