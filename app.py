"""
Care Navigator — Automated Clinical Routing Navigator
Streamlit Application
"""

import html as _html
import json
import os
import unicodedata
import streamlit as st
import streamlit.components.v1 as components
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

# ── SOP lookup helpers ───────────────────────────────────────────────────────

# Map rule_id → fact_key and fact_key → rule_id
RULE_FACT_KEY = {r["id"]: r["fact_key"] for r in SOP_RULES}
FACT_TO_RULE_ID = {r["fact_key"]: r["id"] for r in SOP_RULES}

# Highlight colour per status (mirrors prototype colour semantics)
_STATUS_HL = {
    "Ineligible":    "red",
    "High Complexity": "red",
    "Deferred":      "red",
    "Review":        "amber",
    "Action Required": "amber",
    "Hold":          "amber",
    "Revision Case": "purple",
    "Clear":         "green",
}

# Derived from SOP_RULES.evidence_key — single source of truth.
# evidence_map key  →  SOP flag key (for annotator: highlight only triggered quotes)
EVIDENCE_TO_SOP_FLAG: dict = {}
for _r in SOP_RULES:
    _ek = _r.get("evidence_key", _r["fact_key"])
    if isinstance(_ek, list):
        for _k in _ek:
            EVIDENCE_TO_SOP_FLAG[_k] = _r["fact_key"]
    else:
        EVIDENCE_TO_SOP_FLAG[_ek] = _r["fact_key"]

# SOP flag key  →  evidence_map key or list of keys to try in order (for rule cards)
SOP_FLAG_TO_EVIDENCE_KEY: dict = {
    _r["fact_key"]: _r.get("evidence_key", _r["fact_key"])
    for _r in SOP_RULES
}


def _hl_color_for_rule(rule_id: str) -> str:
    """Return highlight colour token for a rule."""
    for r in SOP_RULES:
        if r["id"] == rule_id:
            return _STATUS_HL.get(r["case_status"], "blue")
    return "blue"


def _norm_text(s: str) -> str:
    # Normalise typographic chars so LLM quotes match transcript text.
    # All substitutions are 1-char:1-char to preserve index positions.
    # (Multi-char subs like em-dash->-- shift all subsequent indices.)
    if not s:
        return s
    # Straight single quotes (1:1)
    s = s.replace('\u2018', "'")
    s = s.replace('\u2019', "'")
    # Straight double quotes (1:1)
    s = s.replace('\u201c', '"')
    s = s.replace('\u201d', '"')
    # Dashes (1:1 - single hyphen for em-dash and en-dash)
    s = s.replace('\u2014', '-')
    s = s.replace('\u2013', '-')
    # Normalise unicode to NFC
    s = unicodedata.normalize('NFC', s)
    return s


def _build_annotated_html(transcript: str, evidence_map: dict, sop_flags: dict) -> str:
    """
    Return the transcript text with evidence quotes wrapped in highlight spans.
    Only quotes whose corresponding SOP flag was triggered are highlighted.
    Overlapping / duplicate quotes are deduplicated. Non-matched text is HTML-escaped.
    """
    norm_transcript = _norm_text(transcript)

    # Collect (start, end, rule_id, color, label) for each matched quote
    spans = []
    for ev_key, ev in evidence_map.items():
        if not isinstance(ev, dict):
            continue
        quote = ev.get("quote")
        if not quote:
            continue
        # Highlight ALL evidence quotes: green=cleared, status-color=flagged
        sop_flag_key = EVIDENCE_TO_SOP_FLAG.get(ev_key)
        rule_id = FACT_TO_RULE_ID.get(sop_flag_key, "") if sop_flag_key else ""
        triggered = bool(sop_flag_key and sop_flags.get(sop_flag_key))
        if triggered:
            color = _hl_color_for_rule(rule_id) if rule_id else "amber"
            label = next((f"{r['id']}: {r['finding']}" for r in SOP_RULES
                          if r["fact_key"] == sop_flag_key), "")
        else:
            color = "green"
            label = next((f"\u2713 {r['id']}: {r['finding']}" for r in SOP_RULES
                          if r["fact_key"] == sop_flag_key),
                         ev_key.replace("_", " ").title())
        norm_quote = _norm_text(quote)
        idx = norm_transcript.find(norm_quote)
        if idx == -1:
            # Try case-insensitive
            idx = norm_transcript.lower().find(norm_quote.lower())
        if idx == -1:
            continue
        end = idx + len(norm_quote)
        # data-rule: use rule_id for triggered (jumpToHL from rule card), ev_key for non-triggered
        anchor = rule_id if triggered else (rule_id or ev_key)
        spans.append((idx, end, anchor, color, label))

    if not spans:
        return _html.escape(transcript)

    # Sort by start; resolve overlaps by keeping longest span
    spans.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    merged = []
    cursor = 0
    for span in spans:
        s, e, rid, col, lbl = span
        if s < cursor:
            continue  # skip overlap
        merged.append(span)
        cursor = e

    # Build HTML
    parts = []
    cursor = 0
    for s, e, rid, col, lbl in merged:
        if cursor < s:
            parts.append(_html.escape(transcript[cursor:s]))
        inner = _html.escape(transcript[s:e])
        parts.append(
            f'<span class="highlight hl-{col}" data-rule="{_html.escape(rid)}" '
            f'data-label="{_html.escape(lbl)}" onclick="handleHLClick(this)">{inner}</span>'
        )
        cursor = e
    if cursor < len(transcript):
        parts.append(_html.escape(transcript[cursor:]))
    return "".join(parts)


def _conf_color(conf: int) -> str:
    if conf >= 85:
        return "#22C55E"
    if conf >= 65:
        return "#F59E0B"
    return "#EF4444"


def _conf_label(conf: int) -> str:
    if conf >= 85:
        return "High"
    if conf >= 65:
        return "Med"
    return "Low"


def _conf_dot_class(conf: int) -> str:
    if conf >= 85:
        return "conf-high"
    if conf >= 65:
        return "conf-med"
    return "conf-low"


def _build_rule_cards_html(logic_results: list, evidence_map: dict) -> str:
    """Build expandable rule-card HTML for all triggered rules."""
    parts = []
    for i, rule in enumerate(logic_results):
        rid = rule["rule_id"]
        color = STATUS_COLORS.get(rule["case_status"], "#6B7280")
        sop_flag_key = RULE_FACT_KEY.get(rid, "")
        # Resolve the evidence_map key (may differ from the SOP flag key)
        ev_mapping = SOP_FLAG_TO_EVIDENCE_KEY.get(sop_flag_key, sop_flag_key)
        ev: dict = {}
        if isinstance(ev_mapping, list):
            for k in ev_mapping:
                candidate = evidence_map.get(k) or {}
                if isinstance(candidate, dict) and candidate.get("quote"):
                    ev = candidate
                    break
            if not ev:
                ev = evidence_map.get(ev_mapping[0]) or {}
        else:
            ev = evidence_map.get(ev_mapping) or {}
        quote = ev.get("quote") if isinstance(ev, dict) else None
        conf = int(ev.get("confidence", 0)) if isinstance(ev, dict) else 0
        open_cls = "open" if i == 0 else ""
        chevron_rot = "rotate(90deg)" if i == 0 else "none"
        evidence_html = (
            f'<div class="rule-evidence">{_html.escape(str(quote))}</div>'
            if quote else
            '<div class="rule-evidence" style="color:var(--gray4);font-style:italic">No verbatim quote extracted</div>'
        )
        conf_bar_html = (
            f'<div class="conf-bar-wrap"><div class="conf-bar-label"><span>Extraction confidence</span>'
            f'<span style="font-weight:500">{conf}% · {_conf_label(conf)}</span></div>'
            f'<div class="conf-bar"><div class="conf-fill" style="width:{conf}%;background:{_conf_color(conf)}"></div></div></div>'
        ) if quote else ''
        parts.append(f"""
<div class="rule-card" data-ruleid="{_html.escape(rid)}" onclick="toggleRule('{rid}')">
  <div class="rule-card-header">
    <div class="rule-left-bar" style="background:{color}"></div>
    <div style="flex:1;min-width:0">
      <div class="rule-id">{_html.escape(rid)} · {_html.escape(rule['category'])}</div>
      <div class="rule-status" style="color:{color}">{_html.escape(rule['case_status'])} — {_html.escape(rule['finding'])}</div>
      <div class="rule-action">{_html.escape(rule['action'])}</div>
    </div>
    <div id="chevron-{rid}" style="font-size:18px;color:var(--gray4);margin-left:8px;transition:transform 0.2s;transform:{chevron_rot}">›</div>
  </div>
  <div class="rule-body {open_cls}" id="body-{rid}">
    <div style="padding-top:10px">
      <div class="evidence-label">Evidence from transcript</div>
      {evidence_html}
      {conf_bar_html}
      {'<button class="jump-btn" onclick="jumpToHL(event,\'' + _html.escape(rid) + '\')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 19V5M5 12l7-7 7 7"/></svg> Jump to evidence</button>' if quote else ''}
    </div>
  </div>
</div>""")
    return "\n".join(parts)


def _get_verify_facts(case_type: str, details: dict, sop_flags: dict, evidence_map: dict) -> list:
    """Return ordered list of fact-verification rows appropriate for the case type."""
    common = [
        {
            "key": "dental_clearance_needed",
            "label": "Dental clearance needed",
            "extracted": sop_flags.get("dental_clearance_needed"),
            "conf": int((evidence_map.get("dental_last_visit_within_6_months") or {}).get("confidence", 50)),
            "rule": "GEN-001",
        },
    ]
    joint = [
        {
            "key": "active_smoker",
            "label": "Active smoker",
            "extracted": details.get("active_smoker"),
            "conf": int((evidence_map.get("active_smoker") or {}).get("confidence", 50)),
            "rule": "JNT-001",
        },
        {
            "key": "has_pt_history",
            "label": "Formal PT history (6+ weeks)",
            "extracted": details.get("has_pt_history"),
            "conf": int((evidence_map.get("has_pt_history") or {}).get("confidence", 50)),
            "rule": "JNT-002",
        },
        {
            "key": "hba1c_elevated",
            "label": f"HbA1c > 7.0 ({details.get('hba1c_value') or 'not stated'})",
            "extracted": sop_flags.get("hba1c_elevated"),
            "conf": int((evidence_map.get("hba1c_value") or {}).get("confidence", 50)),
            "rule": "JNT-003",
        },
        {
            "key": "daily_opioid_over_3_months",
            "label": "Daily opioid use > 3 months",
            "extracted": sop_flags.get("daily_opioid_over_3_months"),
            "conf": int((evidence_map.get("daily_opioid_use") or {}).get("confidence", 50)),
            "rule": "JNT-004",
        },
    ]
    bariatric = [
        {
            "key": "prior_weight_loss_surgery",
            "label": "Prior weight-loss surgery",
            "extracted": details.get("prior_weight_loss_surgery"),
            "conf": int((evidence_map.get("prior_weight_loss_surgery") or {}).get("confidence", 50)),
            "rule": "BAR-001",
        },
        {
            "key": "no_recent_egd",
            "label": "No recent EGD (< 3 months)",
            "extracted": sop_flags.get("no_recent_egd"),
            "conf": int((evidence_map.get("recent_egd_within_3_months") or {}).get("confidence", 50)),
            "rule": "BAR-002",
        },
        {
            "key": "no_registered_dietician",
            "label": "No Registered Dietician identified",
            "extracted": sop_flags.get("no_registered_dietician"),
            "conf": int((evidence_map.get("has_registered_dietician") or {}).get("confidence", 50)),
            "rule": "BAR-003",
        },
    ]
    if case_type == "Joint":
        return common + joint
    elif case_type == "Bariatric":
        return common + bariatric
    else:
        return common + joint + bariatric


def _build_verify_rows_html(verify_facts: list, evidence_map: dict) -> str:
    rows = []
    for f in verify_facts:
        val = f["extracted"]
        val_class = "ve-true" if val is True else ("ve-false" if val is False else "ve-null")
        val_label = "Yes" if val is True else ("No" if val is False else "null")
        conf = f["conf"]
        conf_level = "high" if conf >= 85 else ("med" if conf >= 65 else "low")
        conf_text = "High" if conf >= 85 else ("Med" if conf >= 65 else "Low")
        # Determine if a transcript highlight exists to jump to
        ev_key_or_list = SOP_FLAG_TO_EVIDENCE_KEY.get(f["key"], f["key"])
        if isinstance(ev_key_or_list, list):
            has_quote = any((evidence_map.get(k) or {}).get("quote") for k in ev_key_or_list)
        else:
            has_quote = bool((evidence_map.get(ev_key_or_list) or {}).get("quote"))
        jump_html = (
            f'<button class="vt-jump" onclick="jumpToHL(event,\'{_html.escape(f["rule"])}\')"'
            f' title="Jump to evidence in transcript">'
            f'<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
            f'<path d="M12 19V5M5 12l7-7 7 7"/></svg></button>'
        ) if has_quote else '<div style="width:22px;flex-shrink:0"></div>'
        rows.append(f"""<div class="verify-row" id="vrow-{_html.escape(f['key'])}">
  <div class="verify-label">{_html.escape(f['label'])}
    <div style="font-size:10px;color:var(--gray4);font-family:var(--mono);margin-top:1px">extracted: <span class="{val_class}">{val_label}</span></div>
  </div>
  <div class="conf-chip conf-{conf_level}" title="AI extracted this with {conf}% confidence">AI · {conf_text}</div>
  {jump_html}
  <div class="verify-toggle">
    <button class="vt-btn" onclick="setFact(event,'{_html.escape(f['key'])}','Yes')" title="Confirm Yes" id="ybtn-{_html.escape(f['key'])}">Y</button>
    <button class="vt-btn" onclick="setFact(event,'{_html.escape(f['key'])}','No')" title="Confirm No" id="nbtn-{_html.escape(f['key'])}">N</button>
    <button class="vt-btn" onclick="setFact(event,'{_html.escape(f['key'])}','?')" title="Unknown / not stated" id="ubtn-{_html.escape(f['key'])}">?</button>
  </div>
</div>""")
    return "\n".join(rows)


def build_workspace_html(result: dict, transcript: str) -> str:
    """Build the complete self-contained workspace HTML (runs inside st.components iframe)."""
    pf = result["Patient_Facts"]
    details = pf.get("extracted_details", {})
    evidence_map = result.get("Evidence_Map", {})
    logic_results = result["Logic_Results"]
    sop_flags = result["SOP_Flags"]
    overall = result["Overall_Case_Status"]
    overall_color = STATUS_COLORS.get(overall, "#6B7280")
    patient_name = pf.get("patient_name") or "Unknown Patient"
    case_type = pf.get("case_type", "Unknown")
    clinical_summary = pf.get("clinical_summary", "")
    # Count triggered rules (rules shown as cards), not raw sop_flags.
    # Raw sop_flags can include case-type-filtered entries (e.g. Bariatric BAR-002/003
    # for a Joint case) that inflate the count without a corresponding rule card.
    flags_true = len(logic_results)
    low_conf_count = sum(
        1 for ev in evidence_map.values()
        if isinstance(ev, dict) and int(ev.get("confidence", 100)) < 70
    )

    annotated_html = _build_annotated_html(transcript, evidence_map, sop_flags)
    rule_cards_html = _build_rule_cards_html(logic_results, evidence_map)
    verify_facts = _get_verify_facts(case_type, details, sop_flags, evidence_map)
    verify_rows_html = _build_verify_rows_html(verify_facts, evidence_map)
    total_facts = len(verify_facts)

    # Status pills for the header
    status_pills_html = ""
    seen = set()
    for rule in logic_results:
        s = rule["case_status"]
        if s not in seen:
            seen.add(s)
            color = STATUS_COLORS.get(s, "#6B7280")
            status_pills_html += f'<span class="status-pill" style="background:{color};color:white">{_html.escape(s)}</span>'
    if not status_pills_html:
        status_pills_html = f'<span class="status-pill" style="background:{overall_color};color:white">{_html.escape(overall)}</span>'

    # Fact keys for JS
    fact_keys_json = json.dumps([f["key"] for f in verify_facts])
    final_data_json = json.dumps(result, indent=2)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;500;600&display=swap');
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --navy:#0A1628;--blue:#1A4F72;--blue2:#2E86AB;
  --green:#166534;--greenbg:#DCFCE7;--greentxt:#14532D;
  --amber:#92400E;--amberbg:#FEF3C7;--ambertxt:#78350F;
  --red:#991B1B;--redbg:#FEE2E2;--redtxt:#7F1D1D;
  --purple:#5B21B6;--purpbg:#EDE9FE;--purptxt:#4C1D95;
  --gray1:#F8F7F4;--gray2:#F0EDE8;--gray3:#E5E2DC;
  --gray4:#9CA3AF;--gray5:#6B7280;--gray6:#374151;--gray7:#1F2937;
  --font:'Sora',sans-serif;--mono:'IBM Plex Mono',monospace;
}}
html,body{{font-family:var(--font);background:var(--gray1);color:var(--gray7);font-size:14px;line-height:1.6}}
.workspace{{display:grid;grid-template-columns:1fr 420px}}
/* LEFT */
.left-panel{{display:flex;flex-direction:column;background:white;border-right:1px solid var(--gray3)}}
.panel-header{{padding:12px 16px;border-bottom:1px solid var(--gray3);display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
.panel-label{{font-size:10px;font-weight:600;color:var(--gray4);letter-spacing:.1em;text-transform:uppercase}}
.legend{{display:flex;gap:10px;align-items:center}}
.legend-item{{display:flex;align-items:center;gap:4px;font-size:11px;color:var(--gray5)}}
.dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0}}
.tab-bar{{display:flex;gap:2px;padding:8px 12px 0;background:white;border-bottom:1px solid var(--gray3);flex-shrink:0}}
.tab{{padding:5px 10px;border-radius:6px 6px 0 0;font-size:11px;font-weight:500;color:var(--gray4);cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px}}
.tab.active{{color:var(--navy);border-bottom-color:var(--navy)}}
.transcript-scroll{{padding:16px}}
.transcript-text{{font-family:var(--mono);font-size:12px;line-height:1.9;color:var(--gray6);white-space:pre-wrap}}
.highlight{{border-radius:3px;cursor:pointer;transition:all .15s;position:relative}}
.hl-red{{background:#FEE2E2;border-bottom:2px solid #EF4444}}
.hl-amber{{background:#FEF3C7;border-bottom:2px solid #F59E0B}}
.hl-green{{background:#DCFCE7;border-bottom:2px solid #22C55E}}
.hl-blue{{background:#DBEAFE;border-bottom:2px solid #3B82F6}}
.hl-purple{{background:#EDE9FE;border-bottom:2px solid #7C3AED}}
.highlight:hover{{filter:brightness(.93)}}
.highlight.active-hl{{outline:2px solid var(--navy);outline-offset:2px}}
.hl-tooltip{{display:none;position:fixed;background:var(--navy);color:white;padding:6px 10px;border-radius:6px;font-size:11px;font-family:var(--font);z-index:100;max-width:220px;line-height:1.5;pointer-events:none}}
.hl-tooltip.show{{display:block}}
/* RIGHT */
.right-panel{{display:flex;flex-direction:column;background:var(--gray1)}}
.right-panel .panel-header{{background:white;padding:12px 16px;border-bottom:1px solid var(--gray3);flex-direction:column;gap:8px;flex-shrink:0}}
.right-scroll{{padding:12px;display:flex;flex-direction:column;gap:10px}}
.status-pill{{padding:3px 10px;border-radius:100px;font-size:11px;font-weight:600}}
.progress-bar{{height:2px;background:var(--gray3);position:relative;flex-shrink:0}}
.progress-fill{{height:100%;background:var(--blue2);transition:width .3s}}
/* Rule cards */
.rule-card{{background:white;border-radius:8px;border:1px solid var(--gray3);overflow:hidden}}
.rule-card-header{{padding:10px 12px;display:flex;align-items:flex-start;gap:10px;cursor:pointer}}
.rule-id{{font-family:var(--mono);font-size:10px;color:var(--gray4);margin-bottom:2px}}
.rule-status{{font-size:12px;font-weight:600;margin-bottom:2px}}
.rule-action{{font-size:12px;color:var(--gray6);line-height:1.5}}
.rule-left-bar{{width:3px;border-radius:2px;flex-shrink:0;margin-top:2px;align-self:stretch}}
.rule-body{{display:none;padding:0 12px 12px;border-top:1px solid var(--gray2)}}
.rule-body.open{{display:block}}
.jump-btn-sm{{display:inline-flex;align-items:center;gap:3px;background:transparent;color:var(--gray4);border:1px solid var(--gray3);padding:4px 8px;border-radius:4px;font-size:10px;font-family:var(--font);cursor:pointer;transition:all .15s;flex-shrink:0;white-space:nowrap}}
.jump-btn-sm:hover{{background:var(--navy);color:white;border-color:var(--navy)}}
.vt-jump{{width:22px;height:22px;border:none;background:var(--navy);border-radius:4px;cursor:pointer;display:flex;align-items:center;justify-content:center;color:white;flex-shrink:0;padding:0}}
.vt-jump:hover{{background:var(--blue)}}
.rule-evidence{{background:var(--gray1);border:1px solid var(--gray3);border-radius:6px;padding:8px 10px;margin-top:8px;font-size:11px;font-family:var(--mono);color:var(--gray6);line-height:1.6}}
.evidence-label{{font-size:10px;font-weight:600;color:var(--gray4);letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;font-family:var(--font)}}
.conf-bar-wrap{{margin-top:8px}}
.conf-bar-label{{font-size:10px;color:var(--gray5);margin-bottom:4px;display:flex;justify-content:space-between}}
.conf-bar{{height:4px;background:var(--gray3);border-radius:2px;overflow:hidden}}
.conf-fill{{height:100%;border-radius:2px;transition:width .3s}}
.jump-btn{{display:inline-flex;align-items:center;gap:4px;margin-top:8px;background:var(--navy);color:white;border:none;padding:5px 10px;border-radius:5px;font-size:11px;font-family:var(--font);cursor:pointer}}
.jump-btn:hover{{background:var(--blue)}}
/* Verify */
.verify-section{{background:white;border-radius:8px;border:1px solid var(--gray3);overflow:hidden}}
.verify-header{{padding:10px 12px;border-bottom:1px solid var(--gray3);display:flex;justify-content:space-between;align-items:center}}
.verify-title{{font-size:12px;font-weight:600;color:var(--gray7)}}
.verify-subtitle{{font-size:10px;color:var(--gray4)}}
.verify-row{{display:flex;align-items:center;gap:8px;padding:7px 12px;border-bottom:1px solid var(--gray2)}}
.verify-row:last-child{{border-bottom:none}}
.verify-label{{flex:1;font-size:12px;color:var(--gray6)}}
.verify-extracted{{font-size:11px;font-family:var(--mono);padding:2px 7px;border-radius:4px;flex-shrink:0}}
.ve-true{{background:var(--redbg);color:var(--redtxt)}}
.ve-false{{background:var(--greenbg);color:var(--greentxt)}}
.ve-null{{background:var(--gray2);color:var(--gray5)}}
.conf-chip{{font-size:9px;font-weight:500;padding:2px 7px;border-radius:10px;flex-shrink:0;white-space:nowrap;letter-spacing:.02em}}
.conf-high{{background:#DCFCE7;color:#166534}}.conf-med{{background:#FEF3C7;color:#92400E}}.conf-low{{background:#FEE2E2;color:#991B1B}}
.verify-toggle{{display:flex;gap:3px;flex-shrink:0}}
.vt-btn{{width:26px;height:22px;border:1px solid var(--gray3);background:white;border-radius:4px;font-size:10px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .15s;color:var(--gray5);font-weight:500}}
.vt-btn:hover{{border-color:var(--blue2);color:var(--blue2)}}
.vt-btn.selected-yes{{background:#DCFCE7;border:2px solid #16A34A;color:#166534;font-weight:700}}
.vt-btn.selected-no{{background:#FEE2E2;border:2px solid #DC2626;color:#991B1B;font-weight:700}}
.vt-btn.selected-unk{{background:#F3F4F6;border:2px solid #6B7280;color:#374151;font-weight:700}}
.override-badge{{font-size:10px;background:#FEF3C7;color:#92400E;border:1px solid #F59E0B;padding:1px 6px;border-radius:4px;margin-left:6px}}
.confirm-area{{padding:12px;background:white;border-radius:8px;border:1px solid var(--gray3)}}
.confirm-btn{{width:100%;padding:10px;background:var(--navy);color:white;border:none;border-radius:8px;font-size:13px;font-weight:600;font-family:var(--font);cursor:pointer;transition:background .15s}}
.confirm-btn:hover{{background:var(--blue)}}
.confirm-btn:disabled{{background:var(--gray3);color:var(--gray4);cursor:not-allowed}}
.confirm-note{{font-size:10px;color:var(--gray4);text-align:center;margin-top:6px}}
.summary-box{{background:white;border-radius:8px;border:1px solid var(--gray3);padding:12px}}
.summary-label{{font-size:10px;font-weight:600;color:var(--gray4);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px}}
.summary-text{{font-size:12px;color:var(--gray6);line-height:1.7}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}
.metric{{background:white;border:1px solid var(--gray3);border-radius:6px;padding:8px 10px;text-align:center}}
.metric-n{{font-size:20px;font-weight:600;color:var(--gray7);line-height:1}}
.metric-l{{font-size:10px;color:var(--gray4);margin-top:3px;text-transform:uppercase;letter-spacing:.07em}}
.alert{{padding:8px 12px;border-radius:6px;font-size:12px;display:flex;gap:8px;align-items:flex-start}}
.alert-amber{{background:var(--amberbg);color:var(--ambertxt);border:1px solid #FCD34D}}
.scrollbar-thin::-webkit-scrollbar{{width:4px}}
.scrollbar-thin::-webkit-scrollbar-track{{background:transparent}}
.scrollbar-thin::-webkit-scrollbar-thumb{{background:var(--gray3);border-radius:2px}}
</style>
</head>
<body>
<div class="workspace">

  <!-- LEFT: Transcript -->
  <div class="left-panel">
    <div class="panel-header">
      <div>
        <div class="panel-label">Patient Transcript — {_html.escape(patient_name)} · {_html.escape(case_type)}</div>
      </div>
      <div class="legend">
        <div class="legend-item"><div class="dot" style="background:#EF4444"></div>Blocking</div>
        <div class="legend-item"><div class="dot" style="background:#F59E0B"></div>Review</div>
        <div class="legend-item"><div class="dot" style="background:#3B82F6"></div>Supporting</div>
        <div class="legend-item"><div class="dot" style="background:#22C55E"></div>Cleared</div>
        <div class="legend-item"><div class="dot" style="background:#7C3AED"></div>Revision</div>
      </div>
    </div>
    <div class="tab-bar">
      <div class="tab active" onclick="switchTab('annotated',this)">Annotated</div>
      <div class="tab" onclick="switchTab('raw',this)">Raw</div>
      <div class="tab" onclick="switchTab('json',this)">JSON</div>
    </div>
    <div class="transcript-scroll scrollbar-thin">
      <div class="transcript-text" id="transcript-annotated">{annotated_html}</div>
      <div class="transcript-text" id="transcript-raw" style="display:none">{_html.escape(transcript)}</div>
      <div class="transcript-text" id="transcript-json" style="display:none;font-size:11px;line-height:1.6">{_html.escape(final_data_json)}</div>
    </div>
  </div>

  <!-- RIGHT: Review Panel -->
  <div class="right-panel">
    <div class="panel-header" style="display:flex;flex-direction:column;gap:8px">
      <div style="display:flex;justify-content:space-between;align-items:center;width:100%">
        <div>
          <div class="panel-label">Routing Review</div>
          <div style="font-size:15px;font-weight:600;color:var(--gray7);margin-top:2px">{_html.escape(patient_name)}</div>
        </div>
        <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end">
          {status_pills_html}
        </div>
      </div>
      <div class="progress-bar" style="width:100%;border-radius:2px">
        <div class="progress-fill" id="progress-fill" style="width:0%"></div>
      </div>
      <div style="font-size:10px;color:var(--gray4);display:flex;justify-content:space-between">
        <span id="progress-label">0 of {total_facts} facts confirmed</span>
        <span id="progress-pct">0%</span>
      </div>
    </div>

    <div class="right-scroll scrollbar-thin" id="right-scroll">

      <!-- Summary -->
      <div class="summary-box">
        <div class="summary-label">Clinical Summary</div>
        <div class="summary-text">{_html.escape(clinical_summary)}</div>
      </div>

      <!-- Metrics -->
      <div class="metrics">
        <div class="metric" title="SOP rules triggered — routing actions are required for these">
          <div class="metric-n" style="color:#DC2626">{flags_true}</div>
          <div class="metric-l">Flags</div>
        </div>
        <div class="metric" title="Evidence extractions where AI confidence is below 70% — verify these carefully">
          <div class="metric-n" style="color:#F59E0B">{low_conf_count}</div>
          <div class="metric-l">Low conf.</div>
        </div>
        <div class="metric" title="Facts you have confirmed via Y / N / ? in the Fact Verification section below">
          <div class="metric-n" id="confirmed-count" style="color:#16A34A">0</div>
          <div class="metric-l">Confirmed</div>
        </div>
      </div>

      <!-- Rule Cards -->
      {rule_cards_html if rule_cards_html else '<div class="summary-box"><div class="summary-text" style="color:var(--green)">✓ No SOP rules triggered — case may proceed.</div></div>'}

      <!-- Verification -->
      <div class="verify-section">
        <div class="verify-header">
          <div>
            <div class="verify-title">Fact Verification</div>
            <div class="verify-subtitle">Confirm or correct each extracted fact before finalising</div>
          </div>
        </div>
        <div id="verify-rows">
          {verify_rows_html}
        </div>
      </div>

      <div class="confirm-area">
        <button class="confirm-btn" id="confirm-btn" disabled>Confirm &amp; Finalise Record</button>
        <div class="confirm-note" id="confirm-note">Confirm all {total_facts} facts to enable finalisation</div>
      </div>

    </div>
  </div>
</div>

<div class="hl-tooltip" id="tooltip"></div>

<script>
const TOTAL_FACTS = {total_facts};
const FACT_KEYS = {fact_keys_json};
const FINAL_DATA = {final_data_json};

let factState = {{}};
FACT_KEYS.forEach(k => factState[k] = null);

function switchTab(mode, el) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('transcript-annotated').style.display = mode === 'annotated' ? '' : 'none';
  document.getElementById('transcript-raw').style.display = mode === 'raw' ? '' : 'none';
  document.getElementById('transcript-json').style.display = mode === 'json' ? '' : 'none';
  setTimeout(autoHeight, 50);
}}

function handleHLClick(el) {{
  document.querySelectorAll('.highlight.active-hl').forEach(e => e.classList.remove('active-hl'));
  el.classList.add('active-hl');
  const ruleId = el.dataset.rule;
  const label = el.dataset.label || '';
  const ruleCard = document.querySelector('[data-ruleid="' + ruleId + '"]');
  if (ruleCard) {{
    ruleCard.scrollIntoView({{behavior:'smooth',block:'nearest'}});
    ruleCard.style.outline = '2px solid #2E86AB';
    setTimeout(() => ruleCard.style.outline = '', 1200);
  }}
  const tt = document.getElementById('tooltip');
  if (label) {{
    tt.textContent = label;
    tt.classList.add('show');
    setTimeout(() => tt.classList.remove('show'), 2200);
  }}
}}

document.addEventListener('mousemove', function(e) {{
  const tt = document.getElementById('tooltip');
  if (tt.classList.contains('show')) {{
    tt.style.left = (e.clientX + 12) + 'px';
    tt.style.top = (e.clientY - 28) + 'px';
  }}
}});

function autoHeight() {{
  window.parent.postMessage({{isStreamlitMessage: true, type: 'streamlit:setFrameHeight', height: document.documentElement.scrollHeight + 16}}, '*');
}}

function toggleRule(id) {{
  const body = document.getElementById('body-' + id);
  const ch = document.getElementById('chevron-' + id);
  if (!body) return;
  const isOpen = body.classList.contains('open');
  body.classList.toggle('open');
  ch.style.transform = isOpen ? '' : 'rotate(90deg)';
  autoHeight();
  setTimeout(autoHeight, 250);
}}

function jumpToHL(e, ruleId) {{
  e.stopPropagation();
  const matches = document.querySelectorAll('[data-rule="' + ruleId + '"]');
  if (matches.length) {{
    document.getElementById('transcript-annotated').parentElement.scrollTop = 0;
    // switch to annotated tab
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(t => t.classList.remove('active'));
    tabs[0].classList.add('active');
    document.getElementById('transcript-annotated').style.display = '';
    document.getElementById('transcript-raw').style.display = 'none';
    setTimeout(() => {{
      matches[0].scrollIntoView({{behavior:'smooth',block:'center'}});
      document.querySelectorAll('.highlight.active-hl').forEach(x => x.classList.remove('active-hl'));
      matches[0].classList.add('active-hl');
      setTimeout(() => matches[0].classList.remove('active-hl'), 2000);
    }}, 50);
  }}
}}

function setFact(e, key, val) {{
  e.stopPropagation();
  factState[key] = val;
  rerenderRow(key);
  updateProgress();
}}

function rerenderRow(key) {{
  const row = document.getElementById('vrow-' + key);
  if (!row) return;
  ['Yes','No','?'].forEach((v, i) => {{
    const ids = ['ybtn-','nbtn-','ubtn-'];
    const cls = ['selected-yes','selected-no','selected-unk'];
    const btn = document.getElementById(ids[i] + key);
    if (!btn) return;
    btn.className = 'vt-btn' + (factState[key] === v ? ' ' + cls[i] : '');
  }});
  // override badge
  const labelEl = row.querySelector('.verify-label');
  const extracted = labelEl.querySelector('.ve-true, .ve-false, .ve-null');
  const origLabel = extracted ? extracted.textContent : 'null';
  const override = labelEl.querySelector('.override-badge');
  if (factState[key] !== null && factState[key] !== origLabel) {{
    if (!override) {{
      const b = document.createElement('span');
      b.className = 'override-badge';
      b.textContent = 'overridden';
      labelEl.appendChild(b);
    }}
  }} else {{
    if (override) override.remove();
  }}
}}

function updateProgress() {{
  const done = FACT_KEYS.filter(k => factState[k] !== null).length;
  const pct = Math.round(done / TOTAL_FACTS * 100);
  document.getElementById('progress-fill').style.width = pct + '%';
  document.getElementById('progress-label').textContent = done + ' of ' + TOTAL_FACTS + ' facts confirmed';
  document.getElementById('progress-pct').textContent = pct + '%';
  document.getElementById('confirmed-count').textContent = done;
  const btn = document.getElementById('confirm-btn');
  const note = document.getElementById('confirm-note');
  if (done === TOTAL_FACTS) {{
    btn.disabled = false;
    btn.textContent = '✓ Confirm & Finalise Record';
    note.textContent = 'All facts confirmed — ready to finalise';
  }} else {{
    btn.disabled = true;
    btn.textContent = 'Confirm & Finalise Record';
    note.textContent = 'Confirm all ' + TOTAL_FACTS + ' facts to enable finalisation';
  }}
}}

document.getElementById('confirm-btn').addEventListener('click', function() {{
  this.textContent = '✓ Record Finalised';
  this.style.background = '#166534';
  this.disabled = true;
  document.getElementById('confirm-note').textContent = 'Case routed successfully · JSON exported';
  const overrides = FACT_KEYS.filter(k => {{
    const row = document.getElementById('vrow-' + k);
    if (!row) return false;
    const extracted = row.querySelector('.ve-true, .ve-false, .ve-null');
    const origLabel = extracted ? extracted.textContent : 'null';
    return factState[k] !== null && factState[k] !== origLabel;
  }});
  const finalOutput = Object.assign({{}}, FINAL_DATA, {{
    Care_Team_Verification: Object.fromEntries(FACT_KEYS.map(k => [k, factState[k]])),
    Record_Status: 'Verified'
  }});
  const blob = new Blob([JSON.stringify(finalOutput, null, 2)], {{type:'application/json'}});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'care_routing_' + Date.now() + '.json';
  a.click();
  URL.revokeObjectURL(url);
  if (overrides.length) {{
    const el = document.getElementById('right-scroll');
    const alert = document.createElement('div');
    alert.className = 'alert alert-amber';
    alert.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg><div><strong>' + overrides.length + ' override(s) logged</strong> — corrections will be reviewed to improve extraction accuracy.</div>';
    el.prepend(alert);
  }}
}});

// Open first rule card by default
if (FINAL_DATA.Logic_Results && FINAL_DATA.Logic_Results.length > 0) {{
  const firstId = FINAL_DATA.Logic_Results[0].rule_id;
  const firstBody = document.getElementById('body-' + firstId);
  const firstChevron = document.getElementById('chevron-' + firstId);
  if (firstBody) {{ firstBody.classList.add('open'); }}
  if (firstChevron) {{ firstChevron.style.transform = 'rotate(90deg)'; }}
}}
window.addEventListener('load', function() {{ setTimeout(autoHeight, 150); }});
</script>
</body>
</html>"""


# ── Custom CSS ────────────────────────────────────────────────────────────────

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Sora:wght@300;400;500;600&display=swap');

  /* ── Global font (no * + no !important so icon fonts still win) ── */
  html, body, [class*="css"] {
    font-family: 'Sora', sans-serif;
  }
  /* Apply Sora explicitly to all readable text elements */
  p, div, span, h1, h2, h3, h4, h5, h6,
  input:not([type="file"]), textarea, select,
  label, a, button, [role="option"], [role="listbox"] {
    font-family: 'Sora', sans-serif;
  }

  /* ── Page background ─────────────────────────────── */
  .main, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background-color: #F8F7F4 !important;
  }

  /* ── Remove Streamlit default chrome ─────────────── */
  [data-testid="stHeader"] { display: none !important; }
  [data-testid="stToolbar"] { display: none !important; }
  #MainMenu { display: none !important; }
  footer { display: none !important; }
  [data-testid="stDecoration"] { display: none !important; }

  /* ── Block container ─────────────────────────────── */
  .block-container {
    padding-top: 0 !important;
    padding-bottom: 0.5rem !important;
    padding-left: 20px !important;
    padding-right: 20px !important;
    max-width: 100% !important;
    background: white !important;
  }

  /* ── Input section background strip ─────────────── */
  /* White background for the input strip, divider provides visual separation */
  .stDivider { padding: 0 !important; }
  hr { margin: 10px 0 !important; }

  /* ── Topbar ──────────────────────────────────────── */
  .nav-header {
    background: #0A1628;
    color: white;
    padding: 10px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0;
  }
  .nav-header .logo {
    font-size: 11px;
    font-weight: 600;
    color: #7BA3C8;
    letter-spacing: .12em;
    text-transform: uppercase;
  }
  .nav-header .title {
    font-size: 15px;
    font-weight: 600;
    color: white;
  }
  .nav-right { display: flex; align-items: center; gap: 8px; }
  .nav-pill {
    background: rgba(255,255,255,.08);
    color: #CBD5E1;
    border: none;
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 12px;
    cursor: default;
  }
  .nav-pill.active { background: rgba(255,255,255,.18); color: white; }
  .nav-badge {
    background: #1A3A5C;
    color: #7BC4E8;
    border: 1px solid #2A5A8C;
    padding: 3px 10px;
    border-radius: 100px;
    font-size: 10px;
    font-family: 'IBM Plex Mono', monospace !important;
  }

  /* ── Input card ──────────────────────────────────── */
  .input-card {
    background: white;
    border-bottom: 1px solid #E5E2DC;
    padding: 10px 20px 14px;
  }
  .input-label {
    font-size: 10px;
    font-weight: 600;
    color: #9CA3AF;
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-bottom: 8px;
  }

  /* ── Selectbox ───────────────────────────────────── */
  [data-testid="stSelectbox"] > div > div {
    border: 1px solid #E5E2DC !important;
    border-radius: 8px !important;
    background: white !important;
    font-size: 13px !important;
    color: #374151 !important;
    box-shadow: none !important;
  }
  [data-testid="stSelectbox"] > div > div:focus-within {
    border-color: #1A4F72 !important;
    box-shadow: 0 0 0 2px rgba(26,79,114,.12) !important;
  }
  [data-testid="stSelectbox"] svg { color: #9CA3AF !important; }

  /* ── File uploader ───────────────────────────────── */
  [data-testid="stFileUploader"] section {
    border: 1.5px dashed #D5D0C8 !important;
    border-radius: 8px !important;
    background: #FAFAF8 !important;
    padding: 6px 12px !important;
  }
  /* Re-hide native file input */
  [data-testid="stFileUploader"] input[type="file"] {
    opacity: 0 !important;
    position: absolute !important;
    pointer-events: none !important;
  }
  /* Upload button — sized to match selectbox height, proper hover contrast */
  [data-testid="stFileUploader"] section button[type="submit"] {
    background: white !important;
    color: #374151 !important;
    border: 1px solid #D5D0C8 !important;
    border-radius: 6px !important;
    padding: 4px 14px !important;
    font-size: 12px !important;
    font-family: 'Sora', sans-serif !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    min-height: 0 !important;
    height: auto !important;
    line-height: 1.4 !important;
    transition: background 0.2s, color 0.2s, border-color 0.2s !important;
    box-shadow: none !important;
  }
  [data-testid="stFileUploader"] section button[type="submit"]:hover {
    background: #0A1628 !important;
    color: white !important;
    border-color: #0A1628 !important;
  }
  /* Icon inside upload button inherits color */
  [data-testid="stFileUploader"] section button[type="submit"] [data-testid="stIconMaterial"] {
    font-size: 14px !important;
    vertical-align: middle !important;
  }

  /* ── Text area ───────────────────────────────────── */
  textarea {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    color: #374151 !important;
    border: 1px solid #E5E2DC !important;
    border-radius: 8px !important;
    background: #FAFAF9 !important;
    line-height: 1.7 !important;
  }
  textarea:focus {
    border-color: #1A4F72 !important;
    box-shadow: 0 0 0 2px rgba(26,79,114,.12) !important;
  }

  /* ── Analyze button ──────────────────────────────── */
  [data-testid="stButton"] > button {
    background: #0A1628 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    padding: 8px 20px !important;
    font-family: 'Sora', sans-serif !important;
    letter-spacing: 0.02em !important;
    transition: background .2s !important;
    box-shadow: none !important;
  }
  [data-testid="stButton"] > button:hover {
    background: #1A4F72 !important;
    box-shadow: none !important;
  }
  [data-testid="stButton"] > button:active {
    background: #1A4F72 !important;
  }

  /* ── Divider ─────────────────────────────────────── */
  hr, [data-testid="stDivider"] hr {
    border-color: #E5E2DC !important;
    margin: 6px 0 10px !important;
  }

  /* ── Spinner ─────────────────────────────────────── */
  [data-testid="stSpinner"] > div > div {
    border-top-color: #1A4F72 !important;
  }
  [data-testid="stSpinner"] p {
    color: #6B7280 !important;
    font-size: 13px !important;
  }

  /* ── Alerts ──────────────────────────────────────── */
  [data-testid="stAlert"] {
    border-radius: 8px !important;
    font-size: 13px !important;
  }

  /* ── Expander (raw JSON) ─────────────────────────── */
  [data-testid="stExpander"] {
    border: 1px solid #E5E2DC !important;
    border-radius: 8px !important;
    background: white !important;
  }
  [data-testid="stExpander"] summary {
    font-size: 13px !important;
    color: #374151 !important;
    font-weight: 500 !important;
  }
  [data-testid="stExpander"] summary:hover {
    color: #0A1628 !important;
  }

  /* ── Empty state ─────────────────────────────────── */
  .upload-hint {
    text-align: center;
    padding: 3rem 2rem;
    color: #9CA3AF;
    font-size: 14px;
  }

  /* ── Columns gap ─────────────────────────────────── */
  [data-testid="stHorizontalBlock"] {
    gap: 10px !important;
    align-items: flex-start !important;
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

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="nav-header">
  <div class="topbar-brand">
    <div>
      <div class="logo">Care Navigator</div>
      <div class="title">Clinical Routing Navigator</div>
    </div>
  </div>
  <div class="nav-right">
    <button class="nav-pill active">Review</button>
    <button class="nav-pill">History</button>
    <button class="nav-pill">Admin</button>
    <div class="nav-badge">Clinical Processor v1.0</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Input Section ─────────────────────────────────────────────────────────────

st.markdown('<div class="input-label" style="padding:10px 0 2px">LOAD TRANSCRIPT</div>', unsafe_allow_html=True)

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

# ── Results ───────────────────────────────────────────────────────────────────

if "result" in st.session_state:
    result = st.session_state["result"]
    workspace_html = build_workspace_html(result, st.session_state["transcript"])
    components.html(workspace_html, height=1200, scrolling=False)
else:
    # Empty state
    st.markdown("""
    <div class="upload-hint">
      <div style="font-size:2.5rem;margin-bottom:0.75rem;">🏥</div>
      <div style="font-weight:600;color:#374151;margin-bottom:0.4rem;">No transcript loaded</div>
      <div>Select a sample above or paste/upload a patient transcript to begin routing analysis.</div>
    </div>
    """, unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="text-align:center;font-size:0.72rem;color:#9CA3AF;font-family:\'IBM Plex Mono\',monospace;">Care Navigator · Clinical Routing Navigator · Automated Logic Engine · For internal Care Team use only</div>',
    unsafe_allow_html=True
)
