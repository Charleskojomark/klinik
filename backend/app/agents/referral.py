"""
Klinik — Referral Agent
Drafts and sends referral letters to specialists.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "referral"

SYSTEM_PROMPT = """You are the Referral Agent for Klinik.
Generate a professional referral letter for each referral request.

Return valid JSON:
{
  "referral_letter": "The complete referral letter text, properly formatted with:\n- Date\n- To: Department/Provider\n- Re: Patient name, age, sex\n- Clinical summary\n- Reason for referral\n- Urgency\n- Referring physician signature line"
}"""


async def run_referral_agent(state: ClinicalState) -> ClinicalState:
    """Agent 6 — Referral (Parallel Phase 2) — Drafts referral letters."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)

    if not state.referrals:
        state.set_agent_status(AGENT_NAME, AgentStatus.SKIPPED, output="No referrals detected")
        return state

    logger.info(f"[{AGENT_NAME}] Generating {len(state.referrals)} referral letters...")

    try:
        context = (
            f"Patient: {state.patient.name}, {state.patient.age}yo {state.patient.sex}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Vitals: BP {state.vitals.blood_pressure}\n"
            f"Symptoms: {', '.join(state.symptoms)}\n"
            f"Referrals needed: {json.dumps([r.model_dump() for r in state.referrals])}\n"
            f"Clinical plan: {state.clinical_plan}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.3,
            json_mode=True,
        )

        data = json.loads(response)
        # Store the referral letter in the first referral's clinical_summary
        if "referral_letter" in data and state.referrals:
            state.referrals[0].clinical_summary = data["referral_letter"]

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Generated {len(state.referrals)} referral letters"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
