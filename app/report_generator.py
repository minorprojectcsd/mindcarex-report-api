"""
report_generator.py — Clinical report via Groq LLaMA
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


# ── Check if session has enough data ─────────────────────────────────────────

def _has_data(transcript: str, summary: dict) -> bool:
    """Return True if there is enough data to generate a meaningful report."""
    s = summary or {}
    has_chunks     = int(s.get("total_chunks", 0)) > 0
    has_transcript = bool(transcript and len(transcript.strip()) > 10)
    has_summary    = bool(s) and "error" not in s
    return has_chunks or has_transcript or has_summary


# ── Fallback report for empty sessions ───────────────────────────────────────

def _empty_report(session_id: str, patient_id: str, label: str) -> dict:
    """Return a minimal report when no audio data was captured."""
    report_json = {
        "session_overview":  "No audio data was captured during this session.",
        "stress_analysis":   "Insufficient data — no audio chunks were recorded.",
        "vocal_indicators":  "No acoustic analysis available.",
        "emotional_state":   "Could not assess — no audio data.",
        "risk_assessment":   "Risk level unknown — session had no recorded audio.",
        "recommendations":   [
            "Ensure microphone permissions are granted before starting the session.",
            "Check that the audio recording is working at the start of the next session.",
            "Consider a follow-up session to gather voice analysis data.",
        ],
        "follow_up": "Schedule a new session with audio recording enabled.",
    }
    clinical_notes = (
        f"SESSION ID : {session_id}\n"
        f"PATIENT    : {patient_id}\n"
        f"NOTE       : No audio was recorded during this session.\n"
        f"             Voice analysis requires the microphone to be active.\n\n"
        "RECOMMENDATIONS\n"
        "  • Ensure microphone permissions are granted\n"
        "  • Check audio recording at the start of the next session\n"
        "  • Schedule a follow-up session"
    )
    guardian_message = (
        f"A consultation session ({label}) was completed for your child. "
        "Unfortunately, the voice analysis system was unable to capture audio data during this session. "
        "The doctor will review the session and follow up with you directly. "
        "Please ensure the device microphone is working before the next session."
    )
    return {
        "report_json":      report_json,
        "clinical_notes":   clinical_notes,
        "guardian_message": guardian_message,
    }


# ── Prompt builders ───────────────────────────────────────────────────────────

def _clinical_prompt(transcript: str, summary: dict, label: str) -> str:
    s = summary or {}

    emotions = ", ".join(
        f"{e['label']} ({round(e['avg_score'] * 100)}%)"
        for e in (s.get("top_emotions") or [])[:5]
    ) or "none detected"

    pitch   = s.get("pitch_summary",   {}) or {}
    entropy = s.get("entropy_summary", {}) or {}

    # Safe number formatting — avoid crash if values are None
    duration     = s.get("total_duration_sec") or 0
    avg_stress   = s.get("avg_stress_score")   or 0
    peak_stress  = s.get("peak_stress_score")  or 0
    trend        = s.get("trend")              or "unknown"
    risk         = (s.get("overall_risk_level") or "unknown").upper()
    dom_label    = s.get("dominant_label")     or "unknown"
    state_dist   = s.get("state_distribution") or {}
    pitch_mean   = pitch.get("mean_hz")        or 0
    pitch_std    = pitch.get("std_hz")         or 0
    ent_mean     = entropy.get("mean")         or 0
    ent_trend    = entropy.get("trend")        or "unknown"
    chunks       = s.get("total_chunks")       or 0

    return f"""You are a clinical psychologist assistant. Generate a structured session report.

SESSION: {label}
DURATION: {duration:.0f} seconds  |  CHUNKS ANALYSED: {chunks}

STRESS METRICS:
  Average score : {avg_stress}/100
  Peak score    : {peak_stress}/100
  Trend         : {trend}
  Risk level    : {risk}
  Dominant state: {dom_label}
  Distribution  : {json.dumps(state_dist)}

VOCAL ANALYSIS:
  Dominant emotions : {emotions}
  Pitch (mean/std)  : {pitch_mean} Hz / {pitch_std} Hz
  Spectral entropy  : mean={ent_mean:.3f}  trend={ent_trend}
  (high entropy = erratic, agitated speech patterns)

TRANSCRIPT:
{transcript or '(no transcript available)'}

Respond with ONLY a valid JSON object — no markdown, no preamble:
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
    log.info(f"Generating report for session {session_id}")

    # If no audio data was captured, return a graceful fallback report
    if not _has_data(transcript, summary):
        log.warning(f"Session {session_id} has no audio data — returning empty report")
        return _empty_report(session_id, patient_id, label)

    # Step 1 — Clinical JSON from Groq
    raw = _groq(_clinical_prompt(transcript, summary, label), max_tokens=1200)
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        report_json = json.loads(raw)
    except json.JSONDecodeError as e:
        log.warning(f"JSON parse failed: {e} — storing raw")
        report_json = {"raw_output": raw, "parse_error": str(e)}

    # Step 2 — Guardian message
    try:
        guardian_message = _groq(_guardian_prompt(report_json, label), max_tokens=500)
    except Exception as e:
        log.warning(f"Guardian message failed: {e}")
        guardian_message = (
            f"A voice monitoring session ({label}) was completed for your child. "
            f"The session lasted {(summary or {}).get('total_duration_sec', 0):.0f} seconds. "
            "Please contact the doctor for a full review."
        )

    # Step 3 — Clinical notes string
    s = summary or {}
    lines = [
        f"SESSION ID : {session_id}",
        f"PATIENT    : {patient_id}",
        f"AVG STRESS : {s.get('avg_stress_score', 'N/A')}/100  "
        f"PEAK: {s.get('peak_stress_score', 'N/A')}/100  "
        f"RISK: {(s.get('overall_risk_level') or 'N/A').upper()}",
        "",
        "OVERVIEW",         report_json.get("session_overview", ""),
        "",
        "STRESS ANALYSIS",  report_json.get("stress_analysis", ""),
        "",
        "VOCAL INDICATORS", report_json.get("vocal_indicators", ""),
        "",
        "EMOTIONAL STATE",  report_json.get("emotional_state", ""),
        "",
        "RISK ASSESSMENT",  report_json.get("risk_assessment", ""),
        "",
        "RECOMMENDATIONS",
        *[f"  • {r}" for r in (report_json.get("recommendations") or [])],
        "",
        "FOLLOW-UP",        report_json.get("follow_up", ""),
    ]

    return {
        "report_json":      report_json,
        "clinical_notes":   "\n".join(lines),
        "guardian_message": guardian_message,
    }
