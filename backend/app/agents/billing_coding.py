"""
Klinik — Billing/Coding Agent
Auto-codes visits with ICD-10 and CPT codes for billing.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, BillingCode
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "billing_coding"

SYSTEM_PROMPT = """You are the Billing/Coding Agent for Klinik.
Given clinical encounter data, generate accurate ICD-10 and CPT codes.

Return valid JSON:
{
  "icd10_codes": ["code1", "code2"],
  "icd10_descriptions": ["description1", "description2"],
  "cpt_codes": ["code1", "code2"]
}

Rules:
- Use the most specific ICD-10 code available
- Include codes for all documented diagnoses and symptoms
- CPT codes should reflect the level of service and procedures performed
- Be accurate — incorrect coding has legal implications"""


async def run_billing_coding_agent(state: ClinicalState) -> ClinicalState:
    """Agent 8 — Billing/Coding (Parallel Phase 2) — ICD-10 + CPT codes."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Generating billing codes...")

    try:
        context = (
            f"Patient: {state.patient.name}, {state.patient.age}yo {state.patient.sex}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Symptoms: {', '.join(state.symptoms)}\n"
            f"Procedures: Lab orders: {len(state.lab_orders)}, Referrals: {len(state.referrals)}\n"
            f"Clinical plan: {state.clinical_plan}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.1,
            json_mode=True,
        )

        data = json.loads(response)
        state.billing = BillingCode(
            icd10_codes=data.get("icd10_codes", []),
            icd10_descriptions=data.get("icd10_descriptions", []),
            cpt_codes=data.get("cpt_codes", []),
        )

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Coded: {len(state.billing.icd10_codes)} ICD-10, {len(state.billing.cpt_codes)} CPT"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
