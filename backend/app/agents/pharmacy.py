"""
Klinik — Pharmacy Agent
Drafts prescriptions with drug interaction checking.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, Prescription
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "pharmacy"

SYSTEM_PROMPT = """You are the Pharmacy Agent for Klinik.
Given clinical context and prescribed medications, formalise each prescription with:
- Proper medication name
- Dosage, frequency, duration, route
- Patient instructions
- Drug interaction warnings (check against other medications and patient conditions)

Return valid JSON:
{
  "prescriptions": [
    {"medication": "", "dosage": "", "frequency": "", "duration": "", "route": "oral", "instructions": "", "interaction_warnings": []}
  ],
  "note": "Any additional pharmacy notes"
}"""


async def run_pharmacy_agent(state: ClinicalState) -> ClinicalState:
    """Agent 5 — Pharmacy (Parallel Phase 2) — Drafts Rx, checks interactions."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)

    if not state.prescriptions:
        state.set_agent_status(AGENT_NAME, AgentStatus.SKIPPED, output="No prescriptions detected")
        return state

    logger.info(f"[{AGENT_NAME}] Processing {len(state.prescriptions)} prescriptions...")

    try:
        context = (
            f"Patient: {state.patient.name}, {state.patient.age}yo {state.patient.sex}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Prescriptions: {json.dumps([p.model_dump() for p in state.prescriptions])}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.1,
            max_tokens=512,   # prescriptions JSON
            json_mode=True,
        )

        data = json.loads(response)
        if "prescriptions" in data:
            state.prescriptions = [Prescription(**p) for p in data["prescriptions"]]

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Processed {len(state.prescriptions)} prescriptions"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
