"""FastAPI service exposing the triage agent (Task 1) and account brief (Task 2).

Run:  uvicorn src.api:app --reload
Docs: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.llm import LLMError
from src.triage import triage_ticket

app = FastAPI(
    title="Support & TAM AI Toolkit",
    description="Ticket triage and account health briefs for Technical Support and TAM teams.",
    version="1.0.0",
)


class TriageRequest(BaseModel):
    subject: str = Field(default="", description="Ticket subject line")
    body: str = Field(default="", description="Ticket body text")
    ticket_id: str | None = Field(default=None, description="Optional ticket identifier")

    model_config = {
        "json_schema_extra": {
            "example": {
                "subject": "Unable to connect DataBridge Pro to Connectors",
                "body": "Our Connectors pipeline has been failing since yesterday. "
                        "Error: 'ERR_CONNECTION_TIMEOUT after 30s'. Production is down "
                        "and 47 engineers are blocked.",
                "ticket_id": "TKT-99999",
            }
        }
    }


@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/triage")
def triage(request: TriageRequest) -> dict:
    """Task 1 — classify, route, and draft a first response for an incoming ticket."""
    try:
        return triage_ticket(
            subject=request.subject,
            body=request.body,
            ticket_id=request.ticket_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {exc}") from exc
    