# 📋 MindCareX — Report Generator Service (SVC2)

> AI-powered clinical report generation after mental health consultation sessions.
> Reads voice analysis data from Neon, generates reports via Groq LLaMA.

---

## What This Service Does

After a video consultation session ends, this service:

1. Reads the session transcript and summary from Neon (written by SVC1)
2. Sends two prompts to Groq LLaMA (`llama-3.3-70b-versatile`)
3. Gets back a structured clinical report + a plain-language guardian message
4. Stores both in Neon
5. Spring Boot reads the `guardian_message` from here and emails it to the patient's emergency contact

---

## Report Output

### Clinical report sections (`report_json`)

| Field | Description |
|-------|-------------|
| `session_overview` | 2–3 sentence clinical summary |
| `stress_analysis` | Detailed stress pattern analysis |
| `vocal_indicators` | Interpretation of pitch, entropy, silence |
| `emotional_state` | Emotional assessment during session |
| `risk_assessment` | Risk level reasoning with evidence |
| `recommendations` | Array of clinical action items |
| `follow_up` | Suggested next steps and timeline |

### Other fields

| Field | Used by |
|-------|---------|
| `clinical_notes` | Formatted text for doctor dashboard |
| `guardian_message` | Plain English 3–4 paragraphs for parent/guardian. **Spring Boot emails this.** |

---

## File Structure

```
svc2/
├── main.py                  FastAPI app, creates DB tables on startup
├── requirements.txt
├── Dockerfile               python:3.11-slim (no ffmpeg needed)
├── .env.example
└── app/
    ├── config.py            env vars
    ├── database.py          Neon SQLAlchemy engine, pool_size=3
    ├── models.py            SessionReport table + VoiceSessionRO (read-only mirror of SVC1)
    ├── schemas.py           GenerateReportRequest Pydantic model
    ├── report_generator.py  two Groq LLaMA prompts → clinical JSON + guardian text
    └── router.py            generate, get, patient history endpoints
```

---

## Database Tables

Reads from SVC1 tables (no write permission assumed):
- `voice_sessions` — transcript + summary_json
- `voice_chunks` — not directly used

Creates and owns:

**`session_reports`**
```
session_id (PK), patient_id, generated_at,
report_json, clinical_notes, guardian_message
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `POST` | `/api/report/generate` | Generate report. Body: `{session_id}`. Idempotent — returns cached if exists |
| `GET` | `/api/report/{id}` | Fetch stored report |
| `GET` | `/api/report/patient/{id}/history` | All reports for a patient, newest first |

### Generate request body

```json
{
  "session_id": "uuid-of-completed-voice-session"
}
```

### Generate response shape

```json
{
  "success": true,
  "data": {
    "session_id": "uuid",
    "patient_id": "uuid",
    "generated_at": "2026-03-20T10:00:00",
    "report": {
      "session_overview": "The patient expressed feelings of sadness...",
      "stress_analysis": "Stress scores remained elevated throughout...",
      "vocal_indicators": "Pitch variability was high suggesting...",
      "emotional_state": "Patient showed signs of mild depression...",
      "risk_assessment": "Risk level is low. No immediate concerns...",
      "recommendations": [
        "Schedule follow-up within 2 weeks",
        "Consider CBT referral"
      ],
      "follow_up": "Next session recommended in 14 days."
    },
    "clinical_notes": "SESSION ID: ...\nAVG STRESS: 57.5/100...",
    "guardian_message": "Dear Akash, we wanted to update you about Abhinav's session today..."
  }
}
```

### Error responses

```json
{"success": false, "error": "Session not found", "status": 404}
{"success": false, "error": "Session is not completed yet. Call POST /api/voice/session/stop in svc1 first.", "status": 400}
```

---

## Behaviour Details

**Idempotent** — calling `generate` twice returns the cached report on the second call, no extra Groq API call.

**Graceful empty session handling** — if the session has no audio chunks (mic not working), returns a pre-written fallback report instead of crashing with a Groq error.

**Spring Boot integration** — after generating a report, Spring Boot calls `GET /api/report/{session_id}` and extracts `guardian_message` to include in the guardian notification email.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✅ Yes | Same Neon connection string as SVC1 |
| `GROQ_API_KEY` | ✅ Yes | Groq API key. Free at console.groq.com |
| `GROQ_MODEL` | Optional | Default: `llama-3.3-70b-versatile` |
| `ALLOWED_ORIGINS` | Optional | CORS origins. Default: `http://localhost:5173` |

### `.env.example`

```env
DATABASE_URL=postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require
GROQ_API_KEY=gsk_xxxxxxxxxxxx
GROQ_MODEL=llama-3.3-70b-versatile
ALLOWED_ORIGINS=https://mindcarex.vercel.app,http://localhost:5173
```

---

## Running Locally

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

Verify:
```bash
curl http://localhost:8001/health
# {"status":"ok","service":"svc2_report_generator"}
```

Test (requires a completed SVC1 session):
```bash
curl -X POST http://localhost:8001/api/report/generate \
  -H "Content-Type: application/json" \
  -d '{"session_id":"YOUR_COMPLETED_SESSION_ID"}'
```

---

## Docker

```bash
docker build -t mindcarex-svc2 .
docker run -p 8001:8001 --env-file .env mindcarex-svc2
```

---

## Notes

- SVC1 must be run first — this service reads `voice_sessions` and `voice_chunks` tables written by SVC1
- Session must have `status = "completed"` before report generation (call `POST /api/voice/session/stop` first)
- Groq free tier limit: sufficient for typical consultation volumes
- Model `llama-3.3-70b-versatile` replaced `llama3-70b-8192` in March 2026 (deprecated by Groq)
