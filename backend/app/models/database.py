"""
Klinik — Database Layer (Turso / libSQL)
Persists clinical states and patient records for the patient history panel.
Falls back gracefully to SQLite on disk when Turso is not configured.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)

_conn = None


async def _get_conn():
    global _conn
    if _conn is not None:
        return _conn

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
            _conn = libsql.connect("klinik_local.db")
            logger.info("🗄️  Using local SQLite database (Turso token not set)")
    except Exception as e:
        logger.warning(f"libsql not available ({e}), falling back to stdlib sqlite3")
        import sqlite3
        _conn = sqlite3.connect("klinik_local.db", check_same_thread=False)

    return _conn


async def init_db():
    """Create tables if they don't exist."""
    conn = await _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id TEXT PRIMARY KEY,
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
                created_at TEXT
            )
        """)
        conn.commit()
        logger.info("🗄️  Database tables ready")
    except Exception as e:
        logger.error(f"DB init error: {e}")


async def save_clinical_state(state) -> None:
    """Persist a completed ClinicalState to the database."""
    conn = await _get_conn()
    try:
        # Upsert patient
        conn.execute("""
            INSERT OR REPLACE INTO patients (id, name, age, sex, phone, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            state.patient.patient_id,
            state.patient.name or "Unknown Patient",
            state.patient.age,
            state.patient.sex or "Unknown",
            state.patient.phone or "",
            datetime.utcnow().isoformat(),
        ))

        # Upsert encounter
        conn.execute("""
            INSERT OR REPLACE INTO encounters
            (id, patient_id, patient_name, doctor_id, transcript, supervisor_summary,
             soap_note, diagnoses, lab_orders, prescriptions, referrals, follow_up, billing,
             visit_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.session_id,
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
            state.created_at.isoformat(),
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to save clinical state: {e}")
        raise


def _row_to_patient(row) -> dict:
    return {
        "id": row[0], "name": row[1], "age": row[2],
        "sex": row[3], "phone": row[4], "created_at": row[5],
    }


def _row_to_encounter(row) -> dict:
    return {
        "id": row[0], "patient_id": row[1], "patient_name": row[2],
        "doctor_id": row[3], "transcript": row[4],
        "supervisor_summary": row[5],
        "soap_note":    _safe_json(row[6], {}),
        "diagnoses":    _safe_json(row[7], []),
        "lab_orders":   _safe_json(row[8], []),
        "prescriptions": _safe_json(row[9], []),
        "referrals":    _safe_json(row[10], []),
        "follow_up":    _safe_json(row[11], {}),
        "billing":      _safe_json(row[12], {}),
        "visit_status": row[13],
        "created_at":   row[14],
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
        cursor = conn.execute("SELECT * FROM patients ORDER BY created_at DESC")
        return [_row_to_patient(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"get_all_patients error: {e}")
        return []


async def get_patient(patient_id: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
        row = cursor.fetchone()
        if not row:
            return None
        patient = _row_to_patient(row)
        # Include encounter history
        enc_cursor = conn.execute(
            "SELECT * FROM encounters WHERE patient_id = ? ORDER BY created_at DESC",
            (patient_id,)
        )
        patient["encounters"] = [_row_to_encounter(r) for r in enc_cursor.fetchall()]
        return patient
    except Exception as e:
        logger.error(f"get_patient error: {e}")
        return None


async def get_all_encounters() -> list[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("SELECT * FROM encounters ORDER BY created_at DESC")
        return [_row_to_encounter(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"get_all_encounters error: {e}")
        return []


async def get_encounter(encounter_id: str) -> Optional[dict]:
    conn = await _get_conn()
    try:
        cursor = conn.execute("SELECT * FROM encounters WHERE id = ?", (encounter_id,))
        row = cursor.fetchone()
        return _row_to_encounter(row) if row else None
    except Exception as e:
        logger.error(f"get_encounter error: {e}")
        return None
