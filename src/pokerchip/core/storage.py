"""Atomic manifests, disk-backed records, source fingerprints and audit history."""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from uuid import uuid4
import numpy as np


def clean(value):
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def dumps(value):
    return json.dumps(clean(value), ensure_ascii=False, allow_nan=False, sort_keys=True)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".partial-" + uuid4().hex)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(clean(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def digest(value):
    return hashlib.sha256(dumps(value).encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix):
    return prefix + "_" + uuid4().hex[:16]


def database_ok(path):
    """A cache marker alone is not evidence that SQLite pages are readable."""
    try:
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
            return db.execute('PRAGMA quick_check').fetchone()==('ok',)
    except (sqlite3.Error,OSError):return False


def backup_database(source, destination):
    """Copy a transactionally consistent snapshot, including uncheckpointed WAL."""
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA quick_check').fetchone()!=('ok',):
                raise sqlite3.DatabaseError('SQLite snapshot integrity check failed')


class Records:
    """Indexed JSON rows. SQLite transactions are the stage/chunk commit boundary."""
    TABLES = {"frames", "observations", "predictions", "trajectories", "events", "manual"}

    def __init__(self, path, readonly=False):
        self.path = Path(path)
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)
            self.db.execute('PRAGMA query_only=ON')
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA cache_size=-4096")
        for table in self.TABLES:
            self.db.execute(f"CREATE TABLE IF NOT EXISTS {table}(frame INTEGER, chip TEXT, data TEXT, PRIMARY KEY(frame,chip))")
        self.db.commit()

    def put(self, table, frame, chip, value):
        if table not in self.TABLES:
            raise ValueError("알 수 없는 테이블")
        self.db.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?,?)", (int(frame), str(chip), dumps(value)))

    def rows(self, table, chip=None, start=None, end=None):
        if table not in self.TABLES:
            raise ValueError("알 수 없는 테이블")
        where, args = [], []
        for clause, value in [("chip=?", chip), ("frame>=?", start), ("frame<=?", end)]:
            if value is not None:
                where.append(clause)
                args.append(value)
        query = f"SELECT data FROM {table}" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY frame,chip"
        for row in self.db.execute(query, args):
            yield json.loads(row[0])

    def count(self, table):
        if table not in self.TABLES:
            raise ValueError("알 수 없는 테이블")
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def close(self):
        if not self.readonly:self.db.commit()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, exc, tb):
        if typ:
            self.db.rollback()
        self.close()


def correction(project, action, target, after, reason, before=None):
    if not reason.strip():
        raise ValueError("수정 근거를 입력하세요.")
    history = project.setdefault("corrections", [])
    cursor = project.get("correction_cursor", len(history))
    # Retain abandoned redo entries in a separate immutable audit trail.
    project.setdefault("correction_audit", []).append({"operation": "edit", "at": stamp(), "cursor": cursor})
    project.setdefault("abandoned_corrections", []).extend(history[cursor:])
    del history[cursor:]
    history.append({"id": new_id("edit"), "action": action, "target": target,
                    "before": copy.deepcopy(before), "after": copy.deepcopy(after), "reason": reason,
                    "at": stamp(), "invalidates": ["analysis", "physics", "fit", "export"]})
    project["correction_cursor"] = len(history)


def undo_redo(project, delta):
    n = len(project.get("corrections", []))
    old = project.get("correction_cursor", n)
    project["correction_cursor"] = min(n, max(0, old + delta))
    project.setdefault("correction_audit", []).append({"operation": "undo" if delta < 0 else "redo", "at": stamp(), "from": old, "to": project["correction_cursor"]})


def active_corrections(project):
    return project.get("corrections", [])[:project.get("correction_cursor", len(project.get("corrections", [])))]
