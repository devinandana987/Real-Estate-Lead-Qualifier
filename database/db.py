# database/db.py
"""
SQLite Persistence Layer for Real Estate Lead Qualifier.
Provides robust, thread-safe, and non-destructive database storage and retrieval
for leads, decisions, property matches, and dashboard analytics.
"""

import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Dict, Any, List, Optional, Tuple, Generator

# Default database location within the project
DEFAULT_DB_PATH = os.environ.get(
    "LEAD_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "real_estate_leads.db")
)


def resolve_db_path(db_path: Optional[str] = None) -> str:
    """Resolves and ensures directory exists for the specified SQLite database path."""
    target_path = db_path if db_path else DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    return os.path.abspath(target_path)


@contextmanager
def get_db_connection(db_path: Optional[str] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager that provides a SQLite connection with dict-like row access.
    Automatically commits on success or rolls back on exception, then closes the connection.
    """
    resolved = resolve_db_path(db_path)
    conn = sqlite3.connect(resolved, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys and WAL mode for better concurrency
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database(db_path: Optional[str] = None) -> None:
    """
    Safely and idempotently initializes SQLite tables and indices.
    Never drops or deletes existing data.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()

        # 1. Leads Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                lead_id TEXT PRIMARY KEY,
                name TEXT,
                contact TEXT,
                intent TEXT,
                intent_level TEXT,
                property_type TEXT,
                preferred_city TEXT,
                preferred_locality TEXT,
                alternative_localities TEXT,
                min_budget REAL,
                max_budget REAL,
                budget_flexibility TEXT,
                bedrooms REAL,
                bathrooms REAL,
                min_area_sqft REAL,
                possession_preference TEXT,
                timeline TEXT,
                financing_type TEXT,
                loan_required INTEGER,
                profile_completeness REAL DEFAULT 0.0,
                lead_score REAL,
                lead_quality TEXT,
                next_action TEXT,
                decision_reason TEXT,
                status TEXT DEFAULT 'NEW',
                broker_summary TEXT,
                raw_profile_json TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                updated_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # 2. Lead Property Matches Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lead_property_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id TEXT NOT NULL,
                property_id TEXT NOT NULL,
                title TEXT,
                price REAL,
                location TEXT,
                match_percentage REAL,
                match_reason TEXT,
                created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (lead_id) REFERENCES leads(lead_id) ON DELETE CASCADE
            );
        """)

        # Create indices for fast lookup & filtering
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_quality ON leads(lead_quality);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_next_action ON leads(next_action);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matches_lead_id ON lead_property_matches(lead_id);")


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Converts a sqlite3.Row instance to a standard Python dictionary."""
    if row is None:
        return None
    return dict(row)


def save_lead(lead_data: Dict[str, Any], db_path: Optional[str] = None) -> bool:
    """
    Saves or updates a lead record in the database.
    Uses UPSERT logic so existing leads are updated without overwriting created_at.
    Returns True on success.
    """
    lead_id = lead_data.get("lead_id")
    if not lead_id or not str(lead_id).strip():
        raise ValueError("Cannot save lead: 'lead_id' is missing or empty.")

    initialize_database(db_path)

    # Format JSON strings safely
    alt_localities = lead_data.get("alternative_localities")
    if isinstance(alt_localities, (list, dict)):
        alt_localities = json.dumps(alt_localities)
    elif alt_localities is not None:
        alt_localities = str(alt_localities)

    raw_json = lead_data.get("raw_profile_json")
    if isinstance(raw_json, dict):
        raw_json = json.dumps(raw_json)

    decision_reason = lead_data.get("decision_reason")
    if isinstance(decision_reason, list):
        decision_reason = "\n".join(f"- {str(r)}" for r in decision_reason)
    elif decision_reason is not None:
        decision_reason = str(decision_reason)

    columns = [
        "lead_id", "name", "contact", "intent", "intent_level",
        "property_type", "preferred_city", "preferred_locality", "alternative_localities",
        "min_budget", "max_budget", "budget_flexibility",
        "bedrooms", "bathrooms", "min_area_sqft",
        "possession_preference", "timeline", "financing_type", "loan_required",
        "profile_completeness", "lead_score", "lead_quality",
        "next_action", "decision_reason", "status", "broker_summary", "raw_profile_json"
    ]

    values = [
        str(lead_id).strip(),
        lead_data.get("name"),
        lead_data.get("contact"),
        lead_data.get("intent"),
        lead_data.get("intent_level"),
        lead_data.get("property_type"),
        lead_data.get("preferred_city"),
        lead_data.get("preferred_locality"),
        alt_localities,
        lead_data.get("min_budget"),
        lead_data.get("max_budget"),
        lead_data.get("budget_flexibility"),
        lead_data.get("bedrooms"),
        lead_data.get("bathrooms"),
        lead_data.get("min_area_sqft"),
        lead_data.get("possession_preference"),
        lead_data.get("timeline"),
        lead_data.get("financing_type"),
        1 if lead_data.get("loan_required") is True else (0 if lead_data.get("loan_required") is False else None),
        lead_data.get("profile_completeness", 0.0),
        lead_data.get("lead_score"),
        lead_data.get("lead_quality"),
        lead_data.get("next_action"),
        decision_reason,
        lead_data.get("status", "NEW"),
        lead_data.get("broker_summary"),
        raw_json
    ]

    # SQLite UPSERT: insert or update non-null/specified fields on conflict
    placeholders = ", ".join(["?"] * len(columns))
    col_names = ", ".join(columns)

    update_clauses = [
        f"{col} = COALESCE(excluded.{col}, leads.{col})"
        for col in columns if col != "lead_id"
    ]
    update_clauses.append("updated_at = datetime('now', 'localtime')")
    update_stmt = ", ".join(update_clauses)

    query = f"""
        INSERT INTO leads ({col_names}, created_at, updated_at)
        VALUES ({placeholders}, datetime('now', 'localtime'), datetime('now', 'localtime'))
        ON CONFLICT(lead_id) DO UPDATE SET {update_stmt};
    """

    with get_db_connection(db_path) as conn:
        conn.execute(query, values)
    return True


def update_lead(lead_id: str, updates: Dict[str, Any], db_path: Optional[str] = None) -> bool:
    """
    Updates specific fields of an existing lead by lead_id.
    Returns True if a record was updated.
    """
    if not lead_id or not updates:
        return False

    valid_cols = {
        "name", "contact", "intent", "intent_level", "property_type",
        "preferred_city", "preferred_locality", "alternative_localities",
        "min_budget", "max_budget", "budget_flexibility", "bedrooms",
        "bathrooms", "min_area_sqft", "possession_preference", "timeline",
        "financing_type", "loan_required", "profile_completeness",
        "lead_score", "lead_quality", "next_action", "decision_reason",
        "status", "broker_summary", "raw_profile_json"
    }

    filtered_updates = {k: v for k, v in updates.items() if k in valid_cols}
    if not filtered_updates:
        return False

    # Format values
    if "alternative_localities" in filtered_updates and isinstance(filtered_updates["alternative_localities"], (list, dict)):
        filtered_updates["alternative_localities"] = json.dumps(filtered_updates["alternative_localities"])
    if "decision_reason" in filtered_updates and isinstance(filtered_updates["decision_reason"], list):
        filtered_updates["decision_reason"] = "\n".join(f"- {str(r)}" for r in filtered_updates["decision_reason"])
    if "raw_profile_json" in filtered_updates and isinstance(filtered_updates["raw_profile_json"], dict):
        filtered_updates["raw_profile_json"] = json.dumps(filtered_updates["raw_profile_json"])

    set_clause = ", ".join([f"{col} = ?" for col in filtered_updates.keys()])
    set_clause += ", updated_at = datetime('now', 'localtime')"
    params = list(filtered_updates.values()) + [str(lead_id).strip()]

    query = f"UPDATE leads SET {set_clause} WHERE lead_id = ?;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        return cursor.rowcount > 0


def save_decision(lead_id: str, decision_data: Dict[str, Any], db_path: Optional[str] = None) -> bool:
    """
    Persists decision results (score, quality, next_action, reasoning, summary) for a lead.
    """
    if not lead_id:
        return False

    reason = decision_data.get("decision_reason") or decision_data.get("reasoning") or decision_data.get("reason")
    if isinstance(reason, list):
        reason = "\n".join(f"- {str(r)}" for r in reason)

    # Ensure the lead record exists so decision is reliably recorded
    initialize_database(db_path)
    clean_lead_id = str(lead_id).strip()
    with get_db_connection(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO leads (lead_id, status) VALUES (?, 'NEW');", (clean_lead_id,))

    updates = {
        "lead_score": decision_data.get("lead_score") if decision_data.get("lead_score") is not None else decision_data.get("score"),
        "lead_quality": decision_data.get("lead_quality") or decision_data.get("qualification_status"),
        "next_action": decision_data.get("next_action"),
        "decision_reason": reason,
        "broker_summary": decision_data.get("broker_summary"),
    }
    # Remove keys with None if we don't want to clear them
    filtered = {k: v for k, v in updates.items() if v is not None}
    return update_lead(clean_lead_id, filtered, db_path)


def save_property_matches(lead_id: str, matches: List[Dict[str, Any]], db_path: Optional[str] = None) -> bool:
    """
    Persists property matches associated with a lead.
    Replaces any previous matches for the lead in a single atomic transaction.
    """
    if not lead_id:
        return False

    initialize_database(db_path)
    clean_lead_id = str(lead_id).strip()

    with get_db_connection(db_path) as conn:
        # Ensure lead record exists to satisfy foreign key constraints safely
        conn.execute("INSERT OR IGNORE INTO leads (lead_id, status) VALUES (?, 'NEW');", (clean_lead_id,))

        # Delete prior matches for this lead to prevent stale duplicates
        conn.execute("DELETE FROM lead_property_matches WHERE lead_id = ?;", (clean_lead_id,))

        if not matches:
            return True

        rows_to_insert = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            prop_id = m.get("property_id") or m.get("id") or "UNKNOWN_PROP"
            title = m.get("title") or m.get("name") or str(prop_id)
            price = m.get("price")
            location = m.get("location") or m.get("locality") or m.get("city")
            match_pct = m.get("match_percentage") or m.get("score") or m.get("match_score")
            match_reason = m.get("match_reason") or m.get("reason")

            rows_to_insert.append((
                clean_lead_id,
                str(prop_id),
                str(title),
                float(price) if price is not None else None,
                str(location) if location is not None else None,
                float(match_pct) if match_pct is not None else None,
                str(match_reason) if match_reason is not None else None
            ))

        if rows_to_insert:
            conn.executemany("""
                INSERT INTO lead_property_matches
                (lead_id, property_id, title, price, location, match_percentage, match_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'));
            """, rows_to_insert)

    return True


def get_lead(lead_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a single lead dictionary by lead_id, or None if not found."""
    if not lead_id:
        return None
    initialize_database(db_path)

    query = "SELECT * FROM leads WHERE lead_id = ?;"
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (str(lead_id).strip(),))
        row = cursor.fetchone()
        return row_to_dict(row)


def get_leads(
    status: Optional[str] = None,
    lead_quality: Optional[str] = None,
    next_action: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves leads matching optional filters with pagination.
    Ordered by creation date descending.
    """
    initialize_database(db_path)

    clauses: List[str] = []
    params: List[Any] = []

    if status and status.upper() != "ALL":
        clauses.append("status = ?")
        params.append(status)

    if lead_quality and lead_quality.upper() != "ALL":
        clauses.append("UPPER(lead_quality) = ?")
        params.append(lead_quality.upper())

    if next_action and next_action.upper() != "ALL":
        clauses.append("next_action = ?")
        params.append(next_action)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        clauses.append("(lead_id LIKE ? OR name LIKE ? OR preferred_city LIKE ? OR preferred_locality LIKE ? OR contact LIKE ?)")
        params.extend([pattern, pattern, pattern, pattern, pattern])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT * FROM leads
        {where_sql}
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?;
    """
    params.extend([max(1, limit), max(0, offset)])

    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]


def get_lead_matches(lead_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves all property matches for a specific lead, ordered by match percentage."""
    if not lead_id:
        return []
    initialize_database(db_path)

    query = """
        SELECT * FROM lead_property_matches
        WHERE lead_id = ?
        ORDER BY COALESCE(match_percentage, 0) DESC, id ASC;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(query, (str(lead_id).strip(),))
        return [dict(r) for r in cursor.fetchall()]


def get_dashboard_statistics(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregates metrics and distributions directly from the database for the broker dashboard.
    Safe on empty databases (returns zeroed statistics).
    """
    initialize_database(db_path)

    stats: Dict[str, Any] = {
        "total_leads": 0,
        "hot_leads": 0,
        "warm_leads": 0,
        "cold_leads": 0,
        "escalated_leads": 0,
        "pending_followups": 0,
        "discarded_leads": 0,
        "avg_score": 0.0,
        "quality_distribution": {},
        "action_distribution": {},
        "status_distribution": {}
    }

    with get_db_connection(db_path) as conn:
        # Total and averages
        cursor = conn.execute("SELECT COUNT(*) AS total, AVG(lead_score) AS avg_score FROM leads;")
        row = cursor.fetchone()
        if row:
            stats["total_leads"] = row["total"] or 0
            stats["avg_score"] = round(row["avg_score"] or 0.0, 1)

        # Lead quality breakdown
        cursor = conn.execute("""
            SELECT UPPER(COALESCE(lead_quality, 'UNASSIGNED')) as quality, COUNT(*) as cnt
            FROM leads
            GROUP BY quality;
        """)
        for r in cursor.fetchall():
            q = r["quality"]
            c = r["cnt"]
            stats["quality_distribution"][q] = c
            if q == "HOT":
                stats["hot_leads"] += c
            elif q == "WARM":
                stats["warm_leads"] += c
            elif q in ("COLD", "NURTURE", "LOW PRIORITY", "LOW_PRIORITY"):
                stats["cold_leads"] += c

        # Next action breakdown
        cursor = conn.execute("""
            SELECT COALESCE(next_action, 'UNASSIGNED') as action, COUNT(*) as cnt
            FROM leads
            GROUP BY action;
        """)
        for r in cursor.fetchall():
            a = r["action"]
            c = r["cnt"]
            stats["action_distribution"][a] = c
            if a == "ESCALATE_TO_BROKER":
                stats["escalated_leads"] += c
            elif a in ("CONTINUE_QUALIFICATION", "FOLLOW_UP_LATER", "SEND_PROPERTY_SHORTLIST", "REQUEST_INFORMATION"):
                stats["pending_followups"] += c
            elif a in ("DISCARD", "LOW_PRIORITY"):
                stats["discarded_leads"] += c

        # Status breakdown
        cursor = conn.execute("""
            SELECT COALESCE(status, 'NEW') as status_val, COUNT(*) as cnt
            FROM leads
            GROUP BY status_val;
        """)
        for r in cursor.fetchall():
            stats["status_distribution"][r["status_val"]] = r["cnt"]

    return stats
