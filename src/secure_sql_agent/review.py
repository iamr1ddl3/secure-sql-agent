"""Human approval queue for sensitive results (status `needs_review`).

Rule: a bulk export of RAW identifiers (national ID, phone, account number; more than BULK_PII_ROWS rows) is not returned.
It is parked here and a second person must approve it. Approval never widens access and never shows the approver the data: the requester
collects the result, and the stored SQL is re-run AS THE REQUESTER, so the database still decides what comes back. The approver must be a different, verified staff user in an
approver role. SQLite keeps this dependency-free; swap for a table when there is a writable app schema.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

RAW_PII = {"national_id", "phone", "account_number"}
BULK_PII_ROWS = 20
APPROVER_ROLES = {"branch_manager", "auditor"}


def needs_review(column_names: list[str], row_count: int) -> bool:
    return row_count > BULK_PII_ROWS and any(c in RAW_PII for c in column_names)


class ReviewStore:
    def __init__(self, path: str | Path = "reports/review_queue.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""create table if not exists reviews (
            id text primary key, requester text not null, role text not null, question text not null, sql text not null,
            max_rows integer not null, status text not null default 'pending', approver text,
            created_at text not null, decided_at text)""")

    def create(self, requester: uuid.UUID, role: str, question: str, sql: str, max_rows: int) -> str:
        rid = f"rv_{uuid.uuid4().hex[:12]}"
        self.db.execute("insert into reviews (id, requester, role, question, sql, max_rows, created_at) values (?,?,?,?,?,?,?)",
                        (rid, str(requester), role, question, sql, max_rows, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
        return rid

    def get(self, rid: str) -> sqlite3.Row | None:
        return self.db.execute("select * from reviews where id = ?", (rid,)).fetchone()

    def pending(self) -> list[sqlite3.Row]:
        return self.db.execute("select id, role, question, created_at from reviews where status = 'pending' order by created_at").fetchall()

    def collect(self, rid: str, requester: uuid.UUID) -> sqlite3.Row | None:
        """Requester takes delivery of an approved review, once. The approver never receives the data."""
        cur = self.db.execute("update reviews set status = 'collected' where id = ? and status = 'approved' and requester = ?",
                              (rid, str(requester)))
        self.db.commit()
        return self.get(rid) if cur.rowcount == 1 else None

    def decide(self, rid: str, approver: uuid.UUID, approve: bool) -> bool:
        """Atomically move pending -> approved/rejected. False if it was not pending (already decided, or unknown)."""
        cur = self.db.execute("update reviews set status = ?, approver = ?, decided_at = ? where id = ? and status = 'pending'",
                              ("approved" if approve else "rejected", str(approver), datetime.now(timezone.utc).isoformat(), rid))
        self.db.commit()
        return cur.rowcount == 1
