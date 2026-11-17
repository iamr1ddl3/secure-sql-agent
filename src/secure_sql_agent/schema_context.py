"""Role-aware schema text for the model: only tables and columns the caller's role may use.

Derived from ontology/bank.yaml (see ontology.py). `semantic=True` adds synonyms, joins, row scope and business terms
(the with-ontology arm of the stage-2 eval); the default text is the stage-1 baseline.
"""
from __future__ import annotations

from . import ontology


def schema_for(app_role: str, semantic: bool = False) -> str:
    return ontology.schema_for(app_role, semantic)
