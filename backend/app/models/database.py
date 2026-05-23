"""
Klinik — Database Layer (Turso / libSQL / SQLite fallback)
Persists clinical states and patient records for the patient history panel.

Fixes applied:
  - DB path moved to /app/data/klinik.db (explicit, survives volume mounts)
  - WAL mode + NORMAL synchronous (concurrent multi-process safe)
  - Connection health check — resets on broken connection
  - 30s busy timeout to survive SQLite lock contention
"""

import json
import logging
import os
from datetime import datetime
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)

# Explicit path inside the data volume (docker-compose maps ./data → /app/data)
_DB_PATH = os.environ.get("DB_PATH", "/app/data/klinik.db")

_conn = None


def _make_conn():
    """Create a fresh SQLite connection with WAL mode and named column access."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    import sqlite3
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=30)
    # Row factory: allows dict-style access (row["column_name"])
    # This is CRITICAL — without it, SELECT * with ALTER TABLE migrations
    # returns columns in the wrong order (migrations append to end).
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.commit()
    logger.info(f"🗄️  SQLite connected: {_DB_PATH} (WAL mode, named rows)")
    return conn


async def _get_conn():
    global _conn

    # Validate existing connection is still usable
    if _conn is not None:
        try:
            _conn.execute("SELECT 1")
            return _conn
        except Exception:
            logger.warning("🗄️  DB connection broken — reconnecting")
            _conn = None

    settings = get_settings()

    try:
        import libsql_experimental as libsql  # type: ignore

        if settings.turso_auth_token:
            _conn = libsql.connect(
                database=settings.database_url,
                auth_token=settings.turso_auth_token,
            )
            logger.info("🗄️  Connected to Turso cloud database")
        else:
            _conn = _make_conn()
    except Exception as e:
        logger.warning(f"libsql not available ({e}), using stdlib sqlite3")
        _conn = _make_conn()

    return _conn


async def init_db():
    """Create tables if they don't exist. Also runs safe migrations for older schemas."""
    conn = await _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                name TEXT,
                age INTEGER,
                sex TEXT,
                phone TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS encounters (
                id TEXT PRIMARY KEY,
                tenant_id TEXT,
                patient_id TEXT,
                patient_name TEXT,
                doctor_id TEXT,
                transcript TEXT,
                supervisor_summary TEXT,
                soap_note TEXT,
                diagnoses TEXT,
                lab_orders TEXT,
                prescriptions TEXT,
                referrals TEXT,
                follow_up TEXT,
                billing TEXT,
                visit_status TEXT,
                is_signed_off BOOLEAN,
                signed_by_doctor_id TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                ip_address TEXT,
                endpoint TEXT,
                method TEXT,
                status_code INTEGER,
                duration_ms REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                role TEXT,
                name TEXT,
                created_at TEXT
            )
        """)
        conn.commit()

        # Seed demo users if empty
        cursor = conn.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            from app.services.auth import hash_password
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("admin-default", "admin", hash_password("adminpassword123"), "admin", "System Administrator", datetime.utcnow().isoformat())
            )
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("dr-eze", "doctor", hash_password("doctorpassword123"), "doctor", "Dr. Amadi Eze", datetime.utcnow().isoformat())
            )
            conn.execute(
                "INSERT INTO users (id, username, password_hash, role, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("nurse-jane", "nurse", hash_password("nursepassword123"), "nurse", "Nurse Jane Obi", datetime.utcnow().isoformat())
            )
            conn.commit()
            logger.info("🗄️  Database seeded with default demo users")


        # Safe migrations — add columns that may be missing from older schema versions
        _safe_add_column(conn, "patients",   "tenant_id",          "TEXT")
        _safe_add_column(conn, "patients",   "phone",              "TEXT")
        _safe_add_column(conn, "patients",   "age",                "INTEGER")
        _safe_add_column(conn, "patients",   "sex",                "TEXT")
        _safe_add_column(conn, "encounters", "tenant_id",          "TEXT")
        _safe_add_column(conn, "encounters", "patient_name",       "TEXT")
        _safe_add_column(conn, "encounters", "soap_note",          "TEXT")
        _safe_add_column(conn, "encounters", "diagnoses",          "TEXT")
        _safe_add_column(conn, "encounters", "lab_orders",         "TEXT")
        _safe_add_column(conn, "encounters", "prescriptions",      "TEXT")
        _safe_add_column(conn, "encounters", "referrals",          "TEXT")
        _safe_add_column(conn, "encounters", "follow_up",          "TEXT")
        _safe_add_column(conn, "encounters", "billing",            "TEXT")
        _safe_add_column(conn, "encounters", "supervisor_summary", "TEXT")
        _safe_add_column(conn, "encounters", "visit_status",       "TEXT")
        _safe_add_column(conn, "encounters", "doctor_id",          "TEXT")
        _safe_add_column(conn, "encounters", "transcript",         "TEXT")
        _safe_add_column(conn, "encounters", "is_signed_off",      "BOOLEAN")
        _safe_add_column(conn, "encounters", "signed_by_doctor_id","TEXT")

        logger.info("🗄️  Database tables ready")
    except Exception as e:
        logger.error(f"DB init error: {e}")


def _safe_add_column(conn, table: str, column: str, col_type: str):
    """Add a column to a table if it doesn't already exist (idempotent migration)."""
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        conn.commit()
        logger.info(f"🗄️  Migrated: added {table}.{column}")
    except Exception:
        pass  # Column already exists — safe to ignore


async def save_clinical_state(state) -> None:
    """Persist a completed ClinicalState to the database."""
    conn = await _get_conn()
    try:
        # Upsert patient
        conn.execute("""
            INSERT OR REPLACE INTO patients (id, tenant_id, name, age, sex, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            state.patient.patient_id,
            state.patient.tenant_id,
            state.patient.name or "Unknown Patient",
            state.patient.age,
            state.patient.sex or "Unknown",
            state.patient.phone or "",
            datetime.utcnow().isoformat(),
        ))

        # Upsert encounter
        conn.execute("""
            INSERT OR REPLACE INTO encounters
            (id, tenant_id, patient_id, patient_name, doctor_id, transcript, supervisor_summary,
             soap_note, diagnoses, lab_orders, prescriptions, referrals, follow_up, billing,
             visit_status, is_signed_off, signed_by_doctor_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.session_id,
            state.tenant_id,
            state.patient.patient_id,
            state.patient.name or "Unknown Patient",
            state.doctor_id,
            state.transcript,
            state.supervisor_summary,
            json.dumps(state.soap_note.model_dump()),
            json.dumps(state.diagnoses),
            json.dumps([o.model_dump() for o in state.lab_orders]),
            json.dumps([p.model_dump() for p in state.prescriptions]),
            json.dumps([r.model_dump() for r in state.referrals]),
            json.dumps(state.follow_up.model_dump()),
            json.dumps(state.billing.model_dump()),
            state.visit_status.value,
            state.is_signed_off,
            state.signed_by_doctor_id,
            state.created_at.isoformat(),
        ))
        conn.commit()
        logger.info(f"🗄️  Saved: {state.patient.name or 'Unknown'} / {state.session_id}")
    except Exception as e:
        logger.error(f"Failed to save clinical state: {e}")
        raise


async def log_audit_event(ip_address: str, endpoint: str, method: str, status_code: int, duration_ms: float) -> None:
    """Immutable audit logging for compliance."""
    conn = await _get_conn()
    try:
        conn.execute("""
            INSERT INTO audit_logs (timestamp, ip_address, endpoint, method, status_code, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            datetime.utcnow().isoformat(),
            ip_address,
            endpoint,
            method,
            status_code,
            duration_ms
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")


# Explicit column order for SELECT queries (used in all read functions below).
# By listing columns explicitly in SELECT, the result order is always predictable
# regardless of table migration order or connection type (sqlite3, libsql, etc.).
_PATIENT_COLS  = ["id", "tenant_id", "name", "age", "sex", "phone", "created_at"]
_ENCOUNTER_COLS = [
    "id", "tenant_id", "patient_id", "patient_name", "doctor_id", "transcript",
    "supervisor_summary", "soap_note", "diagnoses", "lab_orders",
    "prescriptions", "referrals", "follow_up", "billing", "visit_status", 
    "is_signed_off", "signed_by_doctor_id", "created_at",
]

_ENCOUNTER_SELECT = ", ".join(f"e.{c}" for c in _ENCOUNTER_COLS)
_ENCOUNTER_SELECT_BARE = ", ".join(_ENCOUNTER_COLS)


def _row_to_patient(row) -> dict:
    """Convert a row tuple to a patient dict. Positional — driven by explicit SELECT."""
    return {
        "id":              row[0],
        "tenant_id":       row[1],
        "name":            row[2],
        "age":             row[3],
        "sex":             row[4],
        "phone":           row[5],
        "created_at":      row[6],
        "encounter_count": row[7] if len(row) > 7 else 0,
    }


def _row_to_encounter(row) -> dict:
    """Convert a row tuple to an encounter dict. Positional — driven by explicit SELECT."""
    return {
        "id":                row[0],
        "tenant_id":         row[1],
        "patient_id":        row[2],
        "patient_name":      row[3] or "Unknown Patient",
        "doctor_id":         row[4],
        "transcript":        row[5],
        "supervisor_summary": row[6],
        "soap_note":         _safe_json(row[7], {}),
        "diagnoses":         _safe_json(row[8], []),
        "lab_orders":        _safe_json(row[9], []),
        "prescriptions":     _safe_json(row[10], []),
        "referrals":         _safe_json(row[11], []),
        "follow_up":         _safe_json(row[12], {}),
        "billing":           _safe_json(row[13], {}),
        "visit_status":      row[14],
        "is_signed_off":     bool(row[15]),
        "signed_by_doctor_id": row[16],
        "created_at":        row[17],
    }


def _safe_json(text: Optional[str], default):
    if not text:
        return default
    try:
        return json.loads(text)
    except Exception:
        return default


async def get_all_patients() -> list[dict]:
    conn = await _get_conn()
    try:
        # LEFT JOIN to get encounter count without a separate query per patient
        cursor = conn.execute("""
            SELECT p.id, p.tenant_id, p.name, p.age, p.sex, p.phone, p.created_at,
                   COUNT(e.id) AS encounter_count
            FROM patients p
            LEFT JOIN encounters e ON e.patient_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
        """)
        return [
            {
                "id": r[0], "tenant_id": r[1], "name": r[2], "age": r[3],
                "sex": r[4], "phone": r[5], "created_at": r[6],
                "encounter_count": r[7],
            }
            for r in cursor.fetchall()
        ]
    except Exception as e:
        logger.error(f"get_all_patients error: {e}")
        return []


async def get_patient(patient_id: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("""
            SELECT p.id, p.tenant_id, p.name, p.age, p.sex, p.phone, p.created_at,
                   COUNT(e.id) AS encounter_count
            FROM patients p
            LEFT JOIN encounters e ON e.patient_id = p.id
            WHERE p.id = ?
            GROUP BY p.id
        """, (patient_id,))
        row = cursor.fetchone()
        if not row:
            return None
        patient = {
            "id": row[0], "tenant_id": row[1], "name": row[2], "age": row[3],
            "sex": row[4], "phone": row[5], "created_at": row[6],
            "encounter_count": row[7],
        }
        # Explicit columns — immune to ALTER TABLE migration order
        enc_cursor = conn.execute("""
            SELECT id, tenant_id, patient_id, patient_name, doctor_id, transcript,
                   supervisor_summary, soap_note, diagnoses, lab_orders,
                   prescriptions, referrals, follow_up, billing, visit_status, 
                   is_signed_off, signed_by_doctor_id, created_at
            FROM encounters WHERE patient_id = ? ORDER BY created_at DESC
        """, (patient_id,))
        patient["encounters"] = [_row_to_encounter(r) for r in enc_cursor.fetchall()]
        return patient
    except Exception as e:
        logger.error(f"get_patient error: {e}")
        return None


async def get_all_encounters() -> list[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("""
            SELECT id, tenant_id, patient_id, patient_name, doctor_id, transcript,
                   supervisor_summary, soap_note, diagnoses, lab_orders,
                   prescriptions, referrals, follow_up, billing, visit_status, 
                   is_signed_off, signed_by_doctor_id, created_at
            FROM encounters ORDER BY created_at DESC
        """)
        return [_row_to_encounter(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"get_all_encounters error: {e}")
        return []


async def get_encounter(encounter_id: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("""
            SELECT id, tenant_id, patient_id, patient_name, doctor_id, transcript,
                   supervisor_summary, soap_note, diagnoses, lab_orders,
                   prescriptions, referrals, follow_up, billing, visit_status, 
                   is_signed_off, signed_by_doctor_id, created_at
            FROM encounters WHERE id = ?
        """, (encounter_id,))
        row = cursor.fetchone()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"get_encounter error: {e}")
        return None


async def get_user_by_username(username: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("SELECT id, username, password_hash, role, name, created_at FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "name": row[4],
            "created_at": row[5]
        }
    except Exception as e:
        logger.error(f"get_user_by_username error: {e}")
        return None


async def get_user_by_id(user_id: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("SELECT id, username, password_hash, role, name, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "role": row[3],
            "name": row[4],
            "created_at": row[5]
        }
    except Exception as e:
        logger.error(f"get_user_by_id error: {e}")
        return None

