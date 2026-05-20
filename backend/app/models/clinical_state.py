"""
Klinik — Core Clinical State Models
Pydantic models that flow through the LangGraph agent pipeline.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enumerations ──────────────────────────────────────────────

class AgentStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


class Urgency(str, Enum):
    ROUTINE = "routine"
    URGENT  = "urgent"
    STAT    = "stat"


class VisitStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    CANCELLED   = "cancelled"


# ── Sub-models ────────────────────────────────────────────────

class PatientInfo(BaseModel):
    patient_id: str = Field(default_factory=lambda: f"pt-{uuid.uuid4().hex[:8]}")
    tenant_id: str = "default_tenant"
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class VitalSigns(BaseModel):
    blood_pressure: Optional[str] = None
    heart_rate: Optional[int] = None
    temperature: Optional[float] = None
    temperature_unit: Optional[str] = None
    respiratory_rate: Optional[int] = None
    spo2: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = None


class SOAPNote(BaseModel):
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""


class LabOrder(BaseModel):
    test_name: str
    urgency: Urgency = Urgency.ROUTINE
    clinical_indication: str = ""
    order_id: str = Field(default_factory=lambda: f"LAB-{uuid.uuid4().hex[:6].upper()}")
    status: str = "ordered"


class Prescription(BaseModel):
    drug_name: str = ""
    medication: str = ""   # alias populated by clinical_nlp
    dosage: str = ""
    frequency: str = ""
    duration: str = ""
    route: str = "oral"
    instructions: str = ""
    interaction_warnings: list[str] = Field(default_factory=list)

    def __init__(self, **data):
        # normalise: accept either 'drug_name' or 'medication'
        if "medication" in data and not data.get("drug_name"):
            data["drug_name"] = data["medication"]
        if "drug_name" in data and not data.get("medication"):
            data["medication"] = data["drug_name"]
        super().__init__(**data)


class Referral(BaseModel):
    to_department: str
    urgency: Urgency = Urgency.ROUTINE
    reason: str = ""
    referral_letter: str = ""
    clinical_summary: Optional[str] = None   # LLM sometimes includes this field


class FollowUp(BaseModel):
    recommended_date: Optional[str] = None
    reason: str = ""
    scheduled: bool = False


class BillingCode(BaseModel):
    icd10_codes: list[str] = Field(default_factory=list)
    icd10_descriptions: list[str] = Field(default_factory=list)
    cpt_codes: list[str] = Field(default_factory=list)


class SMSMessage(BaseModel):
    to_number: Optional[str] = None
    body: str = ""
    sent: bool = False
    sent_at: Optional[datetime] = None


class AgentResult(BaseModel):
    agent_name: str
    status: AgentStatus = AgentStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output: Optional[str] = None
    error: Optional[str] = None


# ── Master Clinical State ─────────────────────────────────────

class ClinicalState(BaseModel):
    """
    The single source of truth that flows through the entire LangGraph pipeline.
    Each agent reads from it and writes to its designated slice.
    """
    # Identity
    session_id: str = Field(default_factory=lambda: f"session-{uuid.uuid4().hex[:8]}")
    tenant_id: str = "default_tenant"
    doctor_id: str = "dr-default"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    visit_status: VisitStatus = VisitStatus.IN_PROGRESS
    is_signed_off: bool = False
    signed_by_doctor_id: Optional[str] = None

    # Input
    transcript: str = ""
    raw_audio_path: Optional[str] = None

    # Extracted clinical data
    patient: PatientInfo = Field(default_factory=PatientInfo)
    vitals: VitalSigns = Field(default_factory=VitalSigns)
    symptoms: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    clinical_plan: str = ""

    # Agent outputs
    soap_note: SOAPNote = Field(default_factory=SOAPNote)
    lab_orders: list[LabOrder] = Field(default_factory=list)
    prescriptions: list[Prescription] = Field(default_factory=list)
    referrals: list[Referral] = Field(default_factory=list)
    follow_up: FollowUp = Field(default_factory=FollowUp)
    billing: BillingCode = Field(default_factory=BillingCode)
    sms_messages: list[SMSMessage] = Field(default_factory=list)

    # Supervisor
    supervisor_summary: str = ""

    # Agent tracking
    agent_results: list[AgentResult] = Field(default_factory=list)

    def set_agent_status(
        self,
        agent_name: str,
        status: AgentStatus,
        output: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Upsert an agent result entry."""
        now = datetime.utcnow()
        for r in self.agent_results:
            if r.agent_name == agent_name:
                r.status = status
                if status == AgentStatus.RUNNING:
                    r.started_at = now
                elif status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.SKIPPED):
                    r.completed_at = now
                if output is not None:
                    r.output = output
                if error is not None:
                    r.error = error
                return
        # First time — create it
        result = AgentResult(agent_name=agent_name, status=status)
        if status == AgentStatus.RUNNING:
            result.started_at = now
        elif status in (AgentStatus.COMPLETED, AgentStatus.FAILED, AgentStatus.SKIPPED):
            result.completed_at = now
        result.output = output
        result.error = error
        self.agent_results.append(result)
