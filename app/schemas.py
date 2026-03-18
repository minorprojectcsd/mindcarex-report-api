from pydantic import BaseModel


class GenerateReportRequest(BaseModel):
    session_id: str
