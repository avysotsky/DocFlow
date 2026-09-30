import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from docflow_worker.benchmarking import (
    BenchmarkCaseResult,
    BenchmarkMetadata,
    FieldComparison,
    _build_breakdowns,
    _build_metrics,
    classify_failure_reasons,
    compare_expected_fields,
    load_manifest,
    run_benchmark,
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


def test_classify_failure_reasons_distinguishes_failure_modes() -> None:
    comparisons = [
        FieldComparison(
            path="data.currency",
            expected="USD",
            actual="EUR",
            matched=False,
        ),
        FieldComparison(
            path="data.total",
            expected="100.00",
            actual=None,
            matched=False,
            error="Path not found: 'total'",
        ),
    ]

    reasons = classify_failure_reasons(
        expected_document_type="supplier_invoice",
        actual_document_type="supplier_quotation",
        expected_validation_status="valid",
        actual_validation_status="invalid",
        comparisons=comparisons,
    )

    assert reasons == [
        "document_type_mismatch",
        "validation_status_mismatch",
        "missing_field",
        "field_mismatch",
    ]


def test_classify_failure_reasons_processing_error_is_terminal() -> None:
    reasons = classify_failure_reasons(
        expected_document_type="supplier_invoice",
        actual_document_type=None,
        expected_validation_status="valid",
        actual_validation_status=None,
        comparisons=[],
        processing_error=True,
    )

    assert reasons == ["processing_error"]


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


def test_load_manifest_normalizes_metadata_and_sha256(tmp_path: Path) -> None:
    pdf_bytes = b"private supplier pdf placeholder"
    digest = hashlib.sha256(pdf_bytes).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "documents": [
                    {
                        "id": "real-001",
                        "file": "corpus/real-001.pdf",
                        "sha256": digest.upper(),
                        "metadata": {
                            "supplier": "  Supplier A  ",
                            "source_kind": "digital",
                            "layout_class": "  multi-page-table  ",
                            "language": "  en  ",
                            "tags": ["vat", "vat", "purchase-order"],
                        },
                        "expected": {"document_type": "supplier_invoice"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    case = manifest.documents[0]

    assert case.sha256 == digest
    assert case.metadata.supplier == "Supplier A"
    assert case.metadata.source_kind == "digital"
    assert case.metadata.layout_class == "multi-page-table"
    assert case.metadata.language == "en"
    assert case.metadata.tags == ["vat", "purchase-order"]


def test_load_manifest_rejects_invalid_sha256(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "documents": [
                    {
                        "id": "real-001",
                        "file": "corpus/real-001.pdf",
                        "sha256": "not-a-sha256",
                        "expected": {"document_type": "supplier_invoice"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="64-character hexadecimal digest"):
        load_manifest(manifest_path)


def test_run_benchmark_reports_corpus_integrity_error_before_pdf_processing(
    tmp_path: Path,
) -> None:
    corpus_directory = tmp_path / "corpus"
    corpus_directory.mkdir()
    pdf_path = corpus_directory / "real-001.pdf"
    pdf_path.write_bytes(b"not actually a pdf; hash check should run first")

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "documents": [
                    {
                        "id": "real-001",
                        "file": "corpus/real-001.pdf",
                        "sha256": "0" * 64,
                        "metadata": {
                            "supplier": "Supplier A",
                            "source_kind": "scanned",
                            "tags": ["noisy"],
                        },
                        "expected": {"document_type": "supplier_invoice"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = asyncio.run(run_benchmark(manifest_path))
    result = report.documents[0]

    assert result.passed is False
    assert result.failure_reasons == ["corpus_integrity_error"]
    assert result.file_sha256 == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert result.metadata.supplier == "Supplier A"
    assert result.metadata.source_kind == "scanned"
    assert result.metadata.tags == ["noisy"]
    assert "SHA-256 mismatch" in (result.error or "")
    assert report.metrics.failure_reason_counts == {"corpus_integrity_error": 1}
    assert report.breakdowns.by_supplier["Supplier A"].documents_failed == 1
    assert report.breakdowns.by_source_kind["scanned"].documents_failed == 1


def test_build_metrics_counts_document_field_and_failure_accuracy() -> None:
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
            failure_reasons=[
                "document_type_mismatch",
                "validation_status_mismatch",
                "field_mismatch",
            ],
        ),
        BenchmarkCaseResult(
            id="error",
            file="missing.pdf",
            passed=False,
            expected_document_type="supplier_invoice",
            failure_reasons=["processing_error"],
            error="FileNotFoundError: missing.pdf",
        ),
    ]

    metrics = _build_metrics(results)

    assert metrics.documents_total == 3
    assert metrics.documents_passed == 1
    assert metrics.documents_failed == 2
    assert metrics.document_pass_rate == pytest.approx(1 / 3)
    assert metrics.document_type_accuracy == pytest.approx(1 / 3)
    assert metrics.validation_status_accuracy == 0.5
    assert metrics.field_accuracy == 0.5
    assert metrics.failure_reason_counts == {
        "document_type_mismatch": 1,
        "field_mismatch": 1,
        "processing_error": 1,
        "validation_status_mismatch": 1,
    }


def test_build_breakdowns_groups_real_corpus_dimensions() -> None:
    results = [
        BenchmarkCaseResult(
            id="supplier-a-ok",
            file="a.pdf",
            passed=True,
            expected_document_type="supplier_quotation",
            actual_document_type="supplier_quotation",
            metadata=BenchmarkMetadata(
                supplier="supplier-a",
                source_kind="digital",
                layout_class="borderless",
                language="en",
            ),
        ),
        BenchmarkCaseResult(
            id="supplier-a-fail",
            file="b.pdf",
            passed=False,
            expected_document_type="supplier_invoice",
            actual_document_type="supplier_invoice",
            metadata=BenchmarkMetadata(
                supplier="supplier-a",
                source_kind="scanned",
                layout_class="table",
                language="en",
            ),
            failure_reasons=["missing_field"],
        ),
        BenchmarkCaseResult(
            id="supplier-b-ok",
            file="c.pdf",
            passed=True,
            expected_document_type="supplier_invoice",
            actual_document_type="supplier_invoice",
            metadata=BenchmarkMetadata(
                supplier="supplier-b",
                source_kind="digital",
                layout_class="table",
                language="de",
            ),
        ),
        BenchmarkCaseResult(
            id="unspecified",
            file="d.pdf",
            passed=False,
            expected_document_type="supplier_invoice",
            metadata=BenchmarkMetadata(source_kind="unknown"),
            failure_reasons=["processing_error"],
        ),
    ]

    breakdowns = _build_breakdowns(results)

    assert breakdowns.by_supplier["supplier-a"].documents_total == 2
    assert breakdowns.by_supplier["supplier-a"].document_pass_rate == 0.5
    assert breakdowns.by_supplier["supplier-b"].documents_total == 1
    assert "unknown" not in breakdowns.by_supplier

    assert breakdowns.by_source_kind["digital"].documents_total == 2
    assert breakdowns.by_source_kind["scanned"].documents_total == 1
    assert breakdowns.by_source_kind["unknown"].documents_total == 1

    assert breakdowns.by_layout_class["table"].documents_total == 2
    assert breakdowns.by_layout_class["borderless"].documents_total == 1
    assert breakdowns.by_language["en"].documents_total == 2
    assert breakdowns.by_language["de"].documents_total == 1
