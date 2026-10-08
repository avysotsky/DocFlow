"""Thin versioned HTTP host for generic DocFlow text extraction."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from docflow_worker.engines import (
    GroqSchemaDrivenTextExtractionBackend,
    OpenAiSchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.text_document_models import RawTextDocumentInput
from docflow_worker.text_artifact_pipeline import BackendFactory, extract_text_document

MAX_REQUEST_BYTES = 1_048_576


class ExtractionHttpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(alias="schemaVersion", ge=1, le=1)
    raw_document: RawTextDocumentInput = Field(alias="rawDocument")
    schema_request: SchemaDrivenTextExtractionRequest = Field(alias="schemaRequest")
    provider: str
    model: str = Field(min_length=1, max_length=200)
    document_name: str | None = Field(default=None, alias="documentName", max_length=256)


def _factory_for(provider: str) -> BackendFactory:
    if provider == "openai":
        return OpenAiSchemaDrivenTextExtractionBackend
    if provider == "groq":
        return GroqSchemaDrivenTextExtractionBackend
    raise ValueError("Unsupported provider")


def create_app(
    *,
    backend_factory: BackendFactory | None = None,
) -> FastAPI:
    app = FastAPI(title="DocFlow API", version="1.0.0", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def limit_body(request: Request, call_next):
        if request.url.path == "/api/v1/extractions":
            if request.headers.get("content-length"):
                try:
                    if int(request.headers["content-length"]) > MAX_REQUEST_BYTES:
                        return JSONResponse(status_code=413, content={"error": "request_too_large"})
                except ValueError:
                    return JSONResponse(status_code=400, content={"error": "invalid_request"})
            body = await request.body()
            if len(body) > MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413, content={"error": "request_too_large"})
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": "invalid_request"})

    @app.get("/health/live")
    async def liveness():
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness():
        # Readiness does not claim external LLM provider availability.
        return {"status": "ready", "providerConnectivityChecked": False}

    @app.post("/api/v1/extractions")
    async def extract(payload: ExtractionHttpRequest):
        if payload.provider not in ("openai", "groq") or not payload.model.strip():
            return JSONResponse(status_code=422, content={"error": "invalid_request"})
        try:
            normalized, structured = await extract_text_document(
                payload.raw_document,
                payload.schema_request,
                model=payload.model,
                backend_factory=backend_factory or _factory_for(payload.provider),
                document_name=payload.document_name,
            )
        except (ValidationError, ValueError):
            return JSONResponse(status_code=422, content={"error": "invalid_request"})
        except Exception:
            # Never return provider exception messages, payload, or credentials.
            return JSONResponse(status_code=502, content={"error": "extraction_failed"})

        return {
            "schemaVersion": 1,
            "normalizedDocument": normalized.model_dump(mode="json"),
            "structuredResult": structured.model_dump(mode="json"),
        }

    return app


app = create_app()
