"""SQLite schema and repository helpers for local signal persistence."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS scan_runs (
    scan_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    duration_ms INTEGER,
    config_json TEXT NOT NULL DEFAULT '{}',
    summary_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS exchange_health (
    exchange TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    source_status TEXT NOT NULL,
    latency_ms INTEGER,
    error_code TEXT,
    error_message TEXT,
    last_success_at TEXT,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (exchange, endpoint)
);

CREATE TABLE IF NOT EXISTS ticker_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    exchange TEXT NOT NULL,
    raw_symbol TEXT NOT NULL,
    unified_symbol TEXT NOT NULL,
    quote_volume_24h_usd REAL,
    base_volume_24h REAL,
    last_price REAL,
    price_change_pct_24h REAL,
    source_status TEXT NOT NULL,
    latency_ms INTEGER,
    updated_at TEXT NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS activity_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    exchanges_json TEXT NOT NULL DEFAULT '[]',
    primary_exchange TEXT,
    activity_score REAL NOT NULL,
    global_quote_volume_24h_usd REAL,
    market_cap_usd REAL,
    market_cap_status TEXT NOT NULL,
    source_status TEXT NOT NULL,
    exchange_scores_json TEXT NOT NULL DEFAULT '{}',
    is_final_top_m INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS market_caps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market_cap_usd REAL,
    market_cap_status TEXT NOT NULL,
    source TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS primary_exchange_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    primary_exchange TEXT NOT NULL,
    primary_score REAL NOT NULL,
    candidate_exchanges_json TEXT NOT NULL DEFAULT '[]',
    score_breakdown_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS kline_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS indicator_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    close REAL NOT NULL,
    ema20 REAL,
    ema60 REAL,
    macd REAL,
    macd_signal REAL,
    macd_histogram REAL,
    bollinger_upper REAL,
    bollinger_middle REAL,
    bollinger_lower REAL,
    volume_ma REAL,
    recent_swing_low REAL,
    support_level REAL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS signals (
    signal_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    primary_exchange TEXT NOT NULL,
    score REAL NOT NULL,
    entry_zone_low REAL NOT NULL,
    entry_zone_high REAL NOT NULL,
    stop_loss REAL NOT NULL,
    stop_reason TEXT NOT NULL,
    timeframe_alignment_json TEXT NOT NULL DEFAULT '{}',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    invalidation TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scan_runs(scan_id)
);

CREATE TABLE IF NOT EXISTS signal_tracking (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    status TEXT NOT NULL,
    max_favorable_excursion REAL,
    max_adverse_excursion REAL,
    stop_touched INTEGER NOT NULL DEFAULT 0,
    target_touched INTEGER NOT NULL DEFAULT 0,
    duration_minutes INTEGER,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

CREATE TABLE IF NOT EXISTS manual_reviews (
    review_id TEXT PRIMARY KEY,
    signal_id TEXT NOT NULL,
    manual_verdict TEXT NOT NULL,
    manual_notes TEXT NOT NULL,
    manual_tags_json TEXT NOT NULL DEFAULT '[]',
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);

CREATE TABLE IF NOT EXISTS strategy_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT,
    feedback_type TEXT NOT NULL,
    feedback_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (signal_id) REFERENCES signals(signal_id)
);
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must be timezone-aware")
    return value.isoformat()


def to_json(value: Any) -> str:
    def default(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return to_iso(obj)
        if is_dataclass(obj):
            return asdict(obj)
        if isinstance(obj, Path):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    return json.dumps(value if value is not None else {}, ensure_ascii=True, sort_keys=True, default=default)


def from_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    return json.loads(value)


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()


class SQLiteRepository:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        init_db(self.db_path)

    def create_scan_run(
        self,
        *,
        scan_id: str | None = None,
        started_at: datetime | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        scan_id = scan_id or str(uuid4())
        started_at = started_at or utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO scan_runs (scan_id, status, started_at, config_json)
                VALUES (?, ?, ?, ?)
                """,
                (scan_id, "running", to_iso(started_at), to_json(config or {})),
            )
            conn.commit()
        return scan_id

    def complete_scan_run(
        self,
        *,
        scan_id: str,
        status: str,
        completed_at: datetime | None = None,
        summary: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> None:
        completed_at = completed_at or utc_now()
        with connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT started_at FROM scan_runs WHERE scan_id = ?",
                (scan_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"scan_run not found: {scan_id}")
            started_at = datetime.fromisoformat(row["started_at"])
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            conn.execute(
                """
                UPDATE scan_runs
                SET status = ?, completed_at = ?, duration_ms = ?, summary_json = ?, error_message = ?
                WHERE scan_id = ?
                """,
                (status, to_iso(completed_at), duration_ms, to_json(summary or {}), error_message, scan_id),
            )
            conn.commit()

    def insert_event(self, event: Any) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO events (event_id, scan_id, event_type, timestamp, status, message, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.scan_id,
                    event.event_type,
                    to_iso(event.timestamp),
                    event.status,
                    event.message,
                    event.payload_json,
                ),
            )
            conn.commit()

    def upsert_exchange_health(
        self,
        *,
        exchange: str,
        endpoint: str,
        source_status: str,
        latency_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        last_success_at: datetime | None = None,
        updated_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        updated_at = updated_at or utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO exchange_health (
                    exchange, endpoint, source_status, latency_ms, error_code,
                    error_message, last_success_at, updated_at, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(exchange, endpoint) DO UPDATE SET
                    source_status = excluded.source_status,
                    latency_ms = excluded.latency_ms,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    last_success_at = excluded.last_success_at,
                    updated_at = excluded.updated_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    exchange,
                    endpoint,
                    source_status,
                    latency_ms,
                    error_code,
                    error_message,
                    to_iso(last_success_at),
                    to_iso(updated_at),
                    to_json(metadata or {}),
                ),
            )
            conn.commit()

    def insert_signal(
        self,
        *,
        scan_id: str,
        signal: Any,
        signal_id: str | None = None,
        status: str = "created",
    ) -> str:
        signal_id = signal_id or str(uuid4())
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO signals (
                    signal_id, scan_id, symbol, primary_exchange, score,
                    entry_zone_low, entry_zone_high, stop_loss, stop_reason,
                    timeframe_alignment_json, reasons_json, invalidation, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    scan_id,
                    signal.symbol,
                    signal.primary_exchange,
                    signal.score,
                    signal.entry_zone_low,
                    signal.entry_zone_high,
                    signal.stop_loss,
                    signal.stop_reason,
                    to_json(signal.timeframe_alignment),
                    to_json(signal.reasons),
                    signal.invalidation,
                    status,
                    to_iso(signal.created_at),
                ),
            )
            conn.commit()
        return signal_id

    def insert_manual_review(self, review: Any) -> None:
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO manual_reviews (
                    review_id, signal_id, manual_verdict, manual_notes, manual_tags_json, reviewed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review.review_id,
                    review.signal_id,
                    review.manual_verdict,
                    review.manual_notes,
                    to_json(review.manual_tags),
                    to_iso(review.reviewed_at),
                ),
            )
            conn.commit()

    def get_signal(self, *, signal_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signals
                WHERE signal_id = ?
                """,
                (signal_id,),
            ).fetchone()
        return self._signal_row_to_dict(row) if row is not None else None

    def update_signal_status(self, *, signal_id: str, status: str) -> None:
        with connect(self.db_path) as conn:
            result = conn.execute(
                """
                UPDATE signals
                SET status = ?
                WHERE signal_id = ?
                """,
                (status, signal_id),
            )
            if result.rowcount == 0:
                raise KeyError(f"signal not found: {signal_id}")
            conn.commit()

    def insert_signal_tracking(
        self,
        *,
        signal_id: str,
        status: str,
        updated_at: datetime | None = None,
        max_favorable_excursion: float | None = None,
        max_adverse_excursion: float | None = None,
        stop_touched: bool = False,
        target_touched: bool = False,
        duration_minutes: int | None = None,
    ) -> None:
        updated_at = updated_at or utc_now()
        with connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO signal_tracking (
                    signal_id, status, max_favorable_excursion, max_adverse_excursion,
                    stop_touched, target_touched, duration_minutes, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    status,
                    max_favorable_excursion,
                    max_adverse_excursion,
                    int(stop_touched),
                    int(target_touched),
                    duration_minutes,
                    to_iso(updated_at),
                ),
            )
            conn.commit()

    def get_latest_signal_tracking(self, *, signal_id: str) -> dict[str, Any] | None:
        with connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT *
                FROM signal_tracking
                WHERE signal_id = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (signal_id,),
            ).fetchone()
        return self._tracking_row_to_dict(row) if row is not None else None

    def get_recent_signal_feedback_rows(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                WITH latest_tracking AS (
                    SELECT st.*
                    FROM signal_tracking st
                    JOIN (
                        SELECT signal_id, MAX(id) AS max_id
                        FROM signal_tracking
                        GROUP BY signal_id
                    ) latest ON latest.signal_id = st.signal_id AND latest.max_id = st.id
                ),
                latest_reviews AS (
                    SELECT mr.*
                    FROM manual_reviews mr
                    JOIN (
                        SELECT signal_id, MAX(reviewed_at) AS max_reviewed_at
                        FROM manual_reviews
                        GROUP BY signal_id
                    ) latest ON latest.signal_id = mr.signal_id AND latest.max_reviewed_at = mr.reviewed_at
                )
                SELECT
                    s.signal_id,
                    s.symbol,
                    s.primary_exchange,
                    s.status AS signal_status,
                    s.created_at,
                    lt.status AS tracking_status,
                    lt.max_favorable_excursion,
                    lt.max_adverse_excursion,
                    lt.stop_touched,
                    lt.target_touched,
                    lt.duration_minutes,
                    lr.manual_verdict,
                    lr.manual_notes,
                    lr.manual_tags_json,
                    lr.reviewed_at
                FROM signals s
                LEFT JOIN latest_tracking lt ON lt.signal_id = s.signal_id
                LEFT JOIN latest_reviews lr ON lr.signal_id = s.signal_id
                ORDER BY s.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._feedback_row_to_dict(row) for row in rows]

    def get_recent_signal_quality_rows(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                WITH latest_tracking AS (
                    SELECT st.*
                    FROM signal_tracking st
                    JOIN (
                        SELECT signal_id, MAX(id) AS max_id
                        FROM signal_tracking
                        GROUP BY signal_id
                    ) latest ON latest.signal_id = st.signal_id AND latest.max_id = st.id
                ),
                latest_reviews AS (
                    SELECT mr.*
                    FROM manual_reviews mr
                    JOIN (
                        SELECT signal_id, MAX(reviewed_at) AS max_reviewed_at
                        FROM manual_reviews
                        GROUP BY signal_id
                    ) latest ON latest.signal_id = mr.signal_id AND latest.max_reviewed_at = mr.reviewed_at
                )
                SELECT
                    s.signal_id,
                    s.symbol,
                    s.primary_exchange,
                    s.score,
                    s.entry_zone_low,
                    s.entry_zone_high,
                    s.stop_loss,
                    s.stop_reason,
                    s.reasons_json,
                    s.status AS signal_status,
                    s.created_at,
                    lt.status AS tracking_status,
                    lt.max_favorable_excursion,
                    lt.max_adverse_excursion,
                    lt.stop_touched,
                    lt.target_touched,
                    lt.duration_minutes,
                    lr.manual_verdict,
                    lr.manual_notes,
                    lr.manual_tags_json,
                    lr.reviewed_at
                FROM signals s
                LEFT JOIN latest_tracking lt ON lt.signal_id = s.signal_id
                LEFT JOIN latest_reviews lr ON lr.signal_id = s.signal_id
                ORDER BY s.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._quality_row_to_dict(row) for row in rows]

    def get_recent_signals(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM signals
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._signal_row_to_dict(row) for row in rows]

    def get_exchange_health(self) -> list[dict[str, Any]]:
        with connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM exchange_health
                ORDER BY exchange ASC, endpoint ASC
                """
            ).fetchall()
        return [self._exchange_health_row_to_dict(row) for row in rows]

    @staticmethod
    def _signal_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["timeframe_alignment"] = from_json(data.pop("timeframe_alignment_json"), {})
        data["reasons"] = from_json(data.pop("reasons_json"), [])
        return data

    @staticmethod
    def _tracking_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["stop_touched"] = bool(data["stop_touched"])
        data["target_touched"] = bool(data["target_touched"])
        return data

    @staticmethod
    def _feedback_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        if "stop_touched" in data and data["stop_touched"] is not None:
            data["stop_touched"] = bool(data["stop_touched"])
        if "target_touched" in data and data["target_touched"] is not None:
            data["target_touched"] = bool(data["target_touched"])
        data["manual_tags"] = from_json(data.pop("manual_tags_json"), [])
        return data

    @staticmethod
    def _quality_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        if "stop_touched" in data and data["stop_touched"] is not None:
            data["stop_touched"] = bool(data["stop_touched"])
        if "target_touched" in data and data["target_touched"] is not None:
            data["target_touched"] = bool(data["target_touched"])
        data["reasons"] = from_json(data.pop("reasons_json"), [])
        data["manual_tags"] = from_json(data.pop("manual_tags_json"), [])
        return data

    @staticmethod
    def _exchange_health_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["metadata"] = from_json(data.pop("metadata_json"), {})
        return data
