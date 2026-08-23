# LLM Prompts & AI Clinical Integration: CareSync

CareSync leverages Google Gemini LLMs to generate structured clinical pre-consultation symptom summaries. This assists attending physicians by distilling unstructured patient symptom narratives into categorized keypoints, timelines, severity indicators, and clinical tags.

---

## 1. AI Clinical Summary Architecture

```
+-----------------------------------------------------------------------------+
|                       CareSync AI Clinical Pipeline                         |
|                                                                             |
|   +--------------------------+                                              |
|   | Patient Booking Symptoms |                                              |
|   | (Raw Unstructured Text)  |                                              |
|   +------------+-------------+                                              |
|                |                                                            |
|                v                                                            |
|   +--------------------------+     Timeout / Rate Limit                     |
|   | Gemini API Model Request +----------------------------+                 |
|   | (gemini-1.5-flash)       |                            |                 |
|   +------------+-------------+                            |                 |
|                |                                          v                 |
|                | Success                +---------------------------------+ |
|                v                        | Heuristic Rule-Based Extractor  | |
|   +--------------------------+          | (Deterministic Keyword Parsing) | |
|   | JSON Output Validation   |          +-----------------+---------------+ |
|   | (Pydantic Schema Check)  |                            |                 |
|   +------------+-------------+                            |                 |
|                |                                          |                 |
|                +--------------------+---------------------+                 |
|                                     |                                       |
|                                     v                                       |
|                       +---------------------------+                         |
|                       | Cached Clinical Summary   |                         |
|                       | (Stored in `appointments`)|                         |
|                       +---------------------------+                         |
+-----------------------------------------------------------------------------+
```

---

## 2. System Prompt Specification

```text
You are an expert clinical medical AI assistant designed to help licensed physicians prepare for upcoming patient consultations.

Your task is to analyze the patient's raw self-reported symptoms and provide a concise, medically structured summary strictly in valid JSON format.

CRITICAL SAFETY & MEDICAL GUIDELINES:
1. Do NOT provide direct patient diagnoses or prescribe treatments.
2. Structure the information into clinical observations: chief complaint, reported onset/duration, pain/severity levels, and relevant contextual factors.
3. If red flag symptoms (e.g. chest pain radiating to arm, sudden severe dyspnea, acute neurological deficit, stroke signs) are identified, flag potential urgency in the 'urgency_level' field ('HIGH', 'MEDIUM', 'LOW').
4. Return ONLY valid JSON matching the exact schema provided. Do not include markdown code blocks, backticks, or preamble text.
```

---

## 3. User Prompt Template

```text
Patient Name: {patient_name}
Consultation Specialization: {doctor_specialization}
Patient Stated Symptoms:
"""
{raw_symptoms}
"""

Extract structured clinical summary:
```

---

## 4. Structured JSON Output Schema

```json
{
  "chief_complaint": "Persistent throbbing headache with photophobia",
  "symptom_duration": "4 days",
  "severity": "Moderate to Severe",
  "urgency_level": "MEDIUM",
  "key_observations": [
    "Unilateral throbbing pain in temporal region",
    "Aggravated by bright light and screen exposure",
    "Over-the-counter NSAIDs provided temporary partial relief"
  ],
  "recommended_focus_areas": [
    "Migraine vs tension-type headache differential",
    "Visual aura check and blood pressure evaluation",
    "Medication overuse screening"
  ],
  "is_fallback": false
}
```

---

## 5. Deterministic Heuristic Fallback Algorithm

If the external Gemini API is unreachable, times out, or encounters rate limits, CareSync automatically executes a local heuristic parser without breaking the consultation workflow:

1. **Duration Regex Extraction**: Scans for time patterns (e.g., `(\d+)\s*(days|weeks|months|hours)`).
2. **Urgency Keyword Detection**:
   - `HIGH`: `"chest pain"`, `"breathless"`, `"shortness of breath"`, `"unconscious"`, `"severe bleeding"`, `"vision loss"`.
   - `MEDIUM`: `"fever"`, `"vomiting"`, `"migraine"`, `"acute"`, `"injury"`.
   - `LOW`: Routine checks, mild cough, checkup.
3. **Structured Fallback Formatting**: Packages parsed tokens into the identical JSON schema with `is_fallback: true`, ensuring frontend components render seamlessly without disruption.
