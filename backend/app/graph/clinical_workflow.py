"""
Klinik — LangGraph Clinical Workflow Graph
The core orchestration engine that runs all 10 agents in the correct order.

Architecture:
  Phase 1 (Sequential):  Transcription → Clinical NLP
  Phase 2 (Parallel):    EHR Notes, Lab Order, Pharmacy, Referral, Scheduling, Billing
  Phase 3 (Convergence): Relationship → Supervisor
"""

import asyncio
import logging
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END

from app.models.clinical_state import ClinicalState
from app.services.event_bus import get_event_bus
from app.agents.transcription import run_transcription_agent
from app.agents.clinical_nlp import run_clinical_nlp_agent
from app.agents.ehr_notes import run_ehr_notes_agent
from app.agents.lab_order import run_lab_order_agent
from app.agents.pharmacy import run_pharmacy_agent
from app.agents.referral import run_referral_agent
from app.agents.scheduling import run_scheduling_agent
from app.agents.billing_coding import run_billing_coding_agent
from app.agents.relationship import run_relationship_agent
from app.agents.supervisor import run_supervisor_agent

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# LangGraph State Type
# We use a dict-based state that wraps ClinicalState
# ──────────────────────────────────────────────

class GraphState(TypedDict):
    clinical_state: ClinicalState


# ──────────────────────────────────────────────
# Node Wrappers — adapt agents to LangGraph node signature
# ──────────────────────────────────────────────

async def transcription_node(state: GraphState) -> GraphState:
    """Phase 1, Node 1: Transcription"""
    cs = state["clinical_state"]
    eb = await get_event_bus()
    await eb.publish_agent_event(cs.session_id, "transcription", "running")
    cs = await run_transcription_agent(cs)
    await eb.publish_agent_event(cs.session_id, "transcription", "completed")
    return {"clinical_state": cs}


async def clinical_nlp_node(state: GraphState) -> GraphState:
    """Phase 1, Node 2: Clinical NLP — extract entities"""
    cs = state["clinical_state"]
    eb = await get_event_bus()
    await eb.publish_agent_event(cs.session_id, "clinical_nlp", "running")
    cs = await run_clinical_nlp_agent(cs)
    await eb.publish_agent_event(cs.session_id, "clinical_nlp", "completed")
    return {"clinical_state": cs}


async def parallel_agents_node(state: GraphState) -> GraphState:
    """
    Phase 2: All 6 agents fire in PARALLEL.
    This is the key performance advantage — all admin work happens simultaneously.
    """
    cs = state["clinical_state"]

    # Notify frontend all 6 are running concurrently
    eb = await get_event_bus()
    for agent in ["ehr_notes", "lab_order", "pharmacy", "referral", "scheduling", "billing_coding"]:
        await eb.publish_agent_event(cs.session_id, agent, "running")

    # Run all Phase 2 agents concurrently
    results = await asyncio.gather(
        run_ehr_notes_agent(cs.model_copy(deep=True)),
        run_lab_order_agent(cs.model_copy(deep=True)),
        run_pharmacy_agent(cs.model_copy(deep=True)),
        run_referral_agent(cs.model_copy(deep=True)),
        run_scheduling_agent(cs.model_copy(deep=True)),
        run_billing_coding_agent(cs.model_copy(deep=True)),
        return_exceptions=True,
    )

    # Merge results back into the master state
    ehr_result, lab_result, pharma_result, ref_result, sched_result, bill_result = results

    if isinstance(ehr_result, ClinicalState):
        cs.soap_note = ehr_result.soap_note
        cs.agent_results.extend([r for r in ehr_result.agent_results if r.agent_name == "ehr_notes"])

    if isinstance(lab_result, ClinicalState):
        cs.lab_orders = lab_result.lab_orders
        cs.agent_results.extend([r for r in lab_result.agent_results if r.agent_name == "lab_order"])

    if isinstance(pharma_result, ClinicalState):
        cs.prescriptions = pharma_result.prescriptions
        cs.agent_results.extend([r for r in pharma_result.agent_results if r.agent_name == "pharmacy"])

    if isinstance(ref_result, ClinicalState):
        cs.referrals = ref_result.referrals
        cs.agent_results.extend([r for r in ref_result.agent_results if r.agent_name == "referral"])

    if isinstance(sched_result, ClinicalState):
        cs.follow_up = sched_result.follow_up
        cs.agent_results.extend([r for r in sched_result.agent_results if r.agent_name == "scheduling"])

    if isinstance(bill_result, ClinicalState):
        cs.billing = bill_result.billing
        cs.agent_results.extend([r for r in bill_result.agent_results if r.agent_name == "billing_coding"])

    # Notify frontend they are all done
    for agent in ["ehr_notes", "lab_order", "pharmacy", "referral", "scheduling", "billing_coding"]:
        await eb.publish_agent_event(cs.session_id, agent, "completed")

    return {"clinical_state": cs}


async def relationship_node(state: GraphState) -> GraphState:
    """Phase 3, Node 1: Patient relationship / SMS"""
    cs = state["clinical_state"]
    cs = await run_relationship_agent(cs)
    return {"clinical_state": cs}


async def supervisor_node(state: GraphState) -> GraphState:
    """Phase 3, Node 2: Supervisor — final confirmation"""
    cs = state["clinical_state"]
    cs = await run_supervisor_agent(cs)
    return {"clinical_state": cs}


# ──────────────────────────────────────────────
# Build the Graph
# ──────────────────────────────────────────────

def build_clinical_graph() -> StateGraph:
    """
    Construct the LangGraph state graph for the clinical workflow.
    
    Flow:
      transcription → clinical_nlp → parallel_agents → relationship → supervisor → END
    """
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("transcription", transcription_node)
    graph.add_node("clinical_nlp", clinical_nlp_node)
    graph.add_node("parallel_agents", parallel_agents_node)
    graph.add_node("relationship", relationship_node)
    graph.add_node("supervisor", supervisor_node)

    # Define edges — sequential flow
    graph.set_entry_point("transcription")
    graph.add_edge("transcription", "clinical_nlp")
    graph.add_edge("clinical_nlp", "parallel_agents")
    graph.add_edge("parallel_agents", "relationship")
    graph.add_edge("relationship", "supervisor")
    graph.add_edge("supervisor", END)

    return graph.compile()


# ──────────────────────────────────────────────
# Run the graph
# ──────────────────────────────────────────────

async def run_clinical_workflow(clinical_state: ClinicalState) -> ClinicalState:
    """
    Execute the full clinical workflow for a consultation.
    Returns the completed ClinicalState with all agent outputs.
    """
    logger.info(f"🏥 Starting clinical workflow for session: {clinical_state.session_id}")

    graph = build_clinical_graph()

    initial_state: GraphState = {"clinical_state": clinical_state}
    final_state = await graph.ainvoke(initial_state)

    result = final_state["clinical_state"]
    logger.info(f"✅ Workflow complete: {result.supervisor_summary}")

    return result
