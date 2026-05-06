"""
Klinik — Scheduling Agent
Books follow-up appointments and notifies patients.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, FollowUp
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "scheduling"

SYSTEM_PROMPT = """You are the Scheduling Agent for Klinik.
Given a follow-up request from a clinical consultation, determine the appointment details.

Return valid JSON:
{
  "appointment": {
    "date": "YYYY-MM-DD",
    "time": "HH:MM",
    "reason": "Brief reason for follow-up",
    "scheduled": true
  }
}

Use the recommended date from the doctor. If the doctor said 'tomorrow', calculate based on today's date."""


async def run_scheduling_agent(state: ClinicalState) -> ClinicalState:
    """Agent 7 — Scheduling (Parallel Phase 2) — Books follow-up appointments."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)

    if not state.follow_up.recommended_date and not state.follow_up.reason:
        state.set_agent_status(AGENT_NAME, AgentStatus.SKIPPED, output="No follow-up requested")
        return state

    logger.info(f"[{AGENT_NAME}] Scheduling follow-up appointment...")

    try:
        context = (
            f"Patient: {state.patient.name}\n"
            f"Follow-up requested: {state.follow_up.recommended_date}\n"
            f"Reason: {state.follow_up.reason}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.1,
            json_mode=True,
        )

        data = json.loads(response)
        if "appointment" in data:
            appt = data["appointment"]
            state.follow_up = FollowUp(
                recommended_date=appt.get("date", state.follow_up.recommended_date),
                reason=appt.get("reason", state.follow_up.reason),
                scheduled=appt.get("scheduled", True),
            )

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Follow-up scheduled: {state.follow_up.recommended_date}"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
