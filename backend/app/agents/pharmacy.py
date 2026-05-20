"""
Klinik — Pharmacy Agent
Drafts prescriptions with drug interaction checking.
"""

import json
import logging
import asyncio
import httpx
from app.models.clinical_state import ClinicalState, AgentStatus, Prescription
from app.services.llm_client import llm_chat

logger = logging.getLogger(__name__)

AGENT_NAME = "pharmacy"

SYSTEM_PROMPT = """You are the Pharmacy Agent for Klinik.
Given clinical context and prescribed medications, formalise each prescription with:
- Proper medication name
- Dosage, frequency, duration, route
- Patient instructions

Return valid JSON:
{
  "prescriptions": [
    {"medication": "", "dosage": "", "frequency": "", "duration": "", "route": "oral", "instructions": ""}
  ],
  "note": "Any additional pharmacy notes"
}"""

async def _get_rxcui(client: httpx.AsyncClient, drug_name: str) -> str | None:
    try:
        resp = await client.get(f"https://rxnav.nlm.nih.gov/REST/rxcui.json?name={drug_name}")
        if resp.status_code == 200:
            data = resp.json()
            if "idGroup" in data and "rxnormId" in data["idGroup"]:
                return data["idGroup"]["rxnormId"][0]
    except Exception as e:
        logger.warning(f"RxNav rxcui fetch failed for {drug_name}: {e}")
    return None

async def _check_interactions(rxcuis: list[str]) -> dict:
    if len(rxcuis) < 2:
        return {}
    
    interactions = {}
    try:
        async with httpx.AsyncClient() as client:
            rxcuis_str = "+".join(rxcuis)
            resp = await client.get(f"https://rxnav.nlm.nih.gov/REST/interaction/list.json?rxcuis={rxcuis_str}")
            if resp.status_code == 200:
                data = resp.json()
                if "fullInteractionTypeGroup" in data:
                    for group in data["fullInteractionTypeGroup"]:
                        for interaction in group["fullInteractionType"]:
                            for min_concept in interaction["minConcept"]:
                                rxcui = min_concept["rxcui"]
                                desc = interaction["interactionPair"][0]["description"]
                                if rxcui not in interactions:
                                    interactions[rxcui] = []
                                interactions[rxcui].append(desc)
    except Exception as e:
        logger.warning(f"RxNav interactions fetch failed: {e}")
    return interactions


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
            parsed_prescriptions = [Prescription(**p) for p in data["prescriptions"]]
            
            # Programmatic Interaction Check using RxNav
            if parsed_prescriptions:
                async with httpx.AsyncClient() as client:
                    rxcui_tasks = [_get_rxcui(client, p.medication) for p in parsed_prescriptions]
                    rxcuis = await asyncio.gather(*rxcui_tasks)
                
                valid_rxcuis = [r for r in rxcuis if r]
                interaction_map = await _check_interactions(valid_rxcuis)
                
                # Map interactions back to prescriptions
                for p, rxcui in zip(parsed_prescriptions, rxcuis):
                    if rxcui and rxcui in interaction_map:
                        p.interaction_warnings = interaction_map[rxcui]
                        
            state.prescriptions = parsed_prescriptions

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Processed {len(state.prescriptions)} prescriptions with clinical RxNav validation."
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
