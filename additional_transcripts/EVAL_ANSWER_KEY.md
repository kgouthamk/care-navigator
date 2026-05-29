# Eval Answer Key — Care Clinical Routing Navigator
# 10 Test Transcripts: Expected Outputs

---

## 01 — James R. | Joint | ALL CLEAR
**Purpose:** Baseline happy path. Every condition is met. Nothing should fire.

| Flag | Expected | Reasoning |
|---|---|---|
| dental_clearance_needed | FALSE | Visit 2 months ago, no pending work |
| active_smoker | FALSE | Never smoked |
| no_pt_history | FALSE | 8 weeks at Riverside PT |
| hba1c_elevated | FALSE | 6.8 — below 7.0 threshold |
| daily_opioid_over_3_months | FALSE | Only ibuprofen, no opioids |

**Expected Overall Status:** Clear
**Expected Actions:** None
**Critical Check:** Confirm that HbA1c 6.8 does NOT trigger the Review rule.

---

## 02 — Denise K. | Joint | DEFERRED (Smoking — quit 6 weeks ago)
**Purpose:** Tests the "quit < 3 months" edge case. She quit — but not long enough.

| Flag | Expected | Reasoning |
|---|---|---|
| active_smoker | TRUE | Quit only 6 weeks ago — within 3 month window |
| no_pt_history | FALSE | 10 weeks at Apex PT |
| dental_clearance_needed | FALSE | Visit in March, no pending work |
| hba1c_elevated | FALSE | Non-diabetic, never tested |
| daily_opioid_over_3_months | FALSE | Only Tylenol |

**Expected Overall Status:** Deferred
**Expected Actions:** Smoking cessation referral; pause case 3 months
**Critical Check:** Confirm "just quit 6 weeks ago" correctly maps to active_smoker: TRUE.

---

## 03 — Marcus T. | Bariatric | ALL CLEAR
**Purpose:** Baseline bariatric happy path. Every bariatric condition is satisfied.

| Flag | Expected | Reasoning |
|---|---|---|
| prior_weight_loss_surgery | FALSE | First surgery |
| no_recent_egd | FALSE | EGD 6 weeks ago |
| no_registered_dietician | FALSE | Sandra Okonkwo RD, established ongoing care |
| dental_clearance_needed | FALSE | Visit in January, no pending work |

**Expected Overall Status:** Clear
**Expected Actions:** None
**Critical Check:** Confirm Sandra Okonkwo, RD is correctly recognized as a valid Registered Dietician.

---

## 04 — Patricia M. | Joint | DENTAL ACTION REQUIRED (HbA1c boundary test)
**Purpose:** Tests the HbA1c = 7.0 boundary. Exactly 7.0 should NOT trigger Review.
Also tests "cleaning next week" = upcoming visit, not pending work.

| Flag | Expected | Reasoning |
|---|---|---|
| hba1c_elevated | FALSE | 7.0 is NOT greater than 7.0 |
| dental_clearance_needed | FALSE | Upcoming appointment is a cleaning only, no pending work |
| active_smoker | FALSE | Non-smoker |
| no_pt_history | FALSE | 6 weeks at Mountain View PT |
| daily_opioid_over_3_months | FALSE | Tramadol twice a week, not daily |

**Expected Overall Status:** Clear
**Expected Actions:** None
**Critical Check 1:** HbA1c 7.0 must NOT trigger the Review flag (rule is strictly > 7.0).
**Critical Check 2:** "Cleaning next week" must NOT be read as pending dental work.
**Critical Check 3:** "Tramadol twice a week" is NOT daily opioid use.

---

## 05 — Linda F. | Bariatric | REVISION CASE + ACTION REQUIRED + HOLD (3 flags)
**Purpose:** Tests multiple simultaneous Bariatric flags firing at once.

| Flag | Expected | Reasoning |
|---|---|---|
| prior_weight_loss_surgery | TRUE | Lap band in 2015, removed after slippage |
| no_recent_egd | TRUE | Last EGD was ~2 years ago |
| no_registered_dietician | TRUE | Weight Watchers alone does not count as RD |
| dental_clearance_needed | TRUE | No dentist visit in 3+ years |

**Expected Overall Status:** Revision Case (highest severity of the four triggered)
**Expected Actions:**
1. Flag as Revision Case — specialized surgical review
2. Schedule EGD after consultation
3. Provide in-network RD list
4. Dental clearance required

**Critical Check 1:** Weight Watchers must NOT count as an RD.
**Critical Check 2:** All 4 rules fire simultaneously and are all listed in output.
**Critical Check 3:** Overall status = "Revision Case" as highest priority, not "Hold".

---

## 06 — Raymond G. | Joint | DENTAL ACTION REQUIRED (Opioid boundary test)
**Purpose:** Tests opioid duration at exactly 3 months. Should NOT trigger High Complexity.
Also tests a pending crown that patient says is "not urgent."

| Flag | Expected | Reasoning |
|---|---|---|
| daily_opioid_over_3_months | FALSE | Exactly 3 months (not greater than 3 months) |
| dental_clearance_needed | TRUE | Pending crown, even if described as "not urgent" |
| active_smoker | FALSE | Quit 8 years ago |
| no_pt_history | FALSE | 12 weeks at ProMotion PT |

**Expected Overall Status:** Action Required
**Expected Actions:** Dental clearance — pending crown must be addressed
**Critical Check 1:** Opioid duration of exactly 3 months must NOT trigger High Complexity (rule is > 3 months).
**Critical Check 2:** A pending crown — even described as non-urgent by dentist — IS pending dental work and MUST trigger dental clearance.

---

## 07 — Trevor N. | Joint | INELIGIBLE + ACTION REQUIRED (Gym ≠ PT)
**Purpose:** Tests that gym workouts with a personal trainer do NOT satisfy the PT requirement.
Also tests pending crown = dental action required.

| Flag | Expected | Reasoning |
|---|---|---|
| no_pt_history | TRUE | LA Fitness + personal trainer = NOT formal PT |
| dental_clearance_needed | TRUE | Pending crown (needs a crown on upper left molar) |
| active_smoker | FALSE | Non-smoker |
| daily_opioid_over_3_months | FALSE | Meloxicam is not an opioid |

**Expected Overall Status:** Ineligible (highest severity, overrides Action Required)
**Expected Actions:**
1. Refer to 6-12 week PT trial
2. Dental clearance required

**Critical Check 1:** "LA Fitness, personal trainer" must map to no_pt_history: TRUE.
**Critical Check 2:** Meloxicam (anti-inflammatory) must NOT be confused with an opioid.
**Critical Check 3:** Overall status is Ineligible, not Action Required, because Ineligible outranks it.

---

## 08 — Camille B. | Bariatric | HOLD (Nutritionist ≠ RD)
**Purpose:** Tests that a single visit to an uncredentialed "nutritionist" does NOT satisfy the RD requirement.

| Flag | Expected | Reasoning |
|---|---|---|
| no_registered_dietician | TRUE | Gym wellness nutritionist, credentials unknown, seen once |
| prior_weight_loss_surgery | FALSE | First surgery |
| no_recent_egd | FALSE | EGD 5 weeks ago |
| dental_clearance_needed | FALSE | Cleaning in March, no pending work |

**Expected Overall Status:** Hold
**Expected Actions:** Provide in-network RD list; establish ongoing RD care before referral
**Critical Check 1:** "Nutritionist at wellness center" with unknown credentials, seen once = no_registered_dietician: TRUE.
**Critical Check 2:** EGD 5 weeks ago correctly recognized as within 3 months.

---

## 09 — Gerald O. | Joint | INELIGIBLE (All 4 joint flags + dental)
**Purpose:** Maximum complexity Joint case. All four Joint SOP rules plus dental all fire simultaneously.

| Flag | Expected | Reasoning |
|---|---|---|
| active_smoker | TRUE | Current half-pack/day smoker |
| daily_opioid_over_3_months | TRUE | Oxycodone daily for 2.5 years |
| no_pt_history | TRUE | Only 2 PT sessions — does not satisfy 6-week requirement |
| hba1c_elevated | TRUE | HbA1c 8.2 |
| dental_clearance_needed | TRUE | No dentist in 3+ years, active dental pain |

**Expected Overall Status:** Ineligible (highest severity among all triggered rules)
**Expected Actions:**
1. Refer to 6-12 week PT trial (Ineligible)
2. Flag for Anesthesia High Risk Consult (High Complexity)
3. Refer to Smoking Cessation (Deferred)
4. Flag for MD Review — glucose optimization (Review)
5. Dental clearance required (Action Required)

**Critical Check 1:** Two PT sessions does NOT satisfy the formal PT requirement.
**Critical Check 2:** All 5 rules fire and all 5 actions appear in output.
**Critical Check 3:** Status = Ineligible as most severe, not Deferred or Review.

---

## 10 — Dorothy W. | Joint | AMBIGUOUS / INCOMPLETE
**Purpose:** Tests graceful null handling when the patient cannot provide clear answers.
The system should use null — NOT false — for fields that are genuinely unknown.

| Flag | Expected | Reasoning |
|---|---|---|
| active_smoker | FALSE | Quit in 1987 — well over 3 months ago |
| no_pt_history | NULL / uncertain | Pool aerobics mentioned; formal PT unclear |
| daily_opioid_over_3_months | NULL / uncertain | Takes daily pill but name unknown; may or may not be opioid |
| dental_clearance_needed | NULL / uncertain | "Recently, maybe last year" — genuinely unclear |
| hba1c_elevated | NULL | No mention |

**Expected Overall Status:** Cannot be determined — requires follow-up with daughter Carol
**Expected Actions:** Case on hold pending clinical follow-up to clarify PT history, medication identity, and dental status.

**Critical Check 1:** "Pool aerobics with granddaughter" must NOT be treated as formal PT.
**Critical Check 2:** Unknown medication taken daily should be flagged as uncertain, NOT assumed to be an opioid.
**Critical Check 3:** Ambiguous dental ("maybe last year") should be null, not false.
**Critical Check 4:** The system should NOT hallucinate certainty where the transcript provides none.

---

## Summary Table

| # | Patient | Type | Expected Status | Rules Fired | Key Test |
|---|---|---|---|---|---|
| 01 | James R. | Joint | Clear | 0 | Happy path |
| 02 | Denise K. | Joint | Deferred | 1 | Quit < 3 months = still active |
| 03 | Marcus T. | Bariatric | Clear | 0 | Bariatric happy path |
| 04 | Patricia M. | Joint | Clear | 0 | HbA1c = 7.0 boundary |
| 05 | Linda F. | Bariatric | Revision Case | 4 | Multiple Bariatric flags |
| 06 | Raymond G. | Joint | Action Required | 1 | Opioid = 3 months boundary |
| 07 | Trevor N. | Joint | Ineligible | 2 | Gym ≠ PT |
| 08 | Camille B. | Bariatric | Hold | 1 | Nutritionist ≠ RD |
| 09 | Gerald O. | Joint | Ineligible | 5 | All flags fire |
| 10 | Dorothy W. | Joint | Unclear | Unknown | Null handling |
