"""
router.py — Report generation endpoints

POST /report/generate                   → pull session from Neon, run LLaMA, store report
GET  /report/{session_id}               → get stored report
GET  /report/patient/{patient_id}/history → all reports for a patient
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database         import get_db
from app.models           import SessionReport, VoiceSessionRO
from app.schemas          import GenerateReportRequest
from app.report_generator import generate

router = APIRouter()
log    = logging.getLogger("report_router")


def ok(data: dict, code: int = 200) -> JSONResponse:
    return JSONResponse({"success": True,  "data":  data}, status_code=code)

def err(msg: str,  code: int = 400) -> JSONResponse:
    return JSONResponse({"success": False, "error": msg},  status_code=code)


# ══════════════════════════════════════════════════════════════════════════════
# POST /report/generate
# Body: { "session_id": "..." }
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/report/generate", status_code=201)
def generate_report(
    body: GenerateReportRequest,
    db:   Annotated[Session, Depends(get_db)],
):
    # Pull session written by svc1
    session = db.query(VoiceSessionRO).filter(VoiceSessionRO.id == body.session_id).first()
    if not session:
        return err(f"Session {body.session_id} not found in database", 404)

    if session.status != "completed":
        return err(
            "Session is not completed yet. "
            "Call POST /api/voice/session/stop in svc1 first."
        )

    # Return cached report if it already exists
    existing = db.query(SessionReport).filter(SessionReport.session_id == body.session_id).first()
    if existing:
        return ok({"note": "Returning cached report", **existing.to_dict()})

    # Generate via Groq LLaMA
    try:
        result = generate(
            session_id=session.id,
            patient_id=session.patient_id,
            label=session.label or "Voice Session",
            transcript=session.full_transcript or "",
            summary=session.summary_json or {},
        )
    except Exception as e:
        log.error(f"Report generation failed: {e}")
        return err(f"Report generation failed: {str(e)}", 500)

    # Store in Neon
    report = SessionReport(
        session_id=session.id,
        patient_id=session.patient_id,
        report_json=result["report_json"],
        clinical_notes=result["clinical_notes"],
        guardian_message=result["guardian_message"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    return ok(report.to_dict(), 201)


# ══════════════════════════════════════════════════════════════════════════════
# GET /report/{session_id}
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/report/{session_id}")
def get_report(session_id: str, db: Annotated[Session, Depends(get_db)]):
    report = db.query(SessionReport).filter(SessionReport.session_id == session_id).first()
    if not report:
        return err("Report not found. Call POST /report/generate first.", 404)
    return ok(report.to_dict())


# ══════════════════════════════════════════════════════════════════════════════
# GET /report/patient/{patient_id}/history
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/report/patient/{patient_id}/history")
def get_patient_history(patient_id: str, db: Annotated[Session, Depends(get_db)]):
    reports = (
        db.query(SessionReport)
        .filter(SessionReport.patient_id == patient_id)
        .order_by(SessionReport.generated_at.desc())
        .all()
    )
    return ok({
        "patient_id":    patient_id,
        "total_reports": len(reports),
        "reports": [
            {
                "session_id":        r.session_id,
                "generated_at":      r.generated_at.isoformat() if r.generated_at else None,
                "risk_assessment":   (r.report_json or {}).get("risk_assessment", "")[:120],
                "guardian_preview":  r.guardian_message[:200] + "…"
                                     if len(r.guardian_message or "") > 200
                                     else r.guardian_message,
            }
            for r in reports
        ],
    })
