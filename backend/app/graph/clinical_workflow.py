"""
Klinik — LangGraph Clinical Workflow Graph
The core orchestration engine that runs all 10 agents in the correct order.

Architecture:
  Phase 1 (Sequential):  Transcription → Clinical NLP
  Phase 2 (Parallel):    EHR Notes, Lab Order, Pharmacy, Referral, Scheduling, Billing
  Phase 3 (Convergence): Relationship → Supervisor

Performance fixes applied:
  #2  — Graph compiled ONCE at module level (not per request)
  #8  — MemorySaver checkpointer for crash-resilience
  #9  — Event bus resolved once per workflow, not inside each node
"""

import asyncio
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.models.clinical_state import ClinicalState
from app.services.event_bus import get_event_bus, EventBus
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
# ──────────────────────────────────────────────

class GraphState(TypedDict):
    clinical_state: ClinicalState
    event_bus: EventBus   # resolved once, shared across all nodes


# ──────────────────────────────────────────────
# Node Wrappers
# ──────────────────────────────────────────────

async def transcription_node(state: GraphState) -> GraphState:
    """Phase 1, Node 1: Transcription"""
    cs, eb = state["clinical_state"], state["event_bus"]
    await eb.publish_agent_event(cs.session_id, "transcription", "running")
    cs = await run_transcription_agent(cs)
    await eb.publish_agent_event(cs.session_id, "transcription", "completed")
    return {**state, "clinical_state": cs}


async def clinical_nlp_node(state: GraphState) -> GraphState:
    """Phase 1, Node 2: Clinical NLP — extract entities"""
    cs, eb = state["clinical_state"], state["event_bus"]
    await eb.publish_agent_event(cs.session_id, "clinical_nlp", "running")
    cs = await run_clinical_nlp_agent(cs)
    await eb.publish_agent_event(cs.session_id, "clinical_nlp", "completed")
    return {**state, "clinical_state": cs}


async def parallel_agents_node(state: GraphState) -> GraphState:
    """
    Phase 2: All 6 agents fire in PARALLEL.
    This is the key performance advantage — all admin work happens simultaneously.
    """
    cs, eb = state["clinical_state"], state["event_bus"]

    # Notify frontend all 6 are running concurrently
    for agent in ["ehr_notes", "lab_order", "pharmacy", "referral", "scheduling", "billing_coding"]:
        await eb.publish_agent_event(cs.session_id, agent, "running")

    # Run all Phase 2 agents concurrently (each gets its own deep copy to avoid races)
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

    return {**state, "clinical_state": cs}


async def relationship_node(state: GraphState) -> GraphState:
    """Phase 3, Node 1: Patient relationship / SMS"""
    cs = state["clinical_state"]
    cs = await run_relationship_agent(cs)
    return {**state, "clinical_state": cs}


async def supervisor_node(state: GraphState) -> GraphState:
    """Phase 3, Node 2: Supervisor — final confirmation"""
    cs = state["clinical_state"]
    cs = await run_supervisor_agent(cs)
    return {**state, "clinical_state": cs}


# ──────────────────────────────────────────────
# Build & Compile the Graph — ONCE at import time
# #2 fix: no longer rebuilt on every request
# #8 fix: MemorySaver checkpointer for resilience
# ──────────────────────────────────────────────

def _build_and_compile() -> object:
    """
    Build and compile the LangGraph state graph.
    Called exactly once at module import — never per-request.
    """
    graph = StateGraph(GraphState)

    graph.add_node("transcription",    transcription_node)
    graph.add_node("clinical_nlp",     clinical_nlp_node)
    graph.add_node("parallel_agents",  parallel_agents_node)
    graph.add_node("relationship",     relationship_node)
    graph.add_node("supervisor",       supervisor_node)

    graph.set_entry_point("transcription")
    graph.add_edge("transcription",   "clinical_nlp")
    graph.add_edge("clinical_nlp",    "parallel_agents")
    graph.add_edge("parallel_agents", "relationship")
    graph.add_edge("relationship",    "supervisor")
    graph.add_edge("supervisor",      END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


# ── Compiled graph singleton ──
_COMPILED_GRAPH = _build_and_compile()
logger.info("✅ LangGraph clinical workflow compiled (singleton)")


# ──────────────────────────────────────────────
# Run the graph
# ──────────────────────────────────────────────

async def run_clinical_workflow(clinical_state: ClinicalState) -> ClinicalState:
    """
    Execute the full clinical workflow for a consultation.
    Returns the completed ClinicalState with all agent outputs.

    Uses the module-level compiled graph singleton (not rebuilt per request).
    Event bus is resolved once here and injected into the initial state so
    all nodes share the same instance without redundant singleton lookups.
    """
    logger.info(f"🏥 Starting clinical workflow: {clinical_state.session_id}")

    # #9 fix: resolve event bus once per workflow run
    eb = await get_event_bus()

    initial_state: GraphState = {
        "clinical_state": clinical_state,
        "event_bus": eb,
    }

    # Each session uses its own checkpointer thread_id for isolation
    config = {"configurable": {"thread_id": clinical_state.session_id}}

    final_state = await _COMPILED_GRAPH.ainvoke(initial_state, config=config)

    result: ClinicalState = final_state["clinical_state"]
    logger.info(f"✅ Workflow complete [{clinical_state.session_id}]: {result.supervisor_summary[:80]}")
    return result
