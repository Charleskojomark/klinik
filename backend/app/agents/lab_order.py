"""
Klinik — Lab Order Agent
Processes and formalises laboratory test orders extracted from speech.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, LabOrder, Urgency
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "lab_order"

SYSTEM_PROMPT = """You are the Lab Order Agent for Klinik.
Given clinical context and extracted lab orders, formalise each order with:
- Proper test name (standardised)
- Urgency level  
- Clinical indication
- A generated order ID (format: LAB-YYYY-NNN)

Return valid JSON:
{
  "orders": [
    {"test_name": "", "urgency": "routine|urgent|stat", "clinical_indication": "", "order_id": ""}
  ]
}"""


async def run_lab_order_agent(state: ClinicalState) -> ClinicalState:
    """Agent 4 — Lab Order (Parallel Phase 2) — Formalises lab orders."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)

    if not state.lab_orders:
        state.set_agent_status(AGENT_NAME, AgentStatus.SKIPPED, output="No lab orders detected")
        return state

    logger.info(f"[{AGENT_NAME}] Processing {len(state.lab_orders)} lab orders...")

    try:
        context = (
            f"Patient: {state.patient.name}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Orders requested: {json.dumps([o.model_dump() for o in state.lab_orders])}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.1,
            max_tokens=256,   # lab order JSON — very short output
            json_mode=True,
        )

        data = json.loads(response)
        if "orders" in data:
            state.lab_orders = [
                LabOrder(
                    test_name=o["test_name"],
                    urgency=Urgency(o.get("urgency", "routine")),
                    clinical_indication=o.get("clinical_indication", ""),
                    order_id=o.get("order_id"),
                )
                for o in data["orders"]
            ]

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Processed {len(state.lab_orders)} lab orders"
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
