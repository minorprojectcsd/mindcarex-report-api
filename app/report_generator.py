"""
report_generator.py — Clinical report via Groq LLaMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reads from Neon (written by svc1):
  - full_transcript   (speech-to-text, chunk by chunk)
  - summary_json      (stress, emotions, pitch, entropy)

Produces two outputs:
  clinical_notes     → structured report for doctor
  guardian_message   → plain-language summary for parent/guardian
                       (your Spring Boot picks this up and emails it)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import json
import logging

import requests

from app.config import GROQ_API_KEY, GROQ_MODEL

log = logging.getLogger("report_generator")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


# ── Groq API call ─────────────────────────────────────────────────────────────

def _groq(prompt: str, max_tokens: int = 1200) -> str:
    r = requests.post(
        GROQ_CHAT_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model":       GROQ_MODEL,
            "messages":    [{"role": "user", "content": prompt}],
            "max_tokens":  max_tokens,
            "temperature": 0.3,
        },
        timeout=40,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ── Prompt builders ───────────────────────────────────────────────────────────

def _clinical_prompt(transcript: str, summary: dict, label: str) -> str:
    s         = summary or {}
    emotions  = ", ".join(
        f"{e['label']} ({round(e['avg_score'] * 100)}%)"
        for e in (s.get("top_emotions") or [])[:5]
    )
    pitch   = s.get("pitch_summary",   {})
    entropy = s.get("entropy_summary", {})

    return f"""You are a clinical psychologist assistant. Generate a structured session report.

SESSION: {label}
DURATION: {s.get('total_duration_sec', 0):.0f} seconds  |  CHUNKS: {s.get('total_chunks', 0)}

STRESS METRICS:
  Average score : {s.get('avg_stress_score', 0)}/100
  Peak score    : {s.get('peak_stress_score', 0)}/100
  Trend         : {s.get('trend', 'unknown')}
  Risk level    : {s.get('overall_risk_level', 'unknown').upper()}
  Dominant state: {s.get('dominant_label', 'unknown')}
  Distribution  : {json.dumps(s.get('state_distribution', {}))}

VOCAL ANALYSIS:
  Dominant emotions : {emotions or 'none detected'}
  Pitch (mean/std)  : {pitch.get('mean_hz', 0)} Hz / {pitch.get('std_hz', 0)} Hz
  Spectral entropy  : mean={entropy.get('mean', 0):.3f}  trend={entropy.get('trend', 'unknown')}
  (high entropy = erratic, agitated speech patterns)

TRANSCRIPT:
{transcript or '(no transcript — GROQ_API_KEY not set in svc1)'}

Respond with ONLY a valid JSON object — no markdown, no explanation:
{{
  "session_overview":  "2-3 sentence clinical summary",
  "stress_analysis":   "detailed pattern analysis",
  "vocal_indicators":  "clinical interpretation of acoustic features",
  "emotional_state":   "emotional assessment during session",
  "risk_assessment":   "risk level reasoning",
  "recommendations":   ["action 1", "action 2", "action 3"],
  "follow_up":         "suggested next steps"
}}"""


def _guardian_prompt(report: dict, label: str) -> str:
    return f"""You are a compassionate healthcare communicator writing to a patient's parent or guardian.
Convert this clinical report into a warm, jargon-free message (3-4 short paragraphs).
Be honest, reassuring, and focus on what support is recommended.

CLINICAL REPORT:
{json.dumps(report, indent=2)}

Write only the message body. No subject line, no greeting, no sign-off.
Session label for context: {label}"""


# ── Main entry ────────────────────────────────────────────────────────────────

def generate(
    session_id: str,
    patient_id: str,
    label: str,
    transcript: str,
    summary: dict,
) -> dict:
    """
    Returns:
      report_json      — structured clinical data (dict)
      clinical_notes   — formatted text for doctor dashboard
      guardian_message — plain text for parent (Spring Boot emails this)
    """
    log.info(f"Generating report for session {session_id}")

    # Step 1 — Clinical JSON
    raw = _groq(_clinical_prompt(transcript, summary, label), max_tokens=1200)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        report_json = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse failed: {e} — storing raw text")
        report_json = {"raw_output": raw, "parse_error": str(e)}

    # Step 2 — Guardian message
    try:
        guardian_message = _groq(_guardian_prompt(report_json, label), max_tokens=500)
    except Exception as e:
        log.warning(f"Guardian message failed: {e}")
        guardian_message = (
            f"A voice monitoring session was completed for your child ({label}). "
            f"The session lasted {summary.get('total_duration_sec', 0):.0f} seconds. "
            "Please contact the doctor for a full review."
        )

    # Step 3 — Clinical notes (readable string for doctor UI)
    s = summary or {}
    lines = [
        f"SESSION ID : {session_id}",
        f"PATIENT    : {patient_id}",
        f"AVG STRESS : {s.get('avg_stress_score', 'N/A')}/100  "
        f"PEAK: {s.get('peak_stress_score', 'N/A')}/100  "
        f"RISK: {s.get('overall_risk_level', 'N/A').upper()}",
        "",
        "OVERVIEW",
        report_json.get("session_overview", ""),
        "",
        "STRESS ANALYSIS",
        report_json.get("stress_analysis", ""),
        "",
        "VOCAL INDICATORS",
        report_json.get("vocal_indicators", ""),
        "",
        "EMOTIONAL STATE",
        report_json.get("emotional_state", ""),
        "",
        "RISK ASSESSMENT",
        report_json.get("risk_assessment", ""),
        "",
        "RECOMMENDATIONS",
        *[f"  • {r}" for r in (report_json.get("recommendations") or [])],
        "",
        "FOLLOW-UP",
        report_json.get("follow_up", ""),
    ]
    clinical_notes = "\n".join(lines)

    return {
        "report_json":       report_json,
        "clinical_notes":    clinical_notes,
        "guardian_message":  guardian_message,
    }
