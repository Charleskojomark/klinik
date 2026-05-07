"""
Klinik — Clinical NLP Agent
Extracts structured clinical entities from the doctor's transcript.
This is the critical agent that turns speech into structured data for all downstream agents.
"""

import re
import json
import logging
from app.models.clinical_state import (
    ClinicalState, AgentStatus, PatientInfo, VitalSigns,
    LabOrder, Prescription, Referral, FollowUp, Urgency,
)
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "clinical_nlp"


def _to_int(val) -> int | None:
    """Coerce LLM output to int, returning None for descriptive strings like 'fast'."""
    if val is None:
        return None
    try:
        # Handle strings like "72 bpm", "120/80" (take first number)
        match = re.search(r'\d+', str(val))
        return int(match.group()) if match else None
    except Exception:
        return None


def _to_float(val) -> float | None:
    """Coerce LLM output to float, returning None on failure."""
    if val is None:
        return None
    try:
        match = re.search(r'[\d.]+', str(val))
        return float(match.group()) if match else None
    except Exception:
        return None


def _safe_vitals(v: dict) -> VitalSigns:
    """Build a VitalSigns safely, converting any descriptive strings to None."""
    return VitalSigns(
        blood_pressure=str(v["blood_pressure"]) if v.get("blood_pressure") else None,
        heart_rate=_to_int(v.get("heart_rate")),
        temperature=_to_float(v.get("temperature")),
        respiratory_rate=_to_int(v.get("respiratory_rate")),
        spo2=_to_int(v.get("spo2")),
        weight=_to_float(v.get("weight")),
    )


SYSTEM_PROMPT = """You are a Clinical NLP extraction engine for Klinik.
You receive a doctor's spoken transcript from a patient consultation.
Extract ALL structured clinical information into the following JSON format.

IMPORTANT: Extract exactly what the doctor says. Do not infer or add information not present.

Return valid JSON with these fields:
{
  "patient": {"name": "", "age": null, "sex": ""},
  "vitals": {"blood_pressure": "", "heart_rate": null, "temperature": null},
  "symptoms": [],
  "diagnoses": [],
  "clinical_plan": "",
  "lab_orders": [{"test_name": "", "urgency": "routine|urgent|stat", "clinical_indication": ""}],
  "prescriptions": [{"medication": "", "dosage": "", "frequency": "", "duration": "", "route": "oral", "instructions": ""}],
  "referrals": [{"to_department": "", "urgency": "routine|urgent|stat", "reason": ""}],
  "follow_up": {"recommended_date": "", "reason": ""}
}

Only include items that the doctor explicitly mentions. Leave arrays empty if no items are mentioned."""


async def run_clinical_nlp_agent(state: ClinicalState) -> ClinicalState:
    """
    Agent 2 — Clinical NLP (Sequential Phase 1)
    
    Takes the transcript and extracts all structured clinical entities.
    This output feeds every downstream agent in Phase 2.
    """
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Extracting clinical entities from transcript...")

    try:
        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=f"Doctor's transcript:\n\n{state.transcript}",
            temperature=0.1,
            max_tokens=1024,  # structured JSON output — 2048 was excessive
            json_mode=True,
        )

        data = json.loads(response)

        # Populate patient info
        if "patient" in data:
            p_data = data["patient"]
            if p_data.get("name"):
                state.patient.name = p_data["name"]
            if p_data.get("age"):
                state.patient.age = p_data["age"]
            if p_data.get("sex"):
                state.patient.sex = p_data["sex"]

        # Populate vitals safely — LLM sometimes returns strings like "fast"
        if "vitals" in data:
            state.vitals = _safe_vitals(data["vitals"])

        # Populate symptoms and diagnoses
        state.symptoms = data.get("symptoms", [])
        state.diagnoses = data.get("diagnoses", [])
        state.clinical_plan = data.get("clinical_plan", "")

        # Populate lab orders
        if "lab_orders" in data:
            state.lab_orders = [
                LabOrder(
                    test_name=o["test_name"],
                    urgency=Urgency(o.get("urgency", "routine")),
                    clinical_indication=o.get("clinical_indication", ""),
                )
                for o in data["lab_orders"]
            ]

        # Populate prescriptions
        if "prescriptions" in data:
            state.prescriptions = [
                Prescription(**p) for p in data["prescriptions"]
            ]

        # Populate referrals
        if "referrals" in data:
            state.referrals = [
                Referral(
                    to_department=r["to_department"],
                    urgency=Urgency(r.get("urgency", "routine")),
                    reason=r.get("reason", ""),
                )
                for r in data["referrals"]
            ]

        # Populate follow-up
        if "follow_up" in data:
            state.follow_up = FollowUp(**data["follow_up"])

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Extracted: {len(state.symptoms)} symptoms, {len(state.diagnoses)} diagnoses, "
                   f"{len(state.lab_orders)} lab orders, {len(state.prescriptions)} prescriptions, "
                   f"{len(state.referrals)} referrals"
        )
        logger.info(f"[{AGENT_NAME}] Extraction complete")

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
