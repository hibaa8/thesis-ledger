import hashlib
import uuid
from datetime import datetime, timezone

import psycopg
from psycopg.types.json import Jsonb

from .store import memory_body, now, rank_memories


class PostgresStore:
    """Durable research records with local chat, caches and usage counters."""

    def __init__(self, local, url, workspace="owner"):
        self.local = local
        self.url = url
        self.workspace = workspace

    def for_visitor(self, visitor):
        return self.local.for_visitor(visitor)

    def for_account(self, account):
        return PostgresStore(self.local.for_account(account), self.url, f"account:{account}")

    def connect(self):
        return self.local.connect()

    def chat_history(self, session, limit=100):
        return self.local.chat_history(session, limit)

    def save_chat(self, session, question, answer):
        self.local.save_chat(session, question, answer)

    def cached_forecast(self, key):
        return self.local.cached_forecast(key)

    def save_forecast(self, key, result):
        self.local.save_forecast(key, result)

    def _db(self):
        return psycopg.connect(self.url, connect_timeout=8)

    def _save(self, kind, record_id, created, payload, *, replace=False):
        conflict = "DO UPDATE SET payload = excluded.payload" if replace else "DO NOTHING"
        with self._db() as db:
            db.execute(
                "INSERT INTO thesis_ledger.records VALUES (%s,%s,%s,%s,%s) "
                f"ON CONFLICT (workspace,kind,id) {conflict}",
                (self.workspace, kind, record_id, created, Jsonb(payload)),
            )

    def save(self, state):
        self._save("run", state["id"], state["created"], state, replace=True)

    def get(self, run_id):
        with self._db() as db:
            row = db.execute(
                "SELECT payload FROM thesis_ledger.records "
                "WHERE workspace=%s AND kind='run' AND id=%s",
                (self.workspace, run_id),
            ).fetchone()
        if not row:
            raise KeyError("Run not found")
        return row[0]

    def runs(self):
        with self._db() as db:
            rows = db.execute(
                "SELECT payload FROM thesis_ledger.records WHERE workspace=%s AND kind='run' "
                "ORDER BY created DESC LIMIT 100",
                (self.workspace,),
            ).fetchall()
        return [row[0] for row in rows]

    def latest_live_report(self, ticker):
        with self._db() as db:
            row = db.execute(
                """SELECT payload FROM thesis_ledger.records
                WHERE workspace=%s AND kind='run' AND payload->>'status'='complete'
                  AND payload->'request'->>'mode'='live'
                  AND payload->'request'->>'ticker'=%s
                  AND payload->'request'->>'as_of' <= %s
                ORDER BY payload->'request'->>'as_of' DESC, created DESC LIMIT 1""",
                (self.workspace, ticker, datetime.now(timezone.utc).date().isoformat()),
            ).fetchone()
        return row[0] if row else None

    def remember(self, run):
        body = memory_body(run)
        memory = dict(
            id=uuid.uuid4().hex,
            run_id=run["id"],
            ticker=run["request"]["ticker"],
            mode=run["request"]["mode"],
            as_of=run["request"]["as_of"],
            created=now(),
            body=body,
            digest=hashlib.sha256(body.encode()).hexdigest(),
        )
        self._save("memory", run["id"], memory["created"], memory)

    def memories(self, ticker=None, mode=None, as_of=None, query="", limit=20):
        with self._db() as db:
            rows = db.execute(
                "SELECT kind, payload FROM thesis_ledger.records "
                "WHERE workspace=%s AND kind IN ('memory', 'revision') ORDER BY created",
                (self.workspace,),
            ).fetchall()
        memories = [payload for kind, payload in rows if kind == "memory"]
        revisions = [payload for kind, payload in rows if kind == "revision"]
        return rank_memories(memories, revisions, ticker, mode, as_of, query, limit)

    def revise(self, memory_id, feedback, scope):
        with self._db() as db:
            exists = db.execute(
                "SELECT 1 FROM thesis_ledger.records "
                "WHERE workspace=%s AND kind='memory' AND payload->>'id'=%s",
                (self.workspace, memory_id),
            ).fetchone()
        if not exists:
            raise KeyError("Memory not found")
        revision = dict(id=uuid.uuid4().hex, memory_id=memory_id, created=now(),
                        scope=scope, feedback=feedback)
        self._save("revision", revision["id"], revision["created"], revision)
        return revision
