"""
Klinik — LLM Client
OpenAI-compatible client that works with:
  - vLLM on AMD MI300X (ROCm) — primary for production
  - Ollama — local development alternative
  - OpenAI API — cloud fallback
Falls back gracefully to mock responses when no server is available.
"""

import json
import re
import logging
from openai import AsyncOpenAI
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# ── OpenAI-compatible client ──────────────────────────────────
# Points at vLLM (AMD MI300X) by default via VLLM_BASE_URL env var.
# Swap to Ollama: set VLLM_BASE_URL=http://localhost:11434/v1
# Swap to OpenAI: set VLLM_BASE_URL=https://api.openai.com/v1 + real key
llm_client = AsyncOpenAI(
    base_url=settings.vllm_base_url,
    api_key=settings.hf_token or "not-needed",  # vLLM/Ollama ignore this
)


# ── JSON Sanitisation ─────────────────────────────────────────

def _sanitize_json_string(text: str) -> str:
    """Fix common JSON issues from LLM output."""
    text = re.sub(r',\s*([}\]])', r'\1', text)
    lines = text.split('\n')
    result = [line for line in lines if line.strip()]
    return '\n'.join(result)


def _extract_json(text: str) -> str:
    """
    Extract JSON from LLM responses that may include markdown code fences,
    explanatory text, or other non-JSON content.
    """
    if not text:
        return text

    text = text.strip()
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Try ```json ... ``` code block
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if match:
        candidate = match.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            sanitized = _sanitize_json_string(candidate)
            try:
                json.loads(sanitized)
                return sanitized
            except json.JSONDecodeError:
                pass

    # Try to find first { ... } or [ ... ] block
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == start_char:
                    depth += 1
                elif text[i] == end_char:
                    depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        sanitized = _sanitize_json_string(candidate)
                        try:
                            json.loads(sanitized)
                            return sanitized
                        except json.JSONDecodeError:
                            break

    return text


# ── Main Chat Function ────────────────────────────────────────

async def llm_chat(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> str:
    """
    Send a chat completion request to the configured LLM server.
    Works with vLLM (AMD ROCm), Ollama, or OpenAI — all use the same API.
    Falls back to mock responses if the server is unreachable.
    """
    effective_system_prompt = system_prompt
    if json_mode:
        effective_system_prompt += (
            "\n\nIMPORTANT: You MUST respond with ONLY valid JSON. "
            "No explanatory text, no markdown fences, no comments. "
            "Just the raw JSON object."
        )

    messages = [
        {"role": "system", "content": effective_system_prompt},
        {"role": "user",   "content": user_message},
    ]

    try:
        response = await llm_client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        result = response.choices[0].message.content

        if json_mode:
            result = _extract_json(result)

        logger.debug(f"LLM response ({len(result)} chars) from {settings.vllm_base_url}")
        return result

    except Exception as e:
        logger.error(
            f"LLM request failed (model={settings.llm_model}, "
            f"base_url={settings.vllm_base_url}): {e}. "
            f"Falling back to mock response."
        )
        return await _mock_llm_response(system_prompt, user_message, json_mode)


# ── Mock Responses (dev / offline fallback) ───────────────────

async def _mock_llm_response(
    system_prompt: str, user_message: str, json_mode: bool
) -> str:
    """
    Plausible mock responses for development without a running LLM server.
    Allows the full agent pipeline to run locally for UI testing.
    """
    prompt_lower = system_prompt.lower()

    if "clinical nlp" in prompt_lower or "extract" in prompt_lower:
        mock = {
            "patient": {"name": "Amaka Obi", "age": 28, "sex": "female"},
            "vitals": {"blood_pressure": "145/95", "heart_rate": 98},
            "symptoms": ["headache", "blurred vision", "elevated blood pressure"],
            "diagnoses": ["pre-eclampsia (suspected)"],
            "clinical_plan": "Order urine protein. Refer obstetrics urgently. Admit for monitoring.",
            "lab_orders": [{"test_name": "urine protein", "urgency": "urgent", "clinical_indication": "suspected pre-eclampsia"}],
            "prescriptions": [],
            "referrals": [{"to_department": "obstetrics", "urgency": "urgent", "reason": "suspected pre-eclampsia at 12 weeks"}],
            "follow_up": {"recommended_date": "tomorrow morning", "reason": "monitoring pre-eclampsia"},
        }
        return json.dumps(mock)

    elif "soap" in prompt_lower:
        mock = {
            "subjective": "28-year-old female, 12 weeks pregnant, presents with headache and blurred vision.",
            "objective": "BP 145/95 mmHg. Alert and oriented.",
            "assessment": "Suspected pre-eclampsia. Requires urgent obstetric evaluation.",
            "plan": "1. Order urine protein test (urgent)\n2. Urgent obstetrics referral\n3. Admit for monitoring\n4. Follow-up tomorrow 9am",
        }
        return json.dumps(mock)

    elif "lab" in prompt_lower:
        mock = {"orders": [{"test_name": "Urine Protein", "urgency": "urgent", "clinical_indication": "Suspected pre-eclampsia", "order_id": "LAB-2026-001"}]}
        return json.dumps(mock)

    elif "pharmacy" in prompt_lower or "prescription" in prompt_lower:
        mock = {"prescriptions": [], "interaction_warnings": [], "note": "No medications prescribed for this visit."}
        return json.dumps(mock)

    elif "referral" in prompt_lower:
        mock = {"referral_letter": "URGENT REFERRAL\nTo: Obstetrics\nRe: Amaka Obi, 28F, 12 weeks\nSuspected pre-eclampsia. BP 145/95.\nDr. Eze"}
        return json.dumps(mock)

    elif "schedul" in prompt_lower:
        mock = {"appointment": {"date": "2026-05-07", "time": "09:00", "reason": "Pre-eclampsia monitoring", "scheduled": True}}
        return json.dumps(mock)

    elif "billing" in prompt_lower or "icd" in prompt_lower:
        mock = {
            "icd10_codes": ["O14.1", "R51.9", "H53.8"],
            "icd10_descriptions": ["Pre-eclampsia, moderate", "Headache, unspecified", "Other visual disturbances"],
            "cpt_codes": ["99214", "81003"],
        }
        return json.dumps(mock)

    elif "sms" in prompt_lower or "patient communication" in prompt_lower:
        mock = {"message": "Hello Amaka, you have been admitted for monitoring. Dr. Eze is coordinating your care. — Klinik Health"}
        return json.dumps(mock)

    elif "supervisor" in prompt_lower:
        return "All done. Amaka is admitted, obstetrics notified, urine protein ordered, follow-up set for 9am tomorrow. Your next patient is ready."

    else:
        return json.dumps({"response": "Mock LLM response — vLLM server not connected."})
