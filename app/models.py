from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, JSON
from app.database import Base


# ── Table written by svc2 ─────────────────────────────────────────────────────

class SessionReport(Base):
    __tablename__ = "session_reports"

    session_id       = Column(String,   primary_key=True)
    patient_id       = Column(String,   nullable=False, index=True)
    generated_at     = Column(DateTime, default=datetime.utcnow)
    report_json      = Column(JSON,     nullable=True)   # structured clinical JSON
    clinical_notes   = Column(Text,     default="")      # doctor-facing formatted text
    guardian_message = Column(Text,     default="")      # parent-facing plain text

    def to_dict(self) -> dict:
        return {
            "session_id":       self.session_id,
            "patient_id":       self.patient_id,
            "generated_at":     self.generated_at.isoformat() if self.generated_at else None,
            "report":           self.report_json,
            "clinical_notes":   self.clinical_notes,
            "guardian_message": self.guardian_message,
        }


# ── Read-only mirror of svc1 table (no FK, no cascade — just reads) ───────────

class VoiceSessionRO(Base):
    """
    Mirrors svc1's voice_sessions table.
    svc2 only reads from this — never writes.
    """
    __tablename__ = "voice_sessions"

    id              = Column(String,   primary_key=True)
    patient_id      = Column(String)
    label           = Column(String)
    status          = Column(String)
    started_at      = Column(DateTime)
    ended_at        = Column(DateTime)
    full_transcript = Column(Text)
    summary_json    = Column(JSON)
