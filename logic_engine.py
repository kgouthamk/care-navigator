"""
Care Navigator — Automated Clinical Routing Navigator
Core Logic Engine: Clinical Processor & SOP Matching
"""

import json
import os
import re
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

# ── SOP Rule Definitions ──────────────────────────────────────────────────────

SOP_RULES = [
    {
        "id": "GEN-001",
        "category": "General",
        "finding": "Dental visit > 6 months ago OR pending dental work",
        "fact_key": "dental_clearance_needed",
        "trigger_value": True,
        "case_status": "Action Required",
        "action": "Instruct patient to complete dental clearance before Consultation.",
        "priority": 5,
    },
    {
        "id": "JNT-001",
        "category": "Joint",
        "finding": "Active Smoker (or quit < 3 months)",
        "fact_key": "active_smoker",
        "trigger_value": True,
        "case_status": "Deferred",
        "action": "Refer to Smoking Cessation education/support; pause case for 3 months.",
        "priority": 2,
    },
    {
        "id": "JNT-002",
        "category": "Joint",
        "finding": "No attempt at PT / Exercise",
        "fact_key": "no_pt_history",
        "trigger_value": True,
        "case_status": "Ineligible",
        "action": "Refer to 6-12 week conservative physical therapy trial.",
        "priority": 0,
    },
    {
        "id": "JNT-003",
        "category": "Joint",
        "finding": "HbA1c > 7.0",
        "fact_key": "hba1c_elevated",
        "trigger_value": True,
        "case_status": "Review",
        "action": "Flag for Clinical MD Review for glucose optimization.",
        "priority": 4,
    },
    {
        "id": "JNT-004",
        "category": "Joint",
        "finding": "Daily Opioid use > 3 months",
        "fact_key": "daily_opioid_over_3_months",
        "trigger_value": True,
        "case_status": "High Complexity",
        "action": 'Flag for Anesthesia "High Risk" Consult.',
        "priority": 1,
    },
    {
        "id": "BAR-001",
        "category": "Bariatric",
        "finding": "History of prior weight-loss surgery",
        "fact_key": "prior_weight_loss_surgery",
        "trigger_value": True,
        "case_status": "Revision Case",
        "action": "Flag as Revision Case; requires specialized surgical review.",
        "priority": 3,
    },
    {
        "id": "BAR-002",
        "category": "Bariatric",
        "finding": "No Endoscopy (EGD) in last 3 months",
        "fact_key": "no_recent_egd",
        "trigger_value": True,
        "case_status": "Action Required",
        "action": "Instruct patient to schedule EGD for after Consultation.",
        "priority": 5,
    },
    {
        "id": "BAR-003",
        "category": "Bariatric",
        "finding": "No Registered Dietician (RD) identified",
        "fact_key": "no_registered_dietician",
        "trigger_value": True,
        "case_status": "Hold",
        "action": "Provide in-network RD list; patient must confirm RD before referral.",
        "priority": 6,
    },
]

STATUS_PRIORITY = {
    "Ineligible": 0,
    "High Complexity": 1,
    "Deferred": 2,
    "Revision Case": 3,
    "Review": 4,
    "Action Required": 5,
    "Hold": 6,
    "Clear": 7,
}

STATUS_COLORS = {
    "Ineligible": "#DC2626",
    "High Complexity": "#EA580C",
    "Deferred": "#D97706",
    "Revision Case": "#7C3AED",
    "Review": "#2563EB",
    "Action Required": "#059669",
    "Hold": "#6B7280",
    "Clear": "#16A34A",
}

# ── Extraction Prompt ─────────────────────────────────────────────────────────

EXTRACTION_SYSTEM_PROMPT = """You are a clinical data extraction specialist for Care Navigator. 
Your task is to read a patient transcript and extract specific clinical facts needed for 
surgical case routing. You must return ONLY a valid JSON object — no commentary, no markdown fences.

Extract the following fields. Use null if information is not mentioned or unclear.

{
  "patient_name": string or null,
  "case_type": "Bariatric" | "Joint" | "Unknown",
  "dental_last_visit_within_6_months": true | false | null,
  "dental_pending_work": true | false | null,
  "active_smoker": true | false | null,
  "smoking_quit_within_3_months": true | false | null,
  "has_pt_history": true | false | null,
  "pt_description": string or null,
  "hba1c_value": number or null,
  "daily_opioid_use": true | false | null,
  "opioid_duration_months": number or null,
  "opioid_medication": string or null,
  "prior_weight_loss_surgery": true | false | null,
  "prior_surgery_description": string or null,
  "recent_egd_within_3_months": true | false | null,
  "has_registered_dietician": true | false | null,
  "rd_description": string or null,
  "chronic_infections": string or null,
  "other_conditions": string or null,
  "clinical_notes": string
}

Critical extraction rules:
- dental_last_visit_within_6_months: if patient says visit "in May", "last month", "just had cleaning", or has a routine cleaning scheduled imminently (e.g. "next week") with no pending restorative work, set to true. If no mention or clearly > 6 months ago, set to false.
- dental_pending_work: any recommended restorative work (crowns, fillings, extractions, root canals) counts as pending = true, even if the dentist described it as "not urgent", "eventually", or "can wait". Only a routine cleaning or checkup with no recommended work = false.
- active_smoker: true even if light/occasional ("cigarette with my coffee", "half-pack a day")
- has_pt_history: requires a formal course of at least several weeks (typically 6+) with a licensed physical therapist. Two sessions or fewer does NOT count even if with a licensed PT — "went twice, stopped" = false. Gym exercises or a personal trainer do NOT count regardless of duration. "8 weeks at Riverside PT" or "12 weeks at ProMotion PT" = true.
- opioids: "pretty much daily for 2 years" = daily_opioid_use: true, opioid_duration_months: 24
- case_type: mentions of weight loss, bariatric, sleeve, lap band = "Bariatric"; hip, knee, joint replacement = "Joint"
- clinical_notes: 2-3 sentence plain-English summary of the patient's situation and key clinical concerns
- recent_egd_within_3_months: if not mentioned and case is Bariatric, set to false
- has_registered_dietician: if patient says they saw a nutritionist "once" but does not have their own RD = false
"""

# ── Processing Functions ──────────────────────────────────────────────────────

# Default model; override with GEMINI_MODEL (e.g. gemini-2.5-flash)
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"


def extract_clinical_facts(transcript: str) -> dict:
    """Call the Clinical Processor to extract structured facts from transcript."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Export your Google AI Studio API key, e.g. "
            'export GEMINI_API_KEY="your-key"'
        )
    client = genai.Client(api_key=api_key)
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    last_exc = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=f"Extract clinical facts from this transcript:\n\n{transcript}",
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_SYSTEM_PROMPT,
                    temperature=0,
                    max_output_tokens=2500,
                    response_mime_type="application/json",
                ),
            )
            break
        except genai_errors.ClientError as e:
            status = getattr(e, "status_code", None)
            if status == 429:
                raise RuntimeError(
                    "Gemini API quota exceeded (HTTP 429). Your API key/project currently has no "
                    "available quota for this model. Check Gemini API quotas/billing, or try again "
                    "later if you are rate-limited."
                ) from e
            if status == 503 and attempt < 2:
                last_exc = e
                time.sleep(2 ** attempt)
                continue
            raise
    else:
        raise RuntimeError(
            "Gemini API is temporarily unavailable (HTTP 503). The model is overloaded — "
            "please try again in a few seconds."
        ) from last_exc
    if not response.text:
        raise RuntimeError(
            "Gemini returned no text; the response may have been blocked or empty. "
            "Check safety settings or try a different GEMINI_MODEL."
        )
    raw = response.text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    return json.loads(raw)


def derive_sop_flags(facts: dict) -> dict:
    """
    Deterministic SOP flag derivation from extracted facts.
    This layer contains zero probabilistic generation — pure rule matching.
    """
    flags = {}

    # GEN-001: Dental clearance needed
    dental_ok = facts.get("dental_last_visit_within_6_months")
    pending = facts.get("dental_pending_work")
    flags["dental_clearance_needed"] = (dental_ok is False) or (pending is True)

    # JNT-001: Active Smoker
    active = facts.get("active_smoker")
    quit_recent = facts.get("smoking_quit_within_3_months")
    flags["active_smoker"] = bool(active) or bool(quit_recent)

    # JNT-002: No formal PT history
    flags["no_pt_history"] = facts.get("has_pt_history") is False

    # JNT-003: HbA1c > 7.0
    hba1c = facts.get("hba1c_value")
    flags["hba1c_elevated"] = (hba1c is not None) and (float(hba1c) > 7.0)

    # JNT-004: Daily opioid > 3 months
    daily = facts.get("daily_opioid_use")
    duration = facts.get("opioid_duration_months") or 0
    flags["daily_opioid_over_3_months"] = bool(daily) and (float(duration) > 3)

    # BAR-001: Prior weight-loss surgery
    flags["prior_weight_loss_surgery"] = bool(facts.get("prior_weight_loss_surgery"))

    # BAR-002: No recent EGD
    flags["no_recent_egd"] = facts.get("recent_egd_within_3_months") is False

    # BAR-003: No RD
    flags["no_registered_dietician"] = facts.get("has_registered_dietician") is False

    return flags


def apply_sop_rules(flags: dict, case_type: str) -> list:
    """Match SOP flags to rules, filtered by case type."""
    triggered = []

    for rule in SOP_RULES:
        if rule["category"] not in ("General",) and rule["category"] != case_type:
            continue
        if flags.get(rule["fact_key"]) == rule["trigger_value"]:
            triggered.append({
                "rule_id": rule["id"],
                "category": rule["category"],
                "finding": rule["finding"],
                "case_status": rule["case_status"],
                "action": rule["action"],
            })

    triggered.sort(key=lambda r: STATUS_PRIORITY.get(r["case_status"], 99))
    return triggered


def determine_overall_status(triggered_rules: list) -> str:
    if not triggered_rules:
        return "Clear"
    statuses = [r["case_status"] for r in triggered_rules]
    return min(statuses, key=lambda s: STATUS_PRIORITY.get(s, 99))


def process_transcript(transcript: str) -> dict:
    """
    Full pipeline:
      1. Extract facts via Clinical Processor (LLM)
      2. Derive deterministic SOP flags (pure logic)
      3. Apply rule matching
      4. Return validated structured output
    """
    facts = extract_clinical_facts(transcript)
    case_type = facts.get("case_type", "Unknown")
    flags = derive_sop_flags(facts)
    triggered_rules = apply_sop_rules(flags, case_type)

    recommended_actions = [
        {
            "rule_id": rule["rule_id"],
            "status": rule["case_status"],
            "action": rule["action"],
        }
        for rule in triggered_rules
    ]

    overall_status = determine_overall_status(triggered_rules)

    return {
        "Patient_Facts": {
            "patient_name": facts.get("patient_name"),
            "case_type": case_type,
            "clinical_summary": facts.get("clinical_notes", ""),
            "extracted_details": {
                "dental_visit_within_6_months": facts.get("dental_last_visit_within_6_months"),
                "dental_pending_work": facts.get("dental_pending_work"),
                "active_smoker": facts.get("active_smoker"),
                "has_pt_history": facts.get("has_pt_history"),
                "pt_description": facts.get("pt_description"),
                "hba1c_value": facts.get("hba1c_value"),
                "daily_opioid_use": facts.get("daily_opioid_use"),
                "opioid_duration_months": facts.get("opioid_duration_months"),
                "opioid_medication": facts.get("opioid_medication"),
                "prior_weight_loss_surgery": facts.get("prior_weight_loss_surgery"),
                "prior_surgery_description": facts.get("prior_surgery_description"),
                "recent_egd": facts.get("recent_egd_within_3_months"),
                "has_registered_dietician": facts.get("has_registered_dietician"),
                "chronic_infections": facts.get("chronic_infections"),
                "other_conditions": facts.get("other_conditions"),
            }
        },
        "SOP_Flags": flags,
        "Logic_Results": triggered_rules,
        "Recommended_Actions": recommended_actions,
        "Overall_Case_Status": overall_status,
    }
