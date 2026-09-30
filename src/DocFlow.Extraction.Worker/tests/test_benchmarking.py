import json
from pathlib import Path

import pytest

from docflow_worker.benchmarking import (
    BenchmarkCaseResult,
    FieldComparison,
    _build_metrics,
    compare_expected_fields,
    load_manifest,
)


def test_compare_expected_fields_supports_nested_arrays() -> None:
    actual = {
        "data": {
            "quotation_number": "QT-001",
            "items": [
                {"sku": "AX-100", "quantity": "20"},
                {"sku": "BX-240", "quantity": "8"},
            ],
            "total": "1748.40",
        },
        "confidence": 1.0,
    }

    comparisons = compare_expected_fields(
        actual,
        {
            "data.quotation_number": "QT-001",
            "data.items.1.sku": "BX-240",
            "data.total": "1748.40",
            "confidence": 1.0,
        },
    )

    assert len(comparisons) == 4
    assert all(comparison.matched for comparison in comparisons)


def test_compare_expected_fields_reports_missing_and_mismatch() -> None:
    comparisons = compare_expected_fields(
        {"data": {"currency": "EUR"}},
        {
            "data.currency": "USD",
            "data.total": "100.00",
        },
    )

    assert comparisons[0].matched is False
    assert comparisons[0].actual == "EUR"
    assert comparisons[0].error is None

    assert comparisons[1].matched is False
    assert comparisons[1].actual is None
    assert comparisons[1].error is not None
    assert "Path not found" in comparisons[1].error


def test_load_manifest_rejects_duplicate_document_ids(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "documents": [
                    {
                        "id": "duplicate",
                        "file": "a.pdf",
                        "expected": {"document_type": "supplier_quotation"},
                    },
                    {
                        "id": "duplicate",
                        "file": "b.pdf",
                        "expected": {"document_type": "supplier_invoice"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ids must be unique"):
        load_manifest(manifest_path)


def test_build_metrics_counts_document_and_field_accuracy() -> None:
    results = [
        BenchmarkCaseResult(
            id="ok",
            file="ok.pdf",
            passed=True,
            expected_document_type="supplier_quotation",
            actual_document_type="supplier_quotation",
            expected_validation_status="valid",
            actual_validation_status="valid",
            field_comparisons=[
                FieldComparison(
                    path="data.total",
                    expected="10.00",
                    actual="10.00",
                    matched=True,
                )
            ],
        ),
        BenchmarkCaseResult(
            id="bad",
            file="bad.pdf",
            passed=False,
            expected_document_type="supplier_invoice",
            actual_document_type="supplier_quotation",
            expected_validation_status="valid",
            actual_validation_status="invalid",
            field_comparisons=[
                FieldComparison(
                    path="data.total",
                    expected="20.00",
                    actual="21.00",
                    matched=False,
                )
            ],
        ),
    ]

    metrics = _build_metrics(results)

    assert metrics.documents_total == 2
    assert metrics.documents_passed == 1
    assert metrics.documents_failed == 1
    assert metrics.document_pass_rate == 0.5
    assert metrics.document_type_accuracy == 0.5
    assert metrics.validation_status_accuracy == 0.5
    assert metrics.field_accuracy == 0.5
