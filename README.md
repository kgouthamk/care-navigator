# Care Navigator — Automated Clinical Routing Navigator

## Overview

A protocol-driven decision-support tool for the Care Team. Processes raw patient
transcripts, extracts clinical facts via an LLM, and applies deterministic SOP rules to
generate routing recommendations with human-in-the-loop verification.

---

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- A [Google AI Studio](https://aistudio.google.com/apikey) Gemini API key

### 2. Install runtime dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Set your API key

#### Option A (recommended): Streamlit secrets (no terminal export needed)

Create `.streamlit/secrets.toml` (this file is git-ignored):

```toml
GEMINI_API_KEY = "your-key-here"
GEMINI_MODEL = "gemini-2.5-flash"   # recommended; default is gemini-2.0-flash
```

> **Important:** `secrets.toml` always takes precedence over environment variables.
> If you update your key, restart the Streamlit server for it to take effect.

#### Option B: Environment variables (per terminal session)
```bash
export GEMINI_API_KEY="your-key-here"
export GEMINI_MODEL="gemini-2.5-flash"   # optional
```

### 4. Run the app
```bash
source .venv/bin/activate
streamlit run app.py
```

The app will open at `http://localhost:8501`

---

## Testing

The test suite is split into two tiers: fast unit tests (no API calls) and LLM eval tests
(require an API key and burn quota — opt-in only).

### Install dev dependencies
```bash
pip install -r requirements-dev.txt
```

### Unit tests — run on every change (fast, no API)

Tests all deterministic logic in `logic_engine.py`: flag derivation, SOP rule matching,
status priority, and every boundary case in the answer key.

```bash
pytest
# or verbosely:
pytest -v
```

**What's covered (45 tests):**

| Class | What it tests |
|---|---|
| `TestDentalClearance` | Pending work fires even with a recent visit; upcoming cleaning does not |
| `TestSmoking` | Quit within 3 months still counts as active smoker |
| `TestPhysicalTherapy` | `null` ≠ `False` — unknown PT history does not block the case |
| `TestHbA1c` | 7.0 is **not** > 7.0 (boundary); null → no flag |
| `TestOpioids` | Exactly 3 months is **not** > 3 months (boundary); twice-a-week ≠ daily |
| `TestBariatricFlags` | EGD recency, RD credential presence |
| `TestApplySopRules` | Joint rules skip Bariatric cases and vice versa; GEN-001 fires for all |
| `TestOverallStatus` | Severity ladder: Ineligible beats all; priority ordering across all statuses |

### LLM eval tests — run on demand (hits the Gemini API)

Runs the full pipeline (`process_transcript`) against 10 hand-crafted transcripts in
`additional_transcripts/` and checks `SOP_Flags` + `Overall_Case_Status` against the
hand-authored answer key (`additional_transcripts/EVAL_ANSWER_KEY.md`).

```bash
# Option 1: CLI flag
pytest --run-evals -v

# Option 2: environment variable
RUN_EVALS=1 pytest -v
```

**What each eval covers:**

| # | Patient | Case type | Expected status | Key test |
|---|---|---|---|---|
| 01 | James R. | Joint | Clear | Happy path; HbA1c 6.8 does not fire |
| 02 | Denise K. | Joint | Deferred | Quit 6 weeks ago = still within 3-month window |
| 03 | Marcus T. | Bariatric | Clear | Sandra Okonkwo RD recognized as valid RD |
| 04 | Patricia M. | Joint | Clear | HbA1c = 7.0 boundary; cleaning ≠ pending work; twice-weekly tramadol ≠ daily opioid |
| 05 | Linda F. | Bariatric | Revision Case | Weight Watchers ≠ RD; all 4 flags fire simultaneously |
| 06 | Raymond G. | Joint | Action Required | Opioid = 3 months boundary; pending crown fires even if "not urgent" |
| 07 | Trevor N. | Joint | Ineligible | LA Fitness personal trainer ≠ formal PT; meloxicam ≠ opioid |
| 08 | Camille B. | Bariatric | Hold | Gym nutritionist w/ unknown credentials ≠ RD; EGD 5 weeks ago is within range |
| 09 | Gerald O. | Joint | Ineligible | All 5 flags fire; 2 PT sessions ≠ formal PT |
| 10 | Dorothy W. | Joint | (see note) | Quit 1987 = not active; unknown medication ≠ assumed opioid; null handling |

> **Known limitation (Dorothy #10):** When key fields are genuinely ambiguous, the system
> currently returns `Clear` instead of a "needs follow-up" status. This is a documented gap
> that requires a schema change to add an `Incomplete` overall status.

---

## File Structure

```
care-navigator/
├── app.py                          # Streamlit UI application
├── logic_engine.py                 # Clinical Processor + SOP Engine
├── requirements.txt                # Runtime dependencies
├── requirements-dev.txt            # Dev/test dependencies (pytest)
├── pytest.ini                      # Test configuration
├── tests/
│   ├── conftest.py                 # Secrets loading, --run-evals flag
│   ├── test_unit.py                # 45 deterministic unit tests (no API)
│   └── test_evals.py               # 10 LLM eval tests (opt-in, API required)
└── additional_transcripts/
    ├── 01_james_joint_all_clear.txt
    ├── ...
    └── EVAL_ANSWER_KEY.md          # Hand-authored ground truth for evals
```

---

## Architecture

```
Transcript (raw text)
        │
        ▼
┌─────────────────────────────┐
│  Layer 1: Clinical Processor │  ← LLM (Google Gemini, temperature=0)
│  Extract structured facts    │     Handles ambiguity,
│  → JSON schema output        │     colloquial phrasing
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Layer 2: SOP Engine         │  ← Pure Python
│  Deterministic rule matching │     Boolean predicates
│  → Triggered rules + actions │     No probabilistic output
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│  Layer 3: Human Verification │  ← Care Team Navigator
│  Review & correct facts      │     Confirms before commit
│  → Finalized JSON record     │
└─────────────────────────────┘
```

---

## SOP Rules Implemented

| ID      | Category  | Finding                        | Status          |
|---------|-----------|--------------------------------|-----------------|
| GEN-001 | General   | Dental visit > 6 months        | Action Required |
| JNT-001 | Joint     | Active smoker / quit < 3 mo    | Deferred        |
| JNT-002 | Joint     | No formal PT attempt           | Ineligible      |
| JNT-003 | Joint     | HbA1c > 7.0                    | Review          |
| JNT-004 | Joint     | Daily opioid use > 3 months    | High Complexity |
| BAR-001 | Bariatric | Prior weight-loss surgery      | Revision Case   |
| BAR-002 | Bariatric | No EGD in last 3 months        | Action Required |
| BAR-003 | Bariatric | No Registered Dietician        | Hold            |

---

## Deploying to Streamlit Community Cloud

1. Push code to a GitHub repository
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo, set `app.py` as the main file
4. Add `GEMINI_API_KEY` and `GEMINI_MODEL` in the Secrets manager
5. Deploy

---

## Output JSON Schema

```json
{
  "Patient_Facts": {
    "patient_name": "string",
    "case_type": "Joint | Bariatric | Unknown",
    "clinical_summary": "string",
    "extracted_details": { ... }
  },
  "SOP_Flags": { "flag_key": true | false },
  "Logic_Results": [
    {
      "rule_id": "JNT-001",
      "category": "Joint",
      "finding": "...",
      "case_status": "Deferred",
      "action": "..."
    }
  ],
  "Recommended_Actions": [
    { "rule_id": "...", "status": "...", "action": "..." }
  ],
  "Overall_Case_Status": "Deferred",
  "Care_Team_Verification": { ... },
  "Record_Status": "Verified"
}
```
