# Unit Test Report — Care Clinical Routing Navigator
**Date:** April 23, 2026
**Runtime:** 1.75s
**Result:** 45/45 passed · 0 failed · 0 skipped

---

## Overview

Unit tests cover the deterministic SOP logic layer (`logic_engine.py`) exclusively — no API calls, no LLM involvement. Every test runs against `derive_sop_flags`, `apply_sop_rules`, and `determine_overall_status` directly, with hand-constructed fact dictionaries as inputs. The suite completes in under 2 seconds and is suitable as a commit-level gate.

Run with:
```bash
pytest tests/test_unit.py -v
```

---

## Results by Class

### TestDentalClearance — 5/5 passed
Tests the `GEN-001` dental clearance flag (`dental_clearance_needed`).

| Test | What it verifies |
|---|---|
| `test_recent_visit_no_pending_no_flag` | Recent visit + no pending work → flag stays False |
| `test_no_visit_triggers` | No visit in 6 months → flag fires |
| `test_pending_work_triggers_even_with_recent_visit` | Pending crown overrides a recent visit — both must be checked |
| `test_upcoming_cleaning_not_pending_work` | Upcoming routine cleaning with no restorative work → flag stays False |
| `test_both_null_no_flag` | Both fields null → no flag (unknown ≠ negative) |

---

### TestSmoking — 5/5 passed
Tests the `JNT-001` smoking flag (`active_smoker`).

| Test | What it verifies |
|---|---|
| `test_active_smoker_triggers` | Current smoker → flag fires |
| `test_quit_within_3_months_triggers` | Quit 6 weeks ago = still within 3-month window → flag fires |
| `test_quit_long_ago_no_flag` | Quit years ago (e.g. 1987) → flag stays False |
| `test_never_smoked_no_flag` | Never smoked, no quit date → flag stays False |
| `test_null_smoking_no_flag` | Both fields null → no flag |

**Key boundary:** `smoking_quit_within_3_months = True` alone is sufficient to trigger the flag — a patient who recently quit is still blocked for surgical clearance.

---

### TestPhysicalTherapy — 3/3 passed
Tests the `JNT-002` PT flag (`no_pt_history`).

| Test | What it verifies |
|---|---|
| `test_has_pt_false_triggers` | Explicit False → flag fires (Ineligible) |
| `test_has_pt_true_no_flag` | Confirmed PT history → flag stays False |
| `test_null_pt_does_not_trigger` | Null (unknown) → flag stays False — unknown ≠ "no PT" |

**Key design decision:** `null` does not trigger the flag. The rule is `has_pt_history is False` — only an explicit negative blocks the case. This prevents routing errors when a patient's PT history is genuinely unconfirmed.

---

### TestHbA1c — 5/5 passed
Tests the `JNT-003` HbA1c flag (`hba1c_elevated`). Rule: strictly `> 7.0`.

| Test | What it verifies |
|---|---|
| `test_below_threshold_no_flag` | 6.8 → no flag |
| `test_exactly_7_not_elevated` | **7.0 is NOT > 7.0** — boundary must not fire |
| `test_above_threshold_triggers` | 7.1 → flag fires |
| `test_high_value_triggers` | 8.2 (Gerald scenario) → flag fires |
| `test_null_no_flag` | No HbA1c value → no flag |

**Critical boundary:** HbA1c = 7.0 must **not** trigger the Review flag. The SOP rule is strictly greater than, not greater-than-or-equal. This is explicitly verified.

---

### TestOpioids — 6/6 passed
Tests the `JNT-004` opioid flag (`daily_opioid_over_3_months`). Rule: daily use AND duration strictly `> 3` months.

| Test | What it verifies |
|---|---|
| `test_daily_under_3_months_no_flag` | 2 months daily → no flag |
| `test_daily_exactly_3_months_no_flag` | **Exactly 3.0 months is NOT > 3** — boundary must not fire |
| `test_daily_over_3_months_triggers` | 3.1 months → flag fires |
| `test_daily_2_years_triggers` | 24 months (Gerald/Bob scenario) → flag fires |
| `test_not_daily_no_flag` | Twice-weekly use (Patricia's tramadol) → no flag |
| `test_null_use_no_flag` | Unknown medication → no flag |

**Critical boundary:** Opioid duration of exactly 3 months must **not** trigger High Complexity. Both conditions must be true simultaneously: daily use AND duration > 3 months.

---

### TestBariatricFlags — 6/6 passed
Tests `BAR-001` (prior surgery), `BAR-002` (EGD recency), `BAR-003` (RD credential).

| Test | What it verifies |
|---|---|
| `test_prior_surgery_triggers` | Prior weight-loss surgery → Revision Case flag fires |
| `test_no_prior_surgery_no_flag` | First surgery → no flag |
| `test_no_recent_egd_triggers` | No EGD in 3 months → flag fires |
| `test_recent_egd_5_weeks_no_flag` | EGD 5 weeks ago = within 3 months → no flag |
| `test_no_rd_triggers` | No Registered Dietician → Hold flag fires |
| `test_has_rd_no_flag` | Confirmed RD → no flag |

---

### TestApplySopRules — 8/8 passed
Tests rule matching, case-type filtering, and severity ordering in `apply_sop_rules`.

| Test | What it verifies |
|---|---|
| `test_no_flags_no_rules_fired` | All-clear flags → empty rule list |
| `test_joint_rules_dont_fire_for_bariatric` | JNT-001, JNT-002 skipped when case_type = Bariatric |
| `test_bariatric_rules_dont_fire_for_joint` | BAR-001/002/003 skipped when case_type = Joint |
| `test_gen001_fires_for_joint` | GEN-001 (dental) fires for Joint cases |
| `test_gen001_fires_for_bariatric` | GEN-001 (dental) fires for Bariatric cases |
| `test_results_sorted_by_severity` | Output sorted: Ineligible → High Complexity → Deferred |
| `test_all_joint_flags_returns_five_rules` | All 5 Joint flags → 5 rules returned |
| `test_all_bariatric_flags_returns_four_rules` | All 4 Bariatric flags → 4 rules returned |

**Key invariant:** GEN-001 is the only General-category rule and must fire for both case types. Joint and Bariatric rules are mutually exclusive.

---

### TestOverallStatus — 7/7 passed
Tests the severity priority ladder in `determine_overall_status`.

| Test | What it verifies |
|---|---|
| `test_no_rules_is_clear` | No triggered rules → Clear |
| `test_single_rule_returns_its_status` | One rule → that rule's status |
| `test_ineligible_beats_all_others` | Ineligible wins over Deferred, Review, Hold |
| `test_high_complexity_beats_deferred` | High Complexity outranks Deferred |
| `test_revision_case_beats_review` | Revision Case outranks Review |
| `test_action_required_beats_hold` | Action Required outranks Hold |
| `test_gerald_scenario_ineligible` | All 5 statuses present → Ineligible wins |

**Priority ladder (lowest index = most severe):**

| Priority | Status |
|---|---|
| 0 | Ineligible |
| 1 | High Complexity |
| 2 | Deferred |
| 3 | Revision Case |
| 4 | Review |
| 5 | Action Required |
| 6 | Hold |
| 7 | Clear |

---

## Coverage

Unit tests cover 100% of the deterministic logic layer. The remaining uncovered lines (41%) are in the LLM integration path (`extract_clinical_facts`, `process_transcript`) which requires a live API call — those are covered by the eval suite.

```
Name              Stmts   Miss  Cover   Missing
-----------------------------------------------
logic_engine.py      78     32    59%   171-218, 297-313
-----------------------------------------------
```

Lines 171–218: `extract_clinical_facts` (Gemini API call + retry loop)
Lines 297–313: `process_transcript` (pipeline orchestration)

Run with coverage:
```bash
pytest tests/test_unit.py --cov=logic_engine --cov-report=term-missing
```
