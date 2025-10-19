
import sqlite3
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

DEFAULT_DB = str(Path(__file__).resolve().parent / "simdb.sqlite")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY,
    address TEXT,
    mls_number TEXT,
    latitude REAL,
    longitude REAL,
    beds INTEGER,
    baths INTEGER,
    sqft INTEGER,
    year_built INTEGER,
    notes TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY,
    property_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(property_id) REFERENCES properties(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    scenario_id INTEGER NOT NULL,
    run_at TEXT,
    monthly_mortgage REAL,
    initial_coc REAL,
    ending_monthly_cf REAL,
    cumulative_cf REAL,
    terminal_equity REAL,
    total_invested_est REAL,
    total_return_est REAL,
    payback_month INTEGER,
    csv_path TEXT,
    FOREIGN KEY(scenario_id) REFERENCES scenarios(id) ON DELETE CASCADE
);
"""

def connect(db_path: str = DEFAULT_DB):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: str = DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()

def now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

# -------- properties --------
def list_properties(db_path: str = DEFAULT_DB) -> List[Dict[str, Any]]:
    conn = connect(db_path)
    try:
        cur = conn.execute("""
            SELECT id, address, mls_number, latitude, longitude, beds, baths, sqft, year_built, notes,
                   created_at, updated_at
            FROM properties
            ORDER BY created_at DESC
        """)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

def upsert_property(prop: Dict[str, Any], db_path: str = DEFAULT_DB) -> int:
    """
    Insert or update a property. If 'id' in prop, update, else insert.
    Returns the id.
    """
    conn = connect(db_path)
    try:
        ts = now()
        if prop.get("id"):
            conn.execute("""
                UPDATE properties
                SET address=?, mls_number=?, latitude=?, longitude=?, beds=?, baths=?, sqft=?, year_built=?, notes=?, updated_at=?
                WHERE id=?
            """, (
                prop.get("address"), prop.get("mls_number"), prop.get("latitude"), prop.get("longitude"),
                prop.get("beds"), prop.get("baths"), prop.get("sqft"), prop.get("year_built"), prop.get("notes"),
                ts, prop["id"]
            ))
            conn.commit()
            return int(prop["id"])
        else:
            cur = conn.execute("""
                INSERT INTO properties (address, mls_number, latitude, longitude, beds, baths, sqft, year_built, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prop.get("address"), prop.get("mls_number"), prop.get("latitude"), prop.get("longitude"),
                prop.get("beds"), prop.get("baths"), prop.get("sqft"), prop.get("year_built"), prop.get("notes"),
                ts, ts
            ))
            conn.commit()
            return int(cur.lastrowid)
    finally:
        conn.close()

def delete_property(prop_id: int, db_path: str = DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM properties WHERE id=?", (prop_id,))
        conn.commit()
    finally:
        conn.close()

# -------- scenarios --------
def list_scenarios(property_id: int, db_path: str = DEFAULT_DB) -> List[Dict[str, Any]]:
    conn = connect(db_path)
    try:
        cur = conn.execute("""
            SELECT id, property_id, name, params_json, created_at, updated_at
            FROM scenarios
            WHERE property_id=?
            ORDER BY updated_at DESC, created_at DESC
        """, (property_id,))
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        for r in rows:
            try:
                r["params"] = json.loads(r["params_json"])
            except Exception:
                r["params"] = {}
        return rows
    finally:
        conn.close()

def get_scenario(scenario_id: int, db_path: str = DEFAULT_DB) -> Optional[Dict[str, Any]]:
    conn = connect(db_path)
    try:
        cur = conn.execute("""
            SELECT id, property_id, name, params_json, created_at, updated_at
            FROM scenarios
            WHERE id=?
        """, (scenario_id,))
        row = cur.fetchone()
        if not row:
            return None
        cols = [c[0] for c in cur.description]
        rec = dict(zip(cols, row))
        try:
            rec["params"] = json.loads(rec["params_json"])
        except Exception:
            rec["params"] = {}
        return rec
    finally:
        conn.close()

def create_scenario(property_id: int, name: str, params: Dict[str, Any], db_path: str = DEFAULT_DB) -> int:
    conn = connect(db_path)
    try:
        ts = now()
        cur = conn.execute("""
            INSERT INTO scenarios (property_id, name, params_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (property_id, name, json.dumps(params), ts, ts))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()

def update_scenario(scenario_id: int, name: str, params: Dict[str, Any], db_path: str = DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        ts = now()
        conn.execute("""
            UPDATE scenarios
            SET name=?, params_json=?, updated_at=?
            WHERE id=?
        """, (name, json.dumps(params), ts, scenario_id))
        conn.commit()
    finally:
        conn.close()

def delete_scenario(scenario_id: int, db_path: str = DEFAULT_DB) -> None:
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM scenarios WHERE id=?", (scenario_id,))
        conn.commit()
    finally:
        conn.close()

# -------- runs --------
def add_run(scenario_id: int, kpis: Dict[str, Any], csv_path: Optional[str], db_path: str = DEFAULT_DB) -> int:
    conn = connect(db_path)
    try:
        cur = conn.execute("""
            INSERT INTO runs (scenario_id, run_at, monthly_mortgage, initial_coc, ending_monthly_cf,
                              cumulative_cf, terminal_equity, total_invested_est, total_return_est, payback_month, csv_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            scenario_id, now(), 
            float(kpis.get("monthly_mortgage", 0.0)),
            float(kpis.get("initial_cash_on_cash_percent", 0.0)),
            float(kpis.get("ending_monthly_cash_flow", 0.0)),
            float(kpis.get("cumulative_cash_flow", 0.0)),
            float(kpis.get("terminal_equity", 0.0)),
            float(kpis.get("total_invested_est", 0.0)),
            float(kpis.get("total_return_est", 0.0)),
            int(kpis.get("payback_month_on_upfront", -1)) if kpis.get("payback_month_on_upfront") is not None else None,
            csv_path
        ))
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()

def list_runs(scenario_id: int, db_path: str = DEFAULT_DB) -> list:
    conn = connect(db_path)
    try:
        cur = conn.execute("""
            SELECT id, scenario_id, run_at, monthly_mortgage, initial_coc, ending_monthly_cf,
                   cumulative_cf, terminal_equity, total_invested_est, total_return_est, payback_month, csv_path
            FROM runs
            WHERE scenario_id=?
            ORDER BY run_at DESC
        """, (scenario_id,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
