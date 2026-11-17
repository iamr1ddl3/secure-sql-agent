"""SQL validator: positive-list check of model-written SQL before it reaches the database.

Defence in depth only. The database (roles, column grants, RLS) is what enforces access; this stage exists to
refuse early with a clear reason, keep obviously hostile SQL away from the database, and give the eval a
measurable "blocked by validator" signal. Everything not explicitly allowed is rejected:

  * exactly one statement, parsed as Postgres; the SQL that runs is the re-generated text, never the original
  * only node types in ALLOWED_NODES (no DML/DDL, SET, COPY, INTO, locking, anonymous/unknown functions)
  * only tables the caller's role may read, always schema-qualified (bank.* / analytics.*)
  * no `*` outside COUNT(*), and no raw PII columns for the auditor
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

MAX_SQL_CHARS = 4000

TABLES: dict[str, set[str]] = {
    "teller": {"bank.branches", "bank.customers", "bank.accounts", "bank.transactions"},
    "branch_manager": {"bank.branches", "bank.customers", "bank.accounts", "bank.transactions", "bank.loans",
                       "bank.employees", "bank.salaries"},
    "hr": {"bank.branches", "bank.employees", "bank.salaries"},
    "auditor": {"bank.branches", "bank.customers", "bank.accounts", "bank.transactions", "bank.loans",
                "bank.employees", "bank.salaries", "analytics.branch_monthly_flows",
                "analytics.branch_customer_counts", "analytics.loan_portfolio_summary",
                "analytics.headcount_by_branch"},
    "intern": {"bank.branches", "analytics.branch_monthly_flows", "analytics.branch_customer_counts",
               "analytics.loan_portfolio_summary", "analytics.headcount_by_branch"},
}
DENIED_COLUMNS: dict[str, set[str]] = {"auditor": {"national_id", "phone", "account_number"}}

ALLOWED_NODES = tuple(getattr(exp, n) for n in """
Select Subquery With CTE Union Intersect Except Table TableAlias Alias Column Identifier Star Literal Boolean Null
Paren And Or Not EQ NEQ GT GTE LT LTE In Between Like ILike Is Add Sub Mul Div Mod Neg Cast DataType Case If
Coalesce Nullif Greatest Least Count Sum Avg Min Max Round Abs Lower Upper Length Concat Substring Extract
TimestampTrunc DateTrunc AtTimeZone Filter Distinct From Join Where Group Having Order Ordered Limit Offset Var
Interval CurrentDate Exists Tuple Ceil Floor
""".split())


class ValidationError(Exception):
    def __init__(self, policy_id: str, detail: str):
        super().__init__(detail)
        self.policy_id, self.detail = policy_id, detail


@dataclass
class Validated:
    sql: str            # normalized Postgres text: the only thing that may be executed
    tables: list[str]


def validate(sql: str, app_role: str) -> Validated:
    if app_role not in TABLES:
        raise ValidationError("validator.unknown_role", f"unknown role {app_role!r}")
    if not sql or len(sql) > MAX_SQL_CHARS:
        raise ValidationError("validator.size", "empty or too long")
    try:
        stmts = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.SqlglotError as e:
        raise ValidationError("validator.parse_error", str(e)[:200]) from e
    if len(stmts) != 1 or stmts[0] is None:
        raise ValidationError("validator.multiple_statements", "exactly one statement is allowed")
    tree = stmts[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        raise ValidationError("validator.not_select", f"only SELECT is allowed, got {type(tree).__name__}")

    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    tables: list[str] = []
    for node in tree.walk():
        if not isinstance(node, ALLOWED_NODES):
            kind = "function" if isinstance(node, (exp.Func, exp.Anonymous)) else "construct"
            raise ValidationError(f"validator.forbidden_{kind}", f"{type(node).__name__} is not allowed")
        if isinstance(node, exp.Select) and (node.args.get("into") or node.args.get("locks")):
            raise ValidationError("validator.not_select", "SELECT INTO / FOR UPDATE is not allowed")
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise ValidationError("validator.select_star", "list the columns you need instead of *")
        if isinstance(node, exp.Table):
            name = f"{node.db}.{node.name}".lower() if node.db else node.name.lower()
            if not node.db and name in ctes:
                continue
            if name not in TABLES[app_role]:
                raise ValidationError("validator.forbidden_table", f"{name} is not available to role {app_role}")
            tables.append(name)
        if isinstance(node, exp.Column) and node.name.lower() in DENIED_COLUMNS.get(app_role, ()):
            raise ValidationError("validator.pii_column", f"{node.name} is not available to role {app_role} (use the masked column)")
    return Validated(tree.sql(dialect="postgres"), sorted(set(tables)))
