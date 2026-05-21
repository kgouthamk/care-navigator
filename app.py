"""
Care Navigator — Automated Clinical Routing Navigator
Streamlit Application
"""

import json
import os
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError
from logic_engine import process_transcript, STATUS_COLORS, SOP_RULES

# Load API credentials from Streamlit secrets (preferred) into env vars (used by logic_engine).
try:
    if "GEMINI_API_KEY" in st.secrets:
        os.environ["GEMINI_API_KEY"] = str(st.secrets["GEMINI_API_KEY"])
    if "GEMINI_MODEL" in st.secrets:
        os.environ["GEMINI_MODEL"] = str(st.secrets["GEMINI_MODEL"])
except StreamlitSecretNotFoundError:
    # No secrets file configured; fall back to env vars.
    pass

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Care Clinical Navigator",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
  }

  .main { background-color: #F7F6F3; }
  .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 1400px; }

  /* Header */
  .nav-header {
    background: #0A1628;
    color: white;
    padding: 1.25rem 2rem;
    border-radius: 12px;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1rem;
  }
  .nav-header h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 1.6rem;
    margin: 0;
    color: #E8F4FD;
    letter-spacing: -0.5px;
  }
  .nav-header .subtitle {
    font-size: 0.78rem;
    color: #7BA3C8;
    font-weight: 400;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .nav-badge {
    background: #1A3A5C;
    border: 1px solid #2A5A8C;
    color: #7BC4E8;
    padding: 0.25rem 0.75rem;
    border-radius: 100px;
    font-size: 0.7rem;
    font-family: 'DM Mono', monospace;
    margin-left: auto;
  }

  /* Panel cards */
  .panel-card {
    background: white;
    border-radius: 12px;
    border: 1px solid #E5E2DC;
    padding: 1.5rem;
    height: 100%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
  }
  .panel-label {
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #9E9990;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #F0EDE8;
  }

  /* Status badge */
  .status-pill {
    display: inline-block;
    padding: 0.35rem 1rem;
    border-radius: 100px;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: white;
  }

  /* Action cards */
  .action-card {
    border-left: 3px solid;
    padding: 0.85rem 1rem;
    border-radius: 0 8px 8px 0;
    margin-bottom: 0.75rem;
    background: #FAFAF8;
  }
  .action-rule-id {
    font-family: 'DM Mono', monospace;
    font-size: 0.68rem;
    color: #9E9990;
    margin-bottom: 0.2rem;
  }
  .action-status {
    font-weight: 600;
    font-size: 0.82rem;
    margin-bottom: 0.3rem;
  }
  .action-text {
    font-size: 0.85rem;
    color: #3D3A35;
    line-height: 1.5;
  }

  /* Fact table */
  .fact-row {
    display: flex;
    align-items: flex-start;
    padding: 0.6rem 0;
    border-bottom: 1px solid #F5F2EE;
    gap: 1rem;
  }
  .fact-label {
    font-size: 0.78rem;
    color: #7A756E;
    width: 200px;
    flex-shrink: 0;
    padding-top: 0.1rem;
  }
  .fact-value {
    font-size: 0.82rem;
    font-weight: 500;
    color: #1C1A17;
    flex: 1;
  }
  .fact-true { color: #DC4A3A; }
  .fact-false { color: #2D7D4A; }
  .fact-null { color: #BCBAB5; font-style: italic; }

  /* Transcript display */
  .transcript-box {
    background: #FAFAF8;
    border: 1px solid #EAE7E2;
    border-radius: 8px;
    padding: 1rem;
    font-size: 0.83rem;
    line-height: 1.7;
    color: #3D3A35;
    max-height: 520px;
    overflow-y: auto;
    font-family: 'DM Mono', monospace;
    white-space: pre-wrap;
  }

  /* Summary box */
  .summary-box {
    background: #EEF4FB;
    border: 1px solid #C5D9EE;
    border-radius: 8px;
    padding: 1rem 1.25rem;
    font-size: 0.88rem;
    color: #1A3A5C;
    line-height: 1.65;
    margin-bottom: 1rem;
  }

  /* Patient header */
  .patient-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding-bottom: 0.75rem;
    border-bottom: 1px solid #EAE7E2;
  }
  .patient-name {
    font-family: 'DM Serif Display', serif;
    font-size: 1.35rem;
    color: #1C1A17;
  }
  .case-type-tag {
    background: #F0EDE8;
    color: #6B6560;
    padding: 0.25rem 0.75rem;
    border-radius: 6px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* JSON viewer */
  .json-block {
    background: #1C1A17;
    color: #A8E6CF;
    border-radius: 8px;
    padding: 1rem;
    font-family: 'DM Mono', monospace;
    font-size: 0.75rem;
    max-height: 400px;
    overflow-y: auto;
    line-height: 1.6;
  }

  /* Verification checks */
  .verify-item {
    background: #FAFAF8;
    border: 1px solid #EAE7E2;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    font-size: 0.84rem;
  }

  /* Upload zone */
  .upload-hint {
    text-align: center;
    padding: 2rem;
    color: #9E9990;
    font-size: 0.88rem;
  }

  /* Statemet counters */
  .metric-row {
    display: flex;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }
  .metric-box {
    flex: 1;
    background: #F7F6F3;
    border: 1px solid #EAE7E2;
    border-radius: 8px;
    padding: 0.75rem;
    text-align: center;
  }
  .metric-num {
    font-family: 'DM Serif Display', serif;
    font-size: 1.6rem;
    color: #1C1A17;
    line-height: 1;
  }
  .metric-lbl {
    font-size: 0.68rem;
    color: #9E9990;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-top: 0.2rem;
  }

  /* Streamlit overrides */
  div[data-testid="stFileUploader"] {
    border: 2px dashed #D5D0C8 !important;
    border-radius: 10px !important;
    background: #FAFAF8 !important;
  }
  div[data-testid="stButton"] button {
    background: #0A1628;
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    font-family: 'DM Sans', sans-serif;
    letter-spacing: 0.02em;
    transition: background 0.2s;
  }
  div[data-testid="stButton"] button:hover {
    background: #1A3A5C;
  }
  .stTextArea textarea {
    font-family: 'DM Mono', monospace;
    font-size: 0.82rem;
    border-radius: 8px;
    border: 1px solid #EAE7E2;
  }
  .stAlert {
    border-radius: 8px;
  }
  div[data-testid="stExpander"] {
    border: 1px solid #EAE7E2 !important;
    border-radius: 8px !important;
  }
</style>
""", unsafe_allow_html=True)

# ── Sample Transcripts ────────────────────────────────────────────────────────

SAMPLE_TRANSCRIPTS = {
    "Sample 1 — Sarah T. (Bariatric)": """Care Team: "Hi Sarah, I just wanted to verify a few details from your pre-consultation profile. To get you scheduled for your consultation, we need to clarify your surgical history. You mentioned you'd already had a prior weight-loss procedure. Could you tell me exactly what that was and when?"
Sarah T: "Yeah, I had the lap band put in back in 2017 in Philadelphia. I'm having it removed and hopefully getting the sleeve done now. Does that matter?"
Care Team: "It does, thank you. One quick check—your employer's plan is paired with ABC Hospital. Are you working with a Registered Dietician (RD) currently?"
Sarah T: "Um, well, yes, Dr. Jones's referred me to a nutritionist like three months ago when I started this process. I saw him once, but I don't really have my own RD."
Care Team: "Got it, that's okay. We just need to ensure you have one identified before we refer you over. We will also need an endoscopy done before we can schedule surgery itself, so try to schedule that for right after your consult. Now, looking at your medical conditions, can you confirm if you are on any chronic immune suppression, or if you have any active infection, open wounds, or active cancer treatment?"
Sarah T: "No active cancer. But, well, a chronic infection, I guess. I get these recurrent urinary tract infections all the time, maybe like once every couple of months. Is that a problem?"
Care Team: "Okay, we'll note that down. Finally, any pending major dental work needed, and have you seen a dentist in the last 6 months?"
Sarah T: "Yes, I just had my clean-up done in May, so I'm good there."
Care Team: "Great, thanks Sarah. We'll finalize this part of your profile and get you set up for an initial consult." """,

    "Sample 2 — Bob L. (Joint)": """[Care Team] Hi Bob, this is the Care Navigator team. We are wrapping up your initial profile to get you matched with your surgeon. We need to clarify a few answers from your questionnaire.
[Bob L] ok what do you need? my hip is killing me.
[Care Team] We're here to help. First, can you confirm if you have used any prescription pain medications, even just sometimes, to manage the hip pain?
[Bob L] yeah. My PCP gave me oxycodone 5mg to take when it was really bad, but i've been on it pretty much daily for 2 years.
[Care Team] Thank you, that's important for the anesthesiologist to know. Moving to your medical history—do you have any history of lower extremity severe trauma or deformity (accidents that required major surgery)?
[Bob L] No, never broke a leg. But I did have a blood clot in my right leg after I broke my ankle in college, if that counts.
[Care Team] Yes, we will note that history of blood clots. Are you currently using a walker or wheelchair and unable to walk more than 30 feet?
[Bob L] No, I still limp around on my own. Just. it hurts.
[Care Team] Got it. Last question for this step: Our records say you haven't attempted any conservative treatment, specifically physical therapy, for this hip pain. Is that correct?
[Bob L] I mean, i tried it. I did like two sessions of exercises in the gym. But it didn't help. This has to be surgical.
[Care Team] Got it. Thanks Bob! We have what we need. We'll be tough on next steps in the next 48 hours.""",

    "Sample 3 — Maria V. (Joint)": """Care Team: "Hi Maria, I'm just trying to verify the final pieces of information for your intake so we can route your case appropriately. We need to check on your comorbidities. Do you have a history of HIV, AIDS, end-stage renal failure, or active cancer treatment?"
Maria V: "Look, I've already answered these questions for my regular doctor three times this month. Why does Care Navigator need them again? I don't have any of those things. I'm just getting old and my knee is falling apart because nobody will help me!"
Care Team: "I understand the frustration, Maria. We just want to make sure we have the most current info for the surgeon. How about your blood sugar? If you have diabetes, do you know what your last HbA1c lab result was? The most recent one."
Maria V: "I just had my physical last week and my doctor was annoyed because it was a 7.4. He's always nagging me to work on that, but it's hard when you can't walk to exercise!"
Care Team: "I hear you. That 7.4 is a helpful number for us to have. Let's talk about lifestyle—and please be honest so we can keep you safe during surgery. Are you currently an active smoker, or have you quit within the last three months?"
Maria V: "Is this where you tell me I can't have surgery because I have a cigarette with my coffee? Yes, I'm active. I smoke maybe a half-pack a day. I tried to quit last year and I lasted two weeks and was miserable the whole time. Are you going to deny me for that?"
Care Team: "We're just gathering the facts for now, Maria. Have you been using oxygen dependence at home? And any substance or alcohol issues?"
Maria V: "No oxygen, my lungs are the only thing that do work. And no, no substances. Now, are we done? I have an appointment."
Care Team: "One last piece, Maria. Regarding your conservative treatment: have you already had a course of formal physical therapy with a professional therapist for this knee pain?"
Maria V: "Yes! I told the other lady this already! I did 12 weeks of PT with ABC Physical Therapy down the road. It was three days a week and it was exhausting. It helped for a little while, but then the pain came right back. I've done my time with the exercises."
Care Team: "Perfect, that's exactly the information we need. And Maria, I hear the frustration in your voice. I know it's exhausting to repeat your history and feel like you're stuck in a loop when you just want to feel better."
Maria V: "I know... I just want to be able to walk to the mailbox without sitting down. It's a lot to manage on my own."
Care Team: "We're going to help you manage it. Here is what happens next: I'm going to review your details and follow up by Thursday afternoon with a clear roadmap for the next few weeks."
Maria V: "Yes. Thursday afternoon. I'll be waiting for the call. Thank you for listening to me complain."
Care Team: "You aren't complaining, Maria—you're advocating for your health. We're glad to have you with Care Navigator." """,
}

# ── Helper Renderers ──────────────────────────────────────────────────────────

def render_bool_fact(val):
    if val is True:
        return '<span class="fact-value fact-true">✓ Yes</span>'
    elif val is False:
        return '<span class="fact-value fact-false">✗ No</span>'
    else:
        return '<span class="fact-value fact-null">not mentioned</span>'

def render_status_pill(status: str) -> str:
    color = STATUS_COLORS.get(status, "#6B7280")
    return f'<span class="status-pill" style="background:{color}">{status}</span>'

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nav-header">
  <div>
    <div class="subtitle">Care Navigator</div>
    <h1>Clinical Routing Navigator</h1>
  </div>
  <div class="nav-badge">Clinical Processor v1.0</div>
</div>
""", unsafe_allow_html=True)

# ── Input Section ─────────────────────────────────────────────────────────────

st.markdown("#### Load Transcript")

input_col1, input_col2 = st.columns([1, 1])

with input_col1:
    sample_choice = st.selectbox(
        "Load a sample transcript",
        ["— Select a sample —"] + list(SAMPLE_TRANSCRIPTS.keys()),
        label_visibility="collapsed"
    )

with input_col2:
    uploaded_file = st.file_uploader(
        "Or upload a .txt file",
        type=["txt"],
        label_visibility="collapsed"
    )

# Determine transcript source
transcript_text = ""
if uploaded_file is not None:
    transcript_text = uploaded_file.read().decode("utf-8")
elif sample_choice != "— Select a sample —":
    transcript_text = SAMPLE_TRANSCRIPTS[sample_choice]

# Text area (editable)
transcript_input = st.text_area(
    "Transcript",
    value=transcript_text,
    height=160,
    placeholder="Paste a patient transcript here, upload a .txt file, or select a sample above…",
    label_visibility="collapsed",
)

process_btn = st.button("⚡  Analyze Transcript", use_container_width=False)

st.divider()

# ── Processing & Results ──────────────────────────────────────────────────────

if process_btn:
    if not transcript_input.strip():
        st.warning("Please provide a transcript before analyzing.")
    else:
        with st.spinner("Clinical Processor is extracting facts and applying SOP logic…"):
            try:
                result = process_transcript(transcript_input)
                st.session_state["result"] = result
                st.session_state["transcript"] = transcript_input
                st.session_state["verified_facts"] = {}
            except Exception as e:
                st.error(f"Processing error: {str(e)}")
                st.stop()

# Display results from session state
if "result" in st.session_state:
    result = st.session_state["result"]
    pf = result["Patient_Facts"]
    details = pf.get("extracted_details", {})
    actions = result["Recommended_Actions"]
    logic = result["Logic_Results"]
    overall = result["Overall_Case_Status"]
    overall_color = STATUS_COLORS.get(overall, "#6B7280")

    # ── Top summary bar ──
    patient_name = pf.get("patient_name") or "Unknown Patient"
    case_type = pf.get("case_type", "Unknown")

    st.markdown(f"""
    <div class="patient-header">
      <div class="patient-name">{patient_name}</div>
      <div style="display:flex;gap:0.75rem;align-items:center;">
        <span class="case-type-tag">{case_type}</span>
        {render_status_pill(overall)}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Metrics row
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown(f"""<div class="metric-box"><div class="metric-num">{len(logic)}</div><div class="metric-lbl">Rules Triggered</div></div>""", unsafe_allow_html=True)
    with col_m2:
        st.markdown(f"""<div class="metric-box"><div class="metric-num">{len(actions)}</div><div class="metric-lbl">Actions Required</div></div>""", unsafe_allow_html=True)
    with col_m3:
        flags_true = sum(1 for v in result["SOP_Flags"].values() if v)
        st.markdown(f"""<div class="metric-box"><div class="metric-num">{flags_true}</div><div class="metric-lbl">Flags Raised</div></div>""", unsafe_allow_html=True)
    with col_m4:
        st.markdown(f"""<div class="metric-box"><div class="metric-num" style="color:{overall_color}">{overall}</div><div class="metric-lbl">Overall Status</div></div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Main two-column layout ──
    left_col, right_col = st.columns([1, 1], gap="medium")

    # LEFT: Transcript + Extracted Facts
    with left_col:
        st.markdown('<div class="panel-label">Original Transcript</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="transcript-box">{st.session_state["transcript"]}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="panel-label">Extracted Clinical Facts</div>', unsafe_allow_html=True)

        facts_display = [
            ("Dental visit within 6 months", render_bool_fact(details.get("dental_visit_within_6_months"))),
            ("Pending dental work", render_bool_fact(details.get("dental_pending_work"))),
            ("Active smoker", render_bool_fact(details.get("active_smoker"))),
            ("Formal PT history", render_bool_fact(details.get("has_pt_history"))),
            ("PT description", f'<span class="fact-value">{details.get("pt_description") or "<span class=\'fact-null\'>—</span>"}</span>'),
            ("HbA1c value", f'<span class="fact-value">{details.get("hba1c_value") or "<span class=\'fact-null\'>not mentioned</span>"}</span>'),
            ("Daily opioid use", render_bool_fact(details.get("daily_opioid_use"))),
            ("Opioid duration (months)", f'<span class="fact-value">{details.get("opioid_duration_months") or "<span class=\'fact-null\'>—</span>"}</span>'),
            ("Opioid medication", f'<span class="fact-value">{details.get("opioid_medication") or "<span class=\'fact-null\'>—</span>"}</span>'),
            ("Prior weight-loss surgery", render_bool_fact(details.get("prior_weight_loss_surgery"))),
            ("Prior surgery description", f'<span class="fact-value">{details.get("prior_surgery_description") or "<span class=\'fact-null\'>—</span>"}</span>'),
            ("Recent EGD (< 3 months)", render_bool_fact(details.get("recent_egd"))),
            ("Registered Dietician", render_bool_fact(details.get("has_registered_dietician"))),
            ("Chronic infections", f'<span class="fact-value">{details.get("chronic_infections") or "<span class=\'fact-null\'>—</span>"}</span>'),
        ]

        for label, val_html in facts_display:
            st.markdown(f"""
            <div class="fact-row">
              <div class="fact-label">{label}</div>
              {val_html}
            </div>
            """, unsafe_allow_html=True)

    # RIGHT: Summary + Recommendations + Verification
    with right_col:
        st.markdown('<div class="panel-label">Clinical Summary</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="summary-box">{pf.get("clinical_summary", "No summary generated.")}</div>', unsafe_allow_html=True)

        st.markdown('<div class="panel-label">SOP-Driven Recommendations</div>', unsafe_allow_html=True)

        if not actions:
            st.success("✅ No blocking SOP conditions identified. Case may proceed.")
        else:
            for action in actions:
                color = STATUS_COLORS.get(action["status"], "#6B7280")
                st.markdown(f"""
                <div class="action-card" style="border-left-color:{color}">
                  <div class="action-rule-id">{action["rule_id"]}</div>
                  <div class="action-status" style="color:{color}">{action["status"]}</div>
                  <div class="action-text">{action["action"]}</div>
                </div>
                """, unsafe_allow_html=True)

        # Verification section
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="panel-label">Human-in-the-Loop Verification</div>', unsafe_allow_html=True)
        st.caption("Review the extracted facts below. Correct any that appear inaccurate before finalizing.")

        verify_facts = {
            "dental_visit_within_6_months": ("Dental visit within 6 months?", details.get("dental_visit_within_6_months")),
            "active_smoker": ("Active smoker?", details.get("active_smoker")),
            "has_pt_history": ("Has formal PT history?", details.get("has_pt_history")),
            "hba1c_elevated": ("HbA1c > 7.0?", result["SOP_Flags"].get("hba1c_elevated")),
            "daily_opioid_over_3_months": ("Daily opioid use > 3 months?", result["SOP_Flags"].get("daily_opioid_over_3_months")),
            "prior_weight_loss_surgery": ("Prior weight-loss surgery?", details.get("prior_weight_loss_surgery")),
            "recent_egd": ("Recent EGD (< 3 months)?", details.get("recent_egd")),
            "has_registered_dietician": ("Has Registered Dietician?", details.get("has_registered_dietician")),
        }

        corrections = {}
        for key, (label, extracted_val) in verify_facts.items():
            if extracted_val is None:
                options = ["Unknown / Not Mentioned", "Yes", "No"]
                default_idx = 0
            elif extracted_val:
                options = ["Yes", "No", "Unknown / Not Mentioned"]
                default_idx = 0
            else:
                options = ["No", "Yes", "Unknown / Not Mentioned"]
                default_idx = 0

            chosen = st.selectbox(
                label,
                options,
                index=default_idx,
                key=f"verify_{key}"
            )
            corrections[key] = chosen

        if st.button("✅  Confirm & Finalize Record", use_container_width=True):
            final_output = {
                "Patient_Facts": pf,
                "SOP_Flags": result["SOP_Flags"],
                "Logic_Results": result["Logic_Results"],
                "Recommended_Actions": result["Recommended_Actions"],
                "Overall_Case_Status": result["Overall_Case_Status"],
                "Care_Team_Verification": corrections,
                "Record_Status": "Verified",
            }
            st.success("✅ Record verified and finalized by Care Team.")
            st.download_button(
                label="⬇ Download Finalized JSON",
                data=json.dumps(final_output, indent=2),
                file_name=f"care_{(patient_name or 'patient').replace(' ', '_').lower()}_routing.json",
                mime="application/json",
                use_container_width=True,
            )

    # ── Raw JSON Output ──
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("🔍 View Raw Validated JSON Output", expanded=False):
        st.markdown('<div class="panel-label">Validated JSON — Logic Engine Output</div>', unsafe_allow_html=True)
        st.json(result)

else:
    # Empty state
    st.markdown("""
    <div class="upload-hint">
      <div style="font-size:2.5rem;margin-bottom:0.75rem;">🏥</div>
      <div style="font-weight:600;color:#3D3A35;margin-bottom:0.4rem;">No transcript loaded</div>
      <div>Select a sample above or paste/upload a patient transcript to begin routing analysis.</div>
    </div>
    """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="text-align:center;font-size:0.72rem;color:#BCBAB5;font-family:\'DM Mono\',monospace;">Care Navigator · Clinical Routing Navigator · Automated Logic Engine · For internal Care Team use only</div>',
    unsafe_allow_html=True
)
