"""
Klinik — Supervisor Agent
Collects all agent outputs, confirms to the doctor, and flags exceptions.
In production, speaks the summary via Simli photorealistic avatar.
"""

import logging
from app.models.clinical_state import ClinicalState, AgentStatus, VisitStatus

logger = logging.getLogger(__name__)

AGENT_NAME = "supervisor"


async def run_supervisor_agent(state: ClinicalState) -> ClinicalState:
    """
    Agent 10 — Supervisor (Phase 3 — Convergence)
    
    Collects all agent results, generates a confirmation summary,
    and flags any exceptions. In production, this text is fed to
    the Simli avatar for spoken confirmation.
    """
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Compiling final summary...")

    try:
        # Collect results
        completed = []
        failed = []
        skipped = []

        for result in state.agent_results:
            if result.agent_name == AGENT_NAME:
                continue
            if result.status == AgentStatus.COMPLETED:
                completed.append(result.agent_name)
            elif result.status == AgentStatus.FAILED:
                failed.append(f"{result.agent_name}: {result.error}")
            elif result.status == AgentStatus.SKIPPED:
                skipped.append(result.agent_name)

        # Build a rich, clinical-first summary
        parts = []

        # 1. Patient identification
        patient_name = state.patient.name or "The patient"
        age_sex = ""
        if state.patient.age:
            age_sex += f", {state.patient.age}"
        if state.patient.sex:
            age_sex += state.patient.sex

        # 2. Lead with the clinical assessment (the most important thing)
        if state.soap_note.assessment:
            parts.append(f"{patient_name}{age_sex}. Assessment: {state.soap_note.assessment.strip()}")
        else:
            parts.append(f"Consultation complete for {patient_name}{age_sex}.")

        # 3. Key subjective findings
        if state.soap_note.subjective:
            # Pull just the first sentence to keep it concise
            first_sentence = state.soap_note.subjective.split('.')[0].strip()
            if first_sentence:
                parts.append(f"Subjective: {first_sentence}.")

        # 4. Diagnoses
        if state.diagnoses:
            dx_list = ", ".join(state.diagnoses[:3])  # top 3
            parts.append(f"Diagnoses: {dx_list}.")

        # 5. Plan highlights
        if state.soap_note.plan:
            first_plan = state.soap_note.plan.split('\n')[0].strip().lstrip('1234567890.) ')
            if first_plan:
                parts.append(f"Plan initiated: {first_plan}.")

        # 6. Lab orders
        if state.lab_orders:
            lab_names = ", ".join(o.test_name for o in state.lab_orders[:2])
            parts.append(f"Labs ordered: {lab_names}.")

        # 7. Prescriptions
        if state.prescriptions:
            rx_names = ", ".join(f"{p.drug_name} {p.dosage}" for p in state.prescriptions[:2])
            parts.append(f"Prescribed: {rx_names}.")

        # 8. Referrals
        if state.referrals:
            ref_depts = ", ".join(r.to_department for r in state.referrals)
            parts.append(f"Referred to: {ref_depts}.")

        # 9. Follow-up
        if state.follow_up.scheduled and state.follow_up.recommended_date:
            parts.append(f"Follow-up: {state.follow_up.recommended_date}.")

        # 10. Admin close-out (brief)
        admin = []
        if state.sms_messages:
            admin.append("patient notified")
        if state.billing.icd10_codes:
            admin.append(f"{len(state.billing.icd10_codes)} ICD-10 coded")
        if admin:
            parts.append(f"Admin: {', '.join(admin)}. Your next patient is ready.")
        else:
            parts.append("Your next patient is ready.")

        summary = " ".join(parts)

        # Flag exceptions
        if failed:
            summary += f" ⚠️ Exceptions: {'; '.join(failed)}"

        state.supervisor_summary = summary
        state.visit_status = VisitStatus.COMPLETED

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=summary
        )

        logger.info(f"[{AGENT_NAME}] Summary: {summary}")

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state
