import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory=None):
        self.path = (
            Path(directory or os.getenv("LEDGER_DATA_DIR", "data")) / "ledger.sqlite3"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, created TEXT, state TEXT);
            CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, run_id TEXT UNIQUE, ticker TEXT,
                mode TEXT, as_of TEXT, created TEXT, body TEXT, digest TEXT);
            CREATE TABLE IF NOT EXISTS revisions(id TEXT PRIMARY KEY, memory_id TEXT, created TEXT,
                scope TEXT, feedback TEXT);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def save(self, state):
        with self.connect() as db:
            db.execute(
                "INSERT INTO runs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                (state["id"], state["created"], json.dumps(state, allow_nan=False)),
            )

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT state FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError("Run not found")
        return json.loads(row[0])

    def runs(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT state FROM runs ORDER BY created DESC LIMIT 100"
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def remember(self, run):
        body = {
            "thesis": run["decision"]["summary"],
            "stance": run["decision"]["stance"],
            "invalidation": run["decision"]["invalidation"],
            "evidence_ids": run["decision"]["evidence_ids"],
            "regime": run["metrics"]["regime"],
            "scope": "Source asset, date, and evidence only; not a general trading rule.",
        }
        text = json.dumps(body, sort_keys=True)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO memories VALUES(?,?,?,?,?,?,?,?)",
                (
                    uuid.uuid4().hex,
                    run["id"],
                    run["request"]["ticker"],
                    run["request"]["mode"],
                    run["request"]["as_of"],
                    now(),
                    text,
                    hashlib.sha256(text.encode()).hexdigest(),
                ),
            )

    def memories(self, ticker=None, mode=None, as_of=None, query="", limit=20):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM memories ORDER BY created DESC").fetchall()
            revisions = [
                dict(r) for r in db.execute("SELECT * FROM revisions ORDER BY created")
            ]
        terms = set(re.findall(r"\w+", query.lower()))
        out = []
        for row in rows:
            m = dict(row)
            if ticker and m["ticker"] != ticker or mode and m["mode"] != mode:
                continue
            # Both availability and market date matter. A retrospective run is not old knowledge.
            if as_of and (m["as_of"] > as_of or m["created"][:10] > as_of):
                continue
            m["body"] = json.loads(m["body"])
            m["revisions"] = [
                r
                for r in revisions
                if r["memory_id"] == m["id"]
                and (not as_of or r["created"][:10] <= as_of)
            ]
            if m["revisions"]:
                m["scope"] = m["revisions"][-1]["scope"]
                if m["scope"] == "retire" and as_of:
                    continue
            m["relevance"] = len(
                terms & set(re.findall(r"\w+", json.dumps(m["body"]).lower()))
            )
            out.append(m)
        return sorted(out, key=lambda m: (m["relevance"], m["created"]), reverse=True)[
            :limit
        ]

    def revise(self, memory_id, feedback, scope):
        with self.connect() as db:
            if not db.execute(
                "SELECT 1 FROM memories WHERE id=?", (memory_id,)
            ).fetchone():
                raise KeyError("Memory not found")
            result = dict(
                id=uuid.uuid4().hex,
                memory_id=memory_id,
                created=now(),
                scope=scope,
                feedback=feedback,
            )
            db.execute(
                "INSERT INTO revisions VALUES(:id,:memory_id,:created,:scope,:feedback)",
                result,
            )
        return result
