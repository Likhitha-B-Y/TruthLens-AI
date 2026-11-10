"""SQLite persistence: documents, pages, passages, embedding cache, sessions, settings, evaluation runs."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    ext           TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    sha256        TEXT NOT NULL UNIQUE,
    stored_path   TEXT NOT NULL,
    page_count    INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    word_count    INTEGER NOT NULL DEFAULT 0,
    passage_count INTEGER NOT NULL DEFAULT 0,
    meta          TEXT NOT NULL DEFAULT '{}',
    is_sample     INTEGER NOT NULL DEFAULT 0,
    uploaded_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    doc_id  INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page    INTEGER NOT NULL,
    text    TEXT NOT NULL,
    PRIMARY KEY (doc_id, page)
);

CREATE TABLE IF NOT EXISTS passages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page      INTEGER NOT NULL,
    idx       INTEGER NOT NULL,
    text      TEXT NOT NULL,
    text_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_passages_doc ON passages(doc_id);

CREATE TABLE IF NOT EXISTS embeddings (
    text_hash TEXT NOT NULL,
    model     TEXT NOT NULL,
    dim       INTEGER NOT NULL,
    vec       BLOB NOT NULL,
    PRIMARY KEY (text_hash, model)
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,           -- queued | running | completed | failed
    answer_text     TEXT NOT NULL,
    document_ids    TEXT NOT NULL DEFAULT '[]',
    settings        TEXT NOT NULL DEFAULT '{}',
    progress        TEXT NOT NULL DEFAULT '{}',
    summary         TEXT NOT NULL DEFAULT '{}',
    claims          TEXT NOT NULL DEFAULT '[]',
    processing_time REAL,
    error           TEXT,
    title           TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    finished_at TEXT,
    status      TEXT NOT NULL,               -- running | completed | failed
    config      TEXT NOT NULL DEFAULT '{}',
    progress    TEXT NOT NULL DEFAULT '{}',
    results     TEXT,
    error       TEXT
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _loads(v: str | None, default: Any) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return default


class Database:
    """Thin, thread-safe SQLite wrapper (one short-lived connection per operation)."""

    def __init__(self, path: Path | str):
        self.path = str(path)
        self._init_lock = threading.Lock()
        self.init()

    # ------------------------------------------------------------------ core
    @contextmanager
    def conn(self) -> Iterator[sqlite3.Connection]:
        c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()

    def init(self) -> None:
        with self._init_lock:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with self.conn() as c:
                c.executescript(SCHEMA)

    # -------------------------------------------------------------- documents
    def add_document(self, *, name: str, ext: str, size_bytes: int, sha256: str, stored_path: str,
                     pages: list[tuple[int, str]], meta: dict, is_sample: bool = False) -> int:
        char_count = sum(len(t) for _, t in pages)
        word_count = sum(len(t.split()) for _, t in pages)
        with self.conn() as c:
            cur = c.execute(
                """INSERT INTO documents(name, ext, size_bytes, sha256, stored_path, page_count, char_count,
                   word_count, meta, is_sample, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (name, ext, size_bytes, sha256, stored_path, len(pages), char_count, word_count,
                 json.dumps(meta), int(is_sample), utcnow()),
            )
            doc_id = cur.lastrowid
            c.executemany("INSERT INTO pages(doc_id, page, text) VALUES (?,?,?)",
                          [(doc_id, p, t) for p, t in pages])
            return int(doc_id)

    def get_document_by_hash(self, sha256: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM documents WHERE sha256=?", (sha256,)).fetchone()
        return self._doc_row(r) if r else None

    def get_document(self, doc_id: int) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        return self._doc_row(r) if r else None

    def list_documents(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM documents ORDER BY uploaded_at DESC, id DESC").fetchall()
        return [self._doc_row(r) for r in rows]

    def delete_document(self, doc_id: int) -> str | None:
        """Delete a document (pages + passages cascade). Returns the stored file path."""
        with self.conn() as c:
            r = c.execute("SELECT stored_path FROM documents WHERE id=?", (doc_id,)).fetchone()
            if not r:
                return None
            c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
            return r["stored_path"]

    def get_pages(self, doc_id: int) -> list[tuple[int, str]]:
        with self.conn() as c:
            rows = c.execute("SELECT page, text FROM pages WHERE doc_id=? ORDER BY page", (doc_id,)).fetchall()
        return [(r["page"], r["text"]) for r in rows]

    @staticmethod
    def _doc_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["meta"] = _loads(d.get("meta"), {})
        d["is_sample"] = bool(d.get("is_sample"))
        return d

    # --------------------------------------------------------------- passages
    def replace_passages(self, doc_id: int, passages: list[dict]) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM passages WHERE doc_id=?", (doc_id,))
            c.executemany(
                "INSERT INTO passages(doc_id, page, idx, text, text_hash) VALUES (?,?,?,?,?)",
                [(doc_id, p["page"], p["idx"], p["text"], p["text_hash"]) for p in passages],
            )
            c.execute("UPDATE documents SET passage_count=? WHERE id=?", (len(passages), doc_id))

    def all_passages(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                """SELECT p.id, p.doc_id, d.name AS doc_name, p.page, p.idx, p.text, p.text_hash
                   FROM passages p JOIN documents d ON d.id = p.doc_id ORDER BY p.id"""
            ).fetchall()
        return [dict(r) for r in rows]

    def get_passages_for_doc(self, doc_id: int, limit: int | None = None) -> list[dict]:
        q = "SELECT id, doc_id, page, idx, text FROM passages WHERE doc_id=? ORDER BY id"
        if limit:
            q += f" LIMIT {int(limit)}"
        with self.conn() as c:
            return [dict(r) for r in c.execute(q, (doc_id,)).fetchall()]

    # ------------------------------------------------------------- embeddings
    def get_embeddings(self, hashes: Iterable[str], model: str) -> dict[str, np.ndarray]:
        hashes = list(set(hashes))
        out: dict[str, np.ndarray] = {}
        with self.conn() as c:
            for i in range(0, len(hashes), 500):
                chunk = hashes[i:i + 500]
                q = ",".join("?" * len(chunk))
                for r in c.execute(
                    f"SELECT text_hash, vec FROM embeddings WHERE model=? AND text_hash IN ({q})",
                    [model, *chunk],
                ):
                    out[r["text_hash"]] = np.frombuffer(r["vec"], dtype=np.float32)
        return out

    def put_embeddings(self, items: dict[str, np.ndarray], model: str) -> None:
        if not items:
            return
        with self.conn() as c:
            c.executemany(
                "INSERT OR REPLACE INTO embeddings(text_hash, model, dim, vec) VALUES (?,?,?,?)",
                [(h, model, int(v.shape[0]), v.astype(np.float32).tobytes()) for h, v in items.items()],
            )

    def prune_embeddings(self) -> int:
        """Remove cached vectors that no passage references any more."""
        with self.conn() as c:
            cur = c.execute("DELETE FROM embeddings WHERE text_hash NOT IN (SELECT text_hash FROM passages)")
            return cur.rowcount

    # ---------------------------------------------------------------- settings
    def get_setting(self, key: str, default: Any = None) -> Any:
        with self.conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return _loads(r["value"], default) if r else default

    def set_setting(self, key: str, value: Any) -> None:
        with self.conn() as c:
            c.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)", (key, json.dumps(value)))

    def delete_setting(self, key: str) -> None:
        with self.conn() as c:
            c.execute("DELETE FROM settings WHERE key=?", (key,))

    # ---------------------------------------------------------------- sessions
    def create_session(self, *, answer_text: str, document_ids: list[int], settings: dict, title: str) -> str:
        sid = uuid.uuid4().hex[:12]
        with self.conn() as c:
            c.execute(
                """INSERT INTO sessions(id, created_at, status, answer_text, document_ids, settings, progress, title)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sid, utcnow(), "queued", answer_text, json.dumps(document_ids), json.dumps(settings),
                 json.dumps({"stage": "queued", "done": 0, "total": 0}), title),
            )
        return sid

    def update_session(self, sid: str, **fields: Any) -> None:
        if not fields:
            return
        json_cols = {"document_ids", "settings", "progress", "summary", "claims"}
        sets, vals = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            vals.append(json.dumps(v) if k in json_cols else v)
        vals.append(sid)
        with self.conn() as c:
            c.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE id=?", vals)

    def get_session(self, sid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        return self._session_row(r, full=True) if r else None

    def list_sessions(self, limit: int = 200) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM sessions ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._session_row(r, full=False) for r in rows]

    def delete_session(self, sid: str) -> bool:
        with self.conn() as c:
            return c.execute("DELETE FROM sessions WHERE id=?", (sid,)).rowcount > 0

    def delete_all_sessions(self) -> int:
        with self.conn() as c:
            return c.execute("DELETE FROM sessions").rowcount

    def fail_stale_sessions(self) -> int:
        """Sessions left 'running' by a previous process can never finish; mark them failed."""
        with self.conn() as c:
            return c.execute(
                "UPDATE sessions SET status='failed', error='Interrupted by server restart', finished_at=? "
                "WHERE status IN ('queued','running')", (utcnow(),)
            ).rowcount

    @staticmethod
    def _session_row(r: sqlite3.Row, full: bool) -> dict:
        d = dict(r)
        for k, default in (("document_ids", []), ("settings", {}), ("progress", {}), ("summary", {}), ("claims", [])):
            d[k] = _loads(d.get(k), default)
        if not full:
            d.pop("claims", None)
            d["answer_preview"] = (d.get("answer_text") or "")[:220]
            d.pop("answer_text", None)
            d.pop("settings", None)
        return d

    # --------------------------------------------------------------- eval runs
    def create_eval_run(self, config: dict) -> str:
        rid = uuid.uuid4().hex[:12]
        with self.conn() as c:
            c.execute(
                "INSERT INTO eval_runs(id, created_at, status, config, progress) VALUES (?,?,?,?,?)",
                (rid, utcnow(), "running", json.dumps(config), json.dumps({"stage": "starting", "done": 0, "total": 0})),
            )
        return rid

    def update_eval_run(self, rid: str, **fields: Any) -> None:
        json_cols = {"config", "progress", "results"}
        sets, vals = [], []
        for k, v in fields.items():
            sets.append(f"{k}=?")
            vals.append(json.dumps(v) if k in json_cols else v)
        vals.append(rid)
        with self.conn() as c:
            c.execute(f"UPDATE eval_runs SET {', '.join(sets)} WHERE id=?", vals)

    def get_eval_run(self, rid: str) -> dict | None:
        with self.conn() as c:
            r = c.execute("SELECT * FROM eval_runs WHERE id=?", (rid,)).fetchone()
        return self._eval_row(r) if r else None

    def list_eval_runs(self, limit: int = 20) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("SELECT * FROM eval_runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._eval_row(r) for r in rows]

    def latest_completed_eval(self) -> dict | None:
        with self.conn() as c:
            r = c.execute(
                "SELECT * FROM eval_runs WHERE status='completed' ORDER BY created_at DESC, rowid DESC LIMIT 1"
            ).fetchone()
        return self._eval_row(r) if r else None

    def fail_stale_eval_runs(self) -> int:
        with self.conn() as c:
            return c.execute(
                "UPDATE eval_runs SET status='failed', error='Interrupted by server restart', finished_at=? "
                "WHERE status='running'", (utcnow(),)
            ).rowcount

    @staticmethod
    def _eval_row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["config"] = _loads(d.get("config"), {})
        d["progress"] = _loads(d.get("progress"), {})
        d["results"] = _loads(d.get("results"), None)
        return d
