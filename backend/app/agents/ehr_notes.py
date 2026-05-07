"""
Klinik — EHR Notes Agent
Generates a complete SOAP note from the clinical NLP extraction.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, SOAPNote
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "ehr_notes"

SYSTEM_PROMPT = """You are the EHR Notes Agent for Klinik.
Generate a professional SOAP note from the following clinical data.

You MUST return ONLY a valid JSON object with exactly these 4 keys:
{"subjective": "...", "objective": "...", "assessment": "...", "plan": "..."}

Rules:
- Each value must be a single string (use \\n for newlines within a field)
- Do NOT use markdown, code fences, or any formatting
- Do NOT include any text before or after the JSON object
- Write in clear, professional medical documentation style"""


async def run_ehr_notes_agent(state: ClinicalState) -> ClinicalState:
    """Agent 3 — EHR Notes (Parallel Phase 2) — Writes SOAP note."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Generating SOAP note...")

    try:
        clinical_context = (
            f"Patient: {state.patient.name}, {state.patient.age}yo {state.patient.sex}\n"
            f"Vitals: BP {state.vitals.blood_pressure}\n"
            f"Symptoms: {', '.join(state.symptoms)}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Plan: {state.clinical_plan}\n"
            f"Transcript: {state.transcript}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=clinical_context,
            temperature=0.2,
            max_tokens=512,   # SOAP note — 4 short fields
            json_mode=True,
        )

        data = json.loads(response)
        state.soap_note = SOAPNote(**data)

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output="SOAP note generated successfully"
        )

    except json.JSONDecodeError as e:
        logger.warning(f"[{AGENT_NAME}] JSON parse failed: {e}. Using fallback SOAP note.")
        # Build a reasonable fallback SOAP note from the available data
        state.soap_note = SOAPNote(
            subjective=f"{state.patient.name}, {state.patient.age}yo {state.patient.sex}. {state.transcript[:200]}",
            objective=f"BP {state.vitals.blood_pressure}. Symptoms: {', '.join(state.symptoms)}.",
            assessment=f"Diagnoses: {', '.join(state.diagnoses)}.",
            plan=state.clinical_plan or "See clinical plan.",
        )
        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output="SOAP note generated (fallback)"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
