"""
Klinik — Relationship Agent
Maintains patient communication via Twilio SMS.
Sends appointment reminders, test results, and care check-ins.
"""

import json
import logging
from app.models.clinical_state import ClinicalState, AgentStatus, SMSMessage
from app.services.llm_client import llm_chat
from app.config import get_settings

logger = logging.getLogger(__name__)

AGENT_NAME = "relationship"

SYSTEM_PROMPT = """You are the Patient Relationship Agent for Klinik.
Generate a warm, professional SMS message to the patient about their visit.

The message should:
- Be written in plain, understandable language (not medical jargon)
- Be concise (under 160 characters if possible, max 320)
- Include the patient's first name
- Summarise what happened (admission, tests ordered, follow-up scheduled)
- Be reassuring and caring
- End with the clinic signature

Return valid JSON:
{
  "message": "The SMS message text"
}"""


async def run_relationship_agent(state: ClinicalState) -> ClinicalState:
    """Agent 9 — Relationship (Parallel Phase 2) — Patient SMS via Twilio."""
    state.set_agent_status(AGENT_NAME, AgentStatus.RUNNING)
    logger.info(f"[{AGENT_NAME}] Composing patient message...")

    try:
        context = (
            f"Patient: {state.patient.name}\n"
            f"Diagnoses: {', '.join(state.diagnoses)}\n"
            f"Actions taken:\n"
            f"- Lab orders: {[o.test_name for o in state.lab_orders]}\n"
            f"- Referrals: {[r.to_department for r in state.referrals]}\n"
            f"- Follow-up: {state.follow_up.recommended_date}\n"
            f"- Prescriptions: {[p.medication for p in state.prescriptions]}"
        )

        response = await llm_chat(
            system_prompt=SYSTEM_PROMPT,
            user_message=context,
            temperature=0.5,
            max_tokens=192,   # SMS message — max 320 chars
            json_mode=True,
        )

        data = json.loads(response)
        sms_body = data.get("message", "")

        if sms_body and state.patient.phone:
            sms = SMSMessage(
                to_number=state.patient.phone,
                body=sms_body,
            )

            # Send via Twilio if configured
            settings = get_settings()
            if settings.twilio_account_sid and settings.twilio_auth_token:
                await _send_twilio_sms(sms, settings)
            else:
                logger.info(f"[{AGENT_NAME}] Twilio not configured — SMS queued but not sent")

            state.sms_messages.append(sms)

        elif sms_body:
            # No phone number — still store the message
            state.sms_messages.append(SMSMessage(body=sms_body))
            logger.info(f"[{AGENT_NAME}] No phone number — message stored but not sent")

        state.set_agent_status(
            AGENT_NAME, AgentStatus.COMPLETED,
            output=f"Patient message composed: {sms_body[:80]}..."
        )

    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Failed: {e}")
        state.set_agent_status(AGENT_NAME, AgentStatus.FAILED, error=str(e))

    return state


async def _send_twilio_sms(sms: SMSMessage, settings):
    """Send an SMS via Twilio REST API (non-blocking via asyncio.to_thread)."""
    import asyncio
    from twilio.rest import Client

    def _send():
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        return client.messages.create(
            body=sms.body,
            from_=settings.twilio_from_number,
            to=sms.to_number,
        )

    try:
        message = await asyncio.to_thread(_send)
        sms.sent = True
        from datetime import datetime
        sms.sent_at = datetime.utcnow()
        logger.info(f"[{AGENT_NAME}] SMS sent: {message.sid}")
    except Exception as e:
        logger.error(f"[{AGENT_NAME}] Twilio SMS failed: {e}")

