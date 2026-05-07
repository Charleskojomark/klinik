"""
Klinik — FHIR R4 Export
Converts a completed ClinicalState into a FHIR R4 Bundle for EHR interoperability.
"""

import uuid
from datetime import datetime
from typing import Any
from app.models.clinical_state import ClinicalState


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _entry(resource: dict) -> dict:
    return {
        "fullUrl": f"urn:uuid:{uuid.uuid4()}",
        "resource": resource,
    }


def clinical_state_to_fhir_bundle(state: ClinicalState) -> dict[str, Any]:
    """
    Convert a ClinicalState into a FHIR R4 Bundle (transaction type).
    Includes: Patient, Encounter, Conditions, Observations, MedicationRequests,
              ServiceRequests (labs), ReferralRequests.
    """
    entries = []
    patient_ref = f"Patient/{state.patient.patient_id}"

    # ── Patient resource ──────────────────────────────────────
    patient_resource = {
        "resourceType": "Patient",
        "id": state.patient.patient_id,
        "name": [{"text": state.patient.name or "Unknown"}],
    }
    if state.patient.age:
        birth_year = datetime.utcnow().year - state.patient.age
        patient_resource["birthDate"] = str(birth_year)
    if state.patient.sex:
        patient_resource["gender"] = state.patient.sex.lower()
    if state.patient.phone:
        patient_resource["telecom"] = [{"system": "phone", "value": state.patient.phone}]
    entries.append(_entry(patient_resource))

    # ── Encounter resource ────────────────────────────────────
    encounter_id = state.session_id
    encounter_resource = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "status": "finished" if state.visit_status.value == "completed" else "in-progress",
        "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"},
        "subject": {"reference": patient_ref},
        "period": {"start": state.created_at.strftime("%Y-%m-%dT%H:%M:%SZ")},
    }
    entries.append(_entry(encounter_resource))
    encounter_ref = f"Encounter/{encounter_id}"

    # ── Conditions (diagnoses) ────────────────────────────────
    for dx in state.diagnoses:
        condition = {
            "resourceType": "Condition",
            "id": f"condition-{uuid.uuid4().hex[:8]}",
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "code": {"text": dx},
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }]
            },
        }
        entries.append(_entry(condition))

    # ── Observations (vitals) ─────────────────────────────────
    vitals_map = {
        "blood_pressure": ("55284-4", "Blood pressure"),
        "heart_rate":     ("8867-4",  "Heart rate"),
        "temperature":    ("8310-5",  "Body temperature"),
        "spo2":           ("59408-5", "Oxygen saturation"),
    }
    for field, (loinc, display) in vitals_map.items():
        value = getattr(state.vitals, field, None)
        if value is None:
            continue
        obs = {
            "resourceType": "Observation",
            "id": f"obs-{uuid.uuid4().hex[:8]}",
            "status": "final",
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}]},
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "valueString": str(value),
        }
        entries.append(_entry(obs))

    # ── MedicationRequests ────────────────────────────────────
    for rx in state.prescriptions:
        med_req = {
            "resourceType": "MedicationRequest",
            "id": f"rx-{uuid.uuid4().hex[:8]}",
            "status": "active",
            "intent": "order",
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "medicationCodeableConcept": {"text": rx.drug_name or rx.medication},
            "dosageInstruction": [{
                "text": f"{rx.dosage} {rx.frequency} for {rx.duration} ({rx.route})",
            }],
        }
        entries.append(_entry(med_req))

    # ── ServiceRequests (lab orders) ──────────────────────────
    for lab in state.lab_orders:
        sr = {
            "resourceType": "ServiceRequest",
            "id": lab.order_id,
            "status": "active",
            "intent": "order",
            "priority": lab.urgency.value,
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "code": {"text": lab.test_name},
            "reasonCode": [{"text": lab.clinical_indication}],
        }
        entries.append(_entry(sr))

    # ── Referrals ─────────────────────────────────────────────
    for ref in state.referrals:
        referral_sr = {
            "resourceType": "ServiceRequest",
            "id": f"ref-{uuid.uuid4().hex[:8]}",
            "status": "active",
            "intent": "referral",
            "priority": ref.urgency.value,
            "subject": {"reference": patient_ref},
            "encounter": {"reference": encounter_ref},
            "performerType": {"text": ref.to_department},
            "reasonCode": [{"text": ref.reason}],
        }
        entries.append(_entry(referral_sr))

    # ── ICD-10 / Billing Codes as Claim ──────────────────────
    if state.billing.icd10_codes:
        claim = {
            "resourceType": "Claim",
            "id": f"claim-{uuid.uuid4().hex[:8]}",
            "status": "active",
            "type": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/claim-type", "code": "professional"}]},
            "use": "claim",
            "patient": {"reference": patient_ref},
            "diagnosis": [
                {
                    "sequence": i + 1,
                    "diagnosisCodeableConcept": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10", "code": code}],
                        "text": state.billing.icd10_descriptions[i] if i < len(state.billing.icd10_descriptions) else "",
                    },
                }
                for i, code in enumerate(state.billing.icd10_codes)
            ],
            "procedure": [
                {
                    "sequence": i + 1,
                    "procedureCodeableConcept": {
                        "coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": code}],
                    },
                }
                for i, code in enumerate(state.billing.cpt_codes)
            ],
        }
        entries.append(_entry(claim))

    return {
        "resourceType": "Bundle",
        "id": f"bundle-{state.session_id}",
        "type": "transaction",
        "timestamp": _now_iso(),
        "total": len(entries),
        "entry": entries,
    }
