"""Differential contract tests: .NET canonical normalization against Python reference."""
from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from docflow_worker.text_document_models import RawTextDocumentInput
from docflow_worker.text_document_normalizer import TextDocumentNormalizer

ROOT = Path(__file__).resolve().parents[3]
CLI_DLL = ROOT / "tools/DocFlow.Normalization.Cli/bin/Release/net8.0/DocFlow.Normalization.Cli.dll"
SAMPLE = Path(__file__).parent / "fixtures/sample_transcript.json"

# Python-only CI does not install dotnet or compile this optional native binary.
# Dedicated .NET parity CI builds it first and must execute all cases.
pytestmark = pytest.mark.skipif(not CLI_DLL.is_file(), reason="Native .NET CLI not built in this job")


def native_normalize(payload: dict) -> dict:
    completed = subprocess.run(
        ["dotnet", str(CLI_DLL)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=15,
    )
    return json.loads(completed.stdout)


def python_normalize(payload: dict) -> dict:
    raw = RawTextDocumentInput.model_validate(payload)
    return TextDocumentNormalizer().normalize(raw).model_dump(mode="json")


@pytest.mark.parametrize("change", ["base", "reverse", "crlf", "unicode", "optional_timestamps", "timezone", "source_identity"])
def test_native_matches_python_exact_output(change: str) -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if change == "reverse":
        payload["segments"].reverse()
    elif change == "crlf":
        payload["segments"][0]["text"] = " First line\r\nSecond line "
    elif change == "unicode":
        payload["title"] = "Квартальный отчёт — Möller"
        payload["segments"][0]["text"] = "Выручка выросла на 15%."
    elif change == "optional_timestamps":
        payload["source"]["source_timestamp"] = None
        payload["source"]["published_at"] = None
        payload["source"]["retrieved_at"] = None
    elif change == "timezone":
        payload["source"]["source_timestamp"] = "2026-09-30T17:00:00+03:00"
        payload["source"]["published_at"] = "2026-09-30T18:00:00+03:00"
        payload["source"]["retrieved_at"] = "2026-10-01T11:30:00+03:00"
    elif change == "source_identity":
        payload["source"]["source_document_id"] = "revised-q3"
    expected = python_normalize(payload)
    actual = native_normalize(payload)
    assert actual == expected
    assert actual["document_id"] == expected["document_id"]
    assert actual["fingerprint"] == expected["fingerprint"]
    assert [x["segment_id"] for x in actual["segments"]] == [
        x["segment_id"] for x in expected["segments"]
    ]


@pytest.mark.parametrize("change", ["empty_segments", "duplicate_sequence", "duplicate_participant", "unknown_participant", "missing_identity", "bad_time"])
def test_native_and_python_both_reject_invalid_input(change: str) -> None:
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    if change == "empty_segments":
        payload["segments"] = []
    elif change == "duplicate_sequence":
        payload["segments"][1]["sequence"] = payload["segments"][0]["sequence"]
    elif change == "duplicate_participant":
        payload["participants"][1]["participant_id"] = payload["participants"][0]["participant_id"]
    elif change == "unknown_participant":
        payload["segments"][0]["participant_id"] = "missing"
    elif change == "missing_identity":
        payload["source"]["source_document_id"] = None
        payload["source"]["source_uri"] = None
    elif change == "bad_time":
        payload["source"]["retrieved_at"] = "2020-01-01T00:00:00Z"
    with pytest.raises(ValueError):
        python_normalize(payload)
    completed = subprocess.run(
        ["dotnet", str(CLI_DLL)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        timeout=15,
    )
    assert completed.returncode != 0
    assert "Invalid document" in completed.stderr
