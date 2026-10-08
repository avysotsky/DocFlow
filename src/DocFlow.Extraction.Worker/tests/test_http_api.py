"""ARCH-01 HTTP and in-process parity: offline synthetic data only."""
import asyncio

import httpx
from docflow_worker.engines import (
    SchemaDrivenTextExtractionBackend,
    SchemaDrivenTextExtractionBackendResult,
    SchemaDrivenTextExtractionRequest,
)
from docflow_worker.http_api import create_app
from docflow_worker.text_document_models import RawTextDocumentInput
from docflow_worker.text_artifact_pipeline import extract_text_document


RAW = {
    "title": "Sample note",
    "document_type": "generic",
    "source": {
        "provider": "synthetic",
        "source_document_id": "sample-1",
        "source_timestamp": "2026-10-01T10:00:00Z",
        "published_at": "2026-10-01T10:01:00Z",
        "retrieved_at": "2026-10-01T10:02:00Z",
    },
    "participants": [],
    "segments": [{"sequence": 1, "text": "Example text."}],
}
SCHEMA = {
    "schema_name": "sample",
    "schema_version": 1,
    "json_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["category"],
        "properties": {"category": {"type": "string"}},
    },
}


class FakeBackend(SchemaDrivenTextExtractionBackend):
    @property
    def name(self):
        return "http_fake"

    async def extract(self, content, *, request, document_name=None):
        return SchemaDrivenTextExtractionBackendResult(
            data={"category": "generic"}, confidence=None
        )


def factory(model):
    assert model == "model-test"
    return FakeBackend()


def request():
    return {
        "schemaVersion": 1,
        "rawDocument": RAW,
        "schemaRequest": SCHEMA,
        "provider": "groq",
        "model": "model-test",
    }


async def post(path, payload, *, app=None):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app or create_app(backend_factory=factory)),
        base_url="http://test",
    ) as client:
        return await client.post(path, json=payload)


def test_http_and_in_process_share_exact_application_result():
    async def run():
        normalized, structured = await extract_text_document(
            RawTextDocumentInput.model_validate(RAW),
            SchemaDrivenTextExtractionRequest.model_validate(SCHEMA),
            model="model-test",
            backend_factory=factory,
        )
        response = await post("/api/v1/extractions", request())
        assert response.status_code == 200
        assert response.json() == {
            "schemaVersion": 1,
            "normalizedDocument": normalized.model_dump(mode="json"),
            "structuredResult": structured.model_dump(mode="json"),
        }
    asyncio.run(run())


def test_invalid_input_is_rejected_without_provider_details():
    async def run():
        for changes in (
            {"schemaVersion": 2},
            {"provider": "unknown"},
            {"model": ""},
            {"schemaRequest": {"schema_name": "bad"}},
            {"unexpected": "not allowed"},
        ):
            payload = request()
            payload.update(changes)
            response = await post("/api/v1/extractions", payload)
            assert response.status_code == 422
            assert response.json() == {"error": "invalid_request"}
    asyncio.run(run())


def test_provider_failure_is_redacted():
    def broken(_model):
        raise RuntimeError("provider-key-and-private-document")

    async def run():
        response = await post("/api/v1/extractions", request(), app=create_app(backend_factory=broken))
        assert response.status_code == 502
        assert response.json() == {"error": "extraction_failed"}
        assert "provider-key-and-private-document" not in response.text
    asyncio.run(run())


def test_oversized_body_and_health_endpoints():
    async def run():
        app = create_app(backend_factory=factory)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get("/health/live")).json() == {"status": "ok"}
            ready = await client.get("/health/ready")
            assert ready.json()["providerConnectivityChecked"] is False
            result = await client.post(
                "/api/v1/extractions",
                content=b"x" * 1_048_577,
                headers={"content-type": "application/json"},
            )
            assert result.status_code == 413
    asyncio.run(run())
