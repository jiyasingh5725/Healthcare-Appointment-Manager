import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Any
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.config import settings
from app.models.appointment import Appointment
from app.models.ai_summary import AISummary
from app.models.prescription import Prescription, Medication

logger = logging.getLogger(__name__)

VALID_URGENCY_LEVELS = {"Low", "Medium", "High"}



def _rule_based_fallback(symptoms: str) -> dict[str, Any]:
    """
    Intelligent non-diagnostic clinical triage heuristic used when LLM API
    is unreachable, unconfigured, or returns an error.
    """
    clean_symptoms = symptoms.strip() if symptoms else ""
    symptoms_lower = clean_symptoms.lower()

    # Urgency analysis cues
    high_keywords = [
        "chest pain", "tightness", "shortness of breath", "difficulty breathing",
        "radiating", "fainting", "syncope", "severe pain", "paralysis", "slurred speech",
        "heavy bleeding", "anaphylaxis", "loss of consciousness", "stroke", "cardiac"
    ]
    med_keywords = [
        "fever", "migraine", "infection", "vomiting", "nausea", "swelling",
        "persistent", "cough", "rash", "dizziness", "moderate pain", "sprain",
        "palpitations", "headache", "stomach pain", "abdominal"
    ]

    if any(kw in symptoms_lower for kw in high_keywords):
        urgency = "High"
    elif any(kw in symptoms_lower for kw in med_keywords):
        urgency = "Medium"
    else:
        urgency = "Low"

    # Chief complaint extraction
    if clean_symptoms:
        first_clause = clean_symptoms.split(".")[0].strip()
        chief_complaint = first_clause[:180] + ("..." if len(first_clause) > 180 else "")
    else:
        chief_complaint = "Routine consultation and general symptom evaluation."

    # Formulate 3 clarifying clinical inquiry questions
    questions = [
        "When did these symptoms first appear and have they changed in intensity over time?",
        "Are there any specific activities, postures, or foods that trigger or relieve the discomfort?",
        "Are you currently taking any prescription medications, supplements, or recent treatments for this issue?"
    ]

    return {
        "urgency_level": urgency,
        "chief_complaint": chief_complaint,
        "suggested_questions": questions,
        "summary_text": f"Pre-visit summary ({urgency} urgency): {chief_complaint}",
        "status": "FALLBACK",
        "model_name": "clinical-heuristic-fallback"
    }


def _call_gemini_api(symptoms: str) -> dict[str, Any]:
    """
    Call Google Gemini REST API with structured JSON output enforcement.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    model = settings.LLM_MODEL_NAME or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"

    prompt = (
        "You are an AI pre-visit medical triage assistant.\n"
        "Analyse these symptoms and return:\n"
        "urgency level (Low / Medium / High),\n"
        "chief complaint,\n"
        "and three suggested questions for the doctor.\n\n"
        f"Symptoms:\n{symptoms}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. You must NOT diagnose the patient or prescribe treatments.\n"
        "2. Urgency level must strictly be one of: 'Low', 'Medium', 'High'.\n"
        "3. Return strictly a single valid JSON object matching the following structure:\n"
        "{\n"
        '  "urgency_level": "Low" | "Medium" | "High",\n'
        '  "chief_complaint": "Concise summary of main symptom/reason for visit",\n'
        '  "suggested_questions": ["Question 1", "Question 2", "Question 3"]\n'
        "}\n"
        "Do not include markdown backticks or commentary outside the JSON."
    )

    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }

    req_data = json.dumps(request_body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
        return parsed


def generate_previsit_summary(
    appointment_id: int,
    symptoms_override: Optional[str],
    db: Session
) -> dict[str, Any]:
    """
    Generate or refresh pre-visit AI symptom summary for an appointment.
    Falls back gracefully if LLM API is unavailable.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    # Use symptoms from override or appointment
    symptoms = (
        symptoms_override.strip()
        if (symptoms_override and symptoms_override.strip())
        else (appointment.symptoms or "").strip()
    )

    # If symptoms are completely blank
    if not symptoms:
        symptoms = "General medical checkup and consultation."

    ai_data: dict[str, Any] = {}
    status_flag = "SUCCESS"
    model_name = settings.LLM_MODEL_NAME or "gemini-1.5-flash"
    error_msg = None

    # Attempt LLM generation
    if settings.GEMINI_API_KEY:
        try:
            raw_result = _call_gemini_api(symptoms)
            urgency_raw = str(raw_result.get("urgency_level", "Medium")).strip().capitalize()
            urgency = urgency_raw if urgency_raw in VALID_URGENCY_LEVELS else "Medium"
            chief_complaint = str(raw_result.get("chief_complaint", symptoms[:150])).strip()
            
            questions = raw_result.get("suggested_questions", [])
            if not isinstance(questions, list) or len(questions) < 3:
                questions = [
                    "How long have you experienced these symptoms?",
                    "Have you noticed any triggers or relieving factors?",
                    "Do you have any related medical history or ongoing treatments?"
                ]
            else:
                questions = [str(q).strip() for q in questions[:3]]

            ai_data = {
                "urgency_level": urgency,
                "chief_complaint": chief_complaint,
                "suggested_questions": questions,
                "summary_text": f"AI Triage ({urgency} Urgency): {chief_complaint}",
                "status": "SUCCESS",
                "model_name": model_name
            }
        except Exception as e:
            logger.warning(f"LLM API error during pre-visit summary: {str(e)}. Using safe fallback heuristic.")
            error_msg = str(e)
            ai_data = _rule_based_fallback(symptoms)
            status_flag = "FALLBACK"
            model_name = ai_data["model_name"]
    else:
        # Fallback when key is unconfigured
        ai_data = _rule_based_fallback(symptoms)
        status_flag = "FALLBACK"
        model_name = ai_data["model_name"]

    # Normalize urgency
    urgency_val = ai_data.get("urgency_level", "Medium")
    if urgency_val not in VALID_URGENCY_LEVELS:
        urgency_val = "Medium"

    chief_complaint_val = ai_data.get("chief_complaint", "Symptom review")
    questions_list = ai_data.get("suggested_questions", [])
    summary_text_val = ai_data.get("summary_text", f"Pre-visit summary: {chief_complaint_val}")

    # Persist or update in ai_summaries table
    existing_summary = db.query(AISummary).filter(
        AISummary.appointment_id == appointment_id,
        AISummary.summary_type == "PREVISIT"
    ).first()

    if existing_summary:
        existing_summary.urgency_level = urgency_val
        existing_summary.chief_complaint = chief_complaint_val
        existing_summary.suggested_questions = json.dumps(questions_list)
        existing_summary.summary_text = summary_text_val
        existing_summary.model_name = model_name
        existing_summary.status = status_flag
        existing_summary.error_message = error_msg
        db.commit()
        db.refresh(existing_summary)
        summary_record = existing_summary
    else:
        summary_record = AISummary(
            appointment_id=appointment_id,
            summary_type="PREVISIT",
            urgency_level=urgency_val,
            chief_complaint=chief_complaint_val,
            suggested_questions=json.dumps(questions_list),
            summary_text=summary_text_val,
            model_name=model_name,
            status=status_flag,
            error_message=error_msg
        )
        db.add(summary_record)
        db.commit()
        db.refresh(summary_record)

    return {
        "id": summary_record.id,
        "appointment_id": summary_record.appointment_id,
        "summary_type": summary_record.summary_type,
        "urgency_level": summary_record.urgency_level,
        "chief_complaint": summary_record.chief_complaint,
        "suggested_questions": questions_list,
        "summary_text": summary_record.summary_text,
        "model_name": summary_record.model_name,
        "status": summary_record.status,
        "error_message": summary_record.error_message,
        "disclaimer": "AI-generated decision-support triage only; not a clinical diagnosis.",
        "created_at": summary_record.created_at
    }


def get_previsit_summary(appointment_id: int, db: Session) -> Optional[dict[str, Any]]:
    """
    Retrieve existing pre-visit AI symptom summary for an appointment.
    """
    summary = db.query(AISummary).filter(
        AISummary.appointment_id == appointment_id,
        AISummary.summary_type == "PREVISIT"
    ).first()

    if not summary:
        return None

    questions = []
    if summary.suggested_questions:
        try:
            questions = json.loads(summary.suggested_questions)
        except Exception:
            questions = [summary.suggested_questions]

    return {
        "id": summary.id,
        "appointment_id": summary.appointment_id,
        "summary_type": summary.summary_type,
        "urgency_level": summary.urgency_level,
        "chief_complaint": summary.chief_complaint,
        "suggested_questions": questions,
        "summary_text": summary.summary_text,
        "model_name": summary.model_name,
        "status": summary.status,
        "error_message": summary.error_message,
        "disclaimer": "AI-generated decision-support triage only; not a clinical diagnosis.",
        "created_at": summary.created_at
    }


# ==========================================
# PHASE 14: POST-VISIT PATIENT-FRIENDLY AI
# ==========================================

def _call_gemini_postvisit_api(clinical_text: str) -> dict[str, Any]:
    """
    Call Google Gemini API to convert physician clinical notes into a patient-friendly summary.
    """
    if not settings.GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not configured")

    model = settings.LLM_MODEL_NAME or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.GEMINI_API_KEY}"

    prompt = (
        "You are an empathetic medical communicator.\n"
        "Convert these clinical notes into a patient-friendly summary with medication schedule and follow-up steps:\n\n"
        f"<notes>\n{clinical_text}\n</notes>\n\n"
        "CRITICAL REQUIREMENTS:\n"
        "1. Translate complex clinical medical jargon into clear, reassuring, plain-English instructions for the patient.\n"
        "2. Do not contradict or modify any medication dosage or physician instructions.\n"
        "3. Provide a structured response in exact JSON format:\n"
        "{\n"
        '  "summary": "Clear, compassionate explanation of the diagnosis and visit outcomes for the patient",\n'
        '  "medication_schedule": [\n'
        '    {\n'
        '      "medicine": "Medicine name",\n'
        '      "dosage": "Dosage quantity (e.g. 500mg)",\n'
        '      "frequency": "When and how often to take it",\n'
        '      "duration": "How many days/weeks"\n'
        '    }\n'
        '  ],\n'
        '  "follow_up_steps": [\n'
        '    "Actionable recovery, rest, test, or review step 1",\n'
        '    "Actionable step 2"\n'
        '  ]\n'
        "}\n"
        "Return strictly the JSON object without markdown formatting."
    )

    request_body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.2
        }
    }

    req_data = json.dumps(request_body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=10) as response:
        res_json = json.loads(response.read().decode("utf-8"))
        raw_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(raw_text)
        return parsed


def _rule_based_postvisit_fallback(
    notes: str,
    follow_up: Optional[str],
    medications: list[Any]
) -> dict[str, Any]:
    """
    Intelligent patient-friendly fallback synthesizer when LLM API is unavailable.
    """
    # Plain language synthesis from notes
    summary_text = (
        f"During your consultation, your doctor evaluated your symptoms and documented: {notes}."
        if notes
        else "Your physician completed your consultation checkup and recorded your treatment plan."
    )

    # Medication schedule mapping
    med_schedule = []
    for m in medications:
        med_schedule.append({
            "medicine": getattr(m, "medication_name", str(m)),
            "dosage": getattr(m, "dosage", "As prescribed"),
            "frequency": getattr(m, "frequency", "Daily"),
            "duration": getattr(m, "duration", "As instructed")
        })

    # Follow-up steps
    follow_up_steps = []
    if follow_up and follow_up.strip():
        follow_up_steps.append(follow_up.strip())
    else:
        follow_up_steps.append("Take prescribed medications according to the schedule.")
        follow_up_steps.append("Rest, maintain adequate hydration, and monitor your symptoms.")
        follow_up_steps.append("Schedule a follow-up review or visit an urgent care center if symptoms worsen.")

    return {
        "summary": summary_text,
        "medication_schedule": med_schedule,
        "follow_up_steps": follow_up_steps,
        "status": "FALLBACK",
        "model_name": "clinical-heuristic-fallback"
    }


def generate_postvisit_summary(
    appointment_id: int,
    notes_override: Optional[str],
    db: Session
) -> dict[str, Any]:
    """
    Generate patient-friendly post-visit AI summary from doctor consultation notes & prescription.
    """
    appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment #{appointment_id} not found."
        )

    # Fetch prescription and medication items
    prescription = db.query(Prescription).filter(Prescription.appointment_id == appointment_id).first()

    raw_notes = notes_override or (prescription.notes if prescription else "") or appointment.symptoms or "Routine medical visit."
    raw_follow_up = prescription.follow_up_instructions if prescription else None
    meds_list = prescription.medications if (prescription and prescription.medications) else []

    # Compile structured notes for LLM prompt
    clinical_narrative_parts = [f"Physician Notes: {raw_notes}"]
    if raw_follow_up:
        clinical_narrative_parts.append(f"Follow-up Advice: {raw_follow_up}")
    if meds_list:
        meds_text = "; ".join([
            f"{m.medication_name} (Dosage: {m.dosage}, Frequency: {m.frequency}, Duration: {m.duration}, Instructions: {m.instructions or 'Standard'})"
            for m in meds_list
        ])
        clinical_narrative_parts.append(f"Prescribed Medications: {meds_text}")

    full_clinical_text = "\n".join(clinical_narrative_parts)

    ai_data: dict[str, Any] = {}
    status_flag = "SUCCESS"
    model_name = settings.LLM_MODEL_NAME or "gemini-1.5-flash"
    error_msg = None

    if settings.GEMINI_API_KEY:
        try:
            raw_result = _call_gemini_postvisit_api(full_clinical_text)
            summary_val = str(raw_result.get("summary", raw_notes)).strip()
            
            med_sched_raw = raw_result.get("medication_schedule", [])
            med_schedule = []
            if isinstance(med_sched_raw, list):
                for item in med_sched_raw:
                    if isinstance(item, dict):
                        med_schedule.append({
                            "medicine": str(item.get("medicine", "Medication")),
                            "dosage": str(item.get("dosage", "As directed")),
                            "frequency": str(item.get("frequency", "Daily")),
                            "duration": str(item.get("duration", "As instructed"))
                        })

            steps_raw = raw_result.get("follow_up_steps", [])
            steps = [str(s).strip() for s in steps_raw if str(s).strip()] if isinstance(steps_raw, list) else []
            if not steps:
                steps = ["Take prescribed medications on time.", "Rest and monitor your condition."]

            ai_data = {
                "summary": summary_val,
                "medication_schedule": med_schedule,
                "follow_up_steps": steps,
                "status": "SUCCESS",
                "model_name": model_name
            }
        except Exception as e:
            logger.warning(f"LLM API error during post-visit summary: {str(e)}. Using safe fallback heuristic.")
            error_msg = str(e)
            ai_data = _rule_based_postvisit_fallback(raw_notes, raw_follow_up, meds_list)
            status_flag = "FALLBACK"
            model_name = ai_data["model_name"]
    else:
        ai_data = _rule_based_postvisit_fallback(raw_notes, raw_follow_up, meds_list)
        status_flag = "FALLBACK"
        model_name = ai_data["model_name"]

    summary_str = ai_data.get("summary", "Your physician has documented your visit and treatment plan.")
    med_sched = ai_data.get("medication_schedule", [])
    follow_steps = ai_data.get("follow_up_steps", [])

    # Store full JSON payload in summary_text for reliable parsing
    payload_to_store = {
        "summary": summary_str,
        "medication_schedule": med_sched,
        "follow_up_steps": follow_steps
    }
    encoded_summary = json.dumps(payload_to_store)

    # Persist in ai_summaries table
    existing_summary = db.query(AISummary).filter(
        AISummary.appointment_id == appointment_id,
        AISummary.summary_type == "POST_VISIT"
    ).first()

    if existing_summary:
        existing_summary.chief_complaint = summary_str[:200]
        existing_summary.summary_text = encoded_summary
        existing_summary.suggested_questions = json.dumps(follow_steps)
        existing_summary.model_name = model_name
        existing_summary.status = status_flag
        existing_summary.error_message = error_msg
        db.commit()
        db.refresh(existing_summary)
        summary_record = existing_summary
    else:
        summary_record = AISummary(
            appointment_id=appointment_id,
            summary_type="POST_VISIT",
            chief_complaint=summary_str[:200],
            summary_text=encoded_summary,
            suggested_questions=json.dumps(follow_steps),
            model_name=model_name,
            status=status_flag,
            error_message=error_msg
        )
        db.add(summary_record)
        db.commit()
        db.refresh(summary_record)

    return {
        "id": summary_record.id,
        "appointment_id": summary_record.appointment_id,
        "summary_type": "POST_VISIT",
        "summary": summary_str,
        "medication_schedule": med_sched,
        "follow_up_steps": follow_steps,
        "summary_text": summary_str,
        "model_name": summary_record.model_name,
        "status": summary_record.status,
        "error_message": summary_record.error_message,
        "disclaimer": "AI-generated patient summary; does not replace professional medical advice.",
        "created_at": summary_record.created_at
    }


def get_postvisit_summary(appointment_id: int, db: Session) -> Optional[dict[str, Any]]:
    """
    Retrieve existing patient-friendly post-visit AI summary for an appointment.
    """
    summary = db.query(AISummary).filter(
        AISummary.appointment_id == appointment_id,
        AISummary.summary_type == "POST_VISIT"
    ).first()

    if not summary:
        return None

    summary_val = summary.chief_complaint or "Consultation complete."
    med_sched = []
    follow_steps = []

    if summary.summary_text:
        try:
            parsed = json.loads(summary.summary_text)
            if isinstance(parsed, dict):
                summary_val = parsed.get("summary", summary_val)
                med_sched = parsed.get("medication_schedule", [])
                follow_steps = parsed.get("follow_up_steps", [])
        except Exception:
            summary_val = summary.summary_text

    if not follow_steps and summary.suggested_questions:
        try:
            follow_steps = json.loads(summary.suggested_questions)
        except Exception:
            follow_steps = [summary.suggested_questions]

    return {
        "id": summary.id,
        "appointment_id": summary.appointment_id,
        "summary_type": "POST_VISIT",
        "summary": summary_val,
        "medication_schedule": med_sched,
        "follow_up_steps": follow_steps,
        "summary_text": summary_val,
        "model_name": summary.model_name,
        "status": summary.status,
        "error_message": summary.error_message,
        "disclaimer": "AI-generated patient summary; does not replace professional medical advice.",
        "created_at": summary.created_at
    }

