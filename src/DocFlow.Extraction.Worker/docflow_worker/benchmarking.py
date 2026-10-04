import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from docflow_worker.pdf_content_extractor import PdfContentExtractor
from docflow_worker.structured_pipeline import extract_structured_document


FailureReason = Literal[
    "processing_error",
    "corpus_integrity_error",
    "document_type_mismatch",
    "validation_status_mismatch",
    "missing_field",
    "field_mismatch",
]


class BenchmarkMetadata(BaseModel):
    supplier: str | None = None
    source_kind: Literal["digital", "scanned", "mixed", "unknown"] = "unknown"
    layout_class: str | None = None
    language: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("supplier", "layout_class", "language")
    @classmethod
    def _optional_text_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank when provided")
        return value

    @field_validator("tags")
    @classmethod
    def _normalize_tags(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for tag in value:
            tag = tag.strip()
            if not tag:
                raise ValueError("tags must not contain blank values")
            if tag not in seen:
                normalized.append(tag)
                seen.add(tag)
        return normalized


class BenchmarkExpectation(BaseModel):
    document_type: Literal["supplier_quotation", "supplier_invoice", "purchase_order"]
    validation_status: Literal["valid", "invalid", "incomplete"] | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    id: str
    file: str
    sha256: str | None = None
    metadata: BenchmarkMetadata = Field(default_factory=BenchmarkMetadata)
    document_type: Literal["auto", "supplier_quotation", "supplier_invoice", "purchase_order"] = "auto"
    expected: BenchmarkExpectation

    @field_validator("id", "file")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("sha256")
    @classmethod
    def _valid_sha256(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return value


class BenchmarkManifest(BaseModel):
    version: int = 1
    documents: list[BenchmarkCase]

    @field_validator("documents")
    @classmethod
    def _documents_not_empty(cls, value: list[BenchmarkCase]) -> list[BenchmarkCase]:
        if not value:
            raise ValueError("benchmark manifest must contain at least one document")
        ids = [case.id for case in value]
        if len(ids) != len(set(ids)):
            raise ValueError("benchmark document ids must be unique")
        return value


class FieldComparison(BaseModel):
    path: str
    expected: Any
    actual: Any = None
    matched: bool
    error: str | None = None


class BenchmarkCaseResult(BaseModel):
    id: str
    file: str
    passed: bool
    expected_document_type: str
    actual_document_type: str | None = None
    expected_validation_status: str | None = None
    actual_validation_status: str | None = None
    confidence: float | None = None
    ocr_applied: bool | None = None
    ocr_page_numbers: list[int] = Field(default_factory=list)
    file_sha256: str | None = None
    metadata: BenchmarkMetadata = Field(default_factory=BenchmarkMetadata)
    field_comparisons: list[FieldComparison] = Field(default_factory=list)
    failure_reasons: list[FailureReason] = Field(default_factory=list)
    error: str | None = None


class BenchmarkMetrics(BaseModel):
    documents_total: int
    documents_passed: int
    documents_failed: int
    document_pass_rate: float
    document_type_correct: int
    document_type_accuracy: float
    validation_status_checked: int
    validation_status_correct: int
    validation_status_accuracy: float | None
    fields_checked: int
    fields_matched: int
    field_accuracy: float | None
    failure_reason_counts: dict[str, int] = Field(default_factory=dict)


class BenchmarkBreakdowns(BaseModel):
    by_supplier: dict[str, BenchmarkMetrics] = Field(default_factory=dict)
    by_source_kind: dict[str, BenchmarkMetrics] = Field(default_factory=dict)
    by_layout_class: dict[str, BenchmarkMetrics] = Field(default_factory=dict)
    by_language: dict[str, BenchmarkMetrics] = Field(default_factory=dict)


class BenchmarkReport(BaseModel):
    manifest_version: int
    manifest_path: str
    metrics: BenchmarkMetrics
    breakdowns: BenchmarkBreakdowns = Field(default_factory=BenchmarkBreakdowns)
    documents: list[BenchmarkCaseResult]


def load_manifest(path: str | Path) -> BenchmarkManifest:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return BenchmarkManifest.model_validate(payload)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_stream:
        for chunk in iter(lambda: file_stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_path_value(root: Any, path: str) -> Any:
    current = root
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                raise KeyError(segment)
            current = current[segment]
        elif isinstance(current, list):
            try:
                index = int(segment)
            except ValueError as exc:
                raise KeyError(segment) from exc
            if index < 0 or index >= len(current):
                raise IndexError(index)
            current = current[index]
        else:
            raise KeyError(segment)
    return current


def compare_expected_fields(
    actual: dict[str, Any],
    expected_fields: dict[str, Any],
) -> list[FieldComparison]:
    comparisons: list[FieldComparison] = []

    for path, expected in expected_fields.items():
        try:
            actual_value = _get_path_value(actual, path)
        except (KeyError, IndexError) as exc:
            comparisons.append(
                FieldComparison(
                    path=path,
                    expected=expected,
                    actual=None,
                    matched=False,
                    error=f"Path not found: {exc}",
                )
            )
            continue

        comparisons.append(
            FieldComparison(
                path=path,
                expected=expected,
                actual=actual_value,
                matched=actual_value == expected,
            )
        )

    return comparisons


def classify_failure_reasons(
    *,
    expected_document_type: str,
    actual_document_type: str | None,
    expected_validation_status: str | None,
    actual_validation_status: str | None,
    comparisons: list[FieldComparison],
    processing_error: bool = False,
) -> list[FailureReason]:
    reasons: list[FailureReason] = []

    if processing_error:
        return ["processing_error"]

    if actual_document_type != expected_document_type:
        reasons.append("document_type_mismatch")

    if (
        expected_validation_status is not None
        and actual_validation_status != expected_validation_status
    ):
        reasons.append("validation_status_mismatch")

    if any(not comparison.matched and comparison.error for comparison in comparisons):
        reasons.append("missing_field")

    if any(not comparison.matched and comparison.error is None for comparison in comparisons):
        reasons.append("field_mismatch")

    return reasons


async def run_benchmark(
    manifest_path: str | Path,
    *,
    output_path: str | Path | None = None,
    enable_ocr: bool = True,
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    tessdata: str | None = None,
) -> BenchmarkReport:
    manifest_path = Path(manifest_path).resolve()
    manifest = load_manifest(manifest_path)
    manifest_directory = manifest_path.parent
    results: list[BenchmarkCaseResult] = []

    for case in manifest.documents:
        pdf_path = (manifest_directory / case.file).resolve()

        try:
            actual_sha256 = _sha256_file(pdf_path)

            if case.sha256 is not None and actual_sha256 != case.sha256:
                results.append(
                    BenchmarkCaseResult(
                        id=case.id,
                        file=case.file,
                        passed=False,
                        expected_document_type=case.expected.document_type,
                        expected_validation_status=case.expected.validation_status,
                        file_sha256=actual_sha256,
                        metadata=case.metadata,
                        failure_reasons=["corpus_integrity_error"],
                        error=(
                            "SHA-256 mismatch: "
                            f"expected {case.sha256}, actual {actual_sha256}"
                        ),
                    )
                )
                continue

            content = PdfContentExtractor(
                enable_ocr=enable_ocr,
                ocr_language=ocr_language,
                ocr_dpi=ocr_dpi,
                tessdata=tessdata,
            ).extract(pdf_path)

            structured = await extract_structured_document(
                content,
                document_type=case.document_type,
                document_name=case.file,
            )
            actual = structured.model_dump(mode="json")
            comparisons = compare_expected_fields(actual, case.expected.fields)

            type_correct = structured.document_type == case.expected.document_type
            validation_correct = (
                case.expected.validation_status is None
                or structured.validation_status == case.expected.validation_status
            )
            fields_correct = all(comparison.matched for comparison in comparisons)
            failure_reasons = classify_failure_reasons(
                expected_document_type=case.expected.document_type,
                actual_document_type=structured.document_type,
                expected_validation_status=case.expected.validation_status,
                actual_validation_status=structured.validation_status,
                comparisons=comparisons,
            )

            results.append(
                BenchmarkCaseResult(
                    id=case.id,
                    file=case.file,
                    passed=type_correct and validation_correct and fields_correct,
                    expected_document_type=case.expected.document_type,
                    actual_document_type=structured.document_type,
                    expected_validation_status=case.expected.validation_status,
                    actual_validation_status=structured.validation_status,
                    confidence=structured.confidence,
                    ocr_applied=content.ocr_applied,
                    ocr_page_numbers=content.ocr_page_numbers,
                    file_sha256=actual_sha256,
                    metadata=case.metadata,
                    field_comparisons=comparisons,
                    failure_reasons=failure_reasons,
                )
            )
        except Exception as exc:
            results.append(
                BenchmarkCaseResult(
                    id=case.id,
                    file=case.file,
                    passed=False,
                    expected_document_type=case.expected.document_type,
                    expected_validation_status=case.expected.validation_status,
                    metadata=case.metadata,
                    failure_reasons=["processing_error"],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    report = BenchmarkReport(
        manifest_version=manifest.version,
        manifest_path=str(manifest_path),
        metrics=_build_metrics(results),
        breakdowns=_build_breakdowns(results),
        documents=results,
    )

    if output_path is not None:
        report_path = Path(output_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    return report


def _build_metrics(results: list[BenchmarkCaseResult]) -> BenchmarkMetrics:
    documents_total = len(results)
    documents_passed = sum(result.passed for result in results)
    document_type_correct = sum(
        result.actual_document_type == result.expected_document_type
        for result in results
    )

    validation_results = [
        result
        for result in results
        if result.expected_validation_status is not None
    ]
    validation_status_correct = sum(
        result.actual_validation_status == result.expected_validation_status
        for result in validation_results
    )

    comparisons = [
        comparison
        for result in results
        for comparison in result.field_comparisons
    ]
    fields_matched = sum(comparison.matched for comparison in comparisons)
    failure_reason_counts = Counter(
        reason
        for result in results
        for reason in result.failure_reasons
    )

    return BenchmarkMetrics(
        documents_total=documents_total,
        documents_passed=documents_passed,
        documents_failed=documents_total - documents_passed,
        document_pass_rate=(documents_passed / documents_total if documents_total else 0.0),
        document_type_correct=document_type_correct,
        document_type_accuracy=(
            document_type_correct / documents_total if documents_total else 0.0
        ),
        validation_status_checked=len(validation_results),
        validation_status_correct=validation_status_correct,
        validation_status_accuracy=(
            validation_status_correct / len(validation_results)
            if validation_results
            else None
        ),
        fields_checked=len(comparisons),
        fields_matched=fields_matched,
        field_accuracy=(fields_matched / len(comparisons) if comparisons else None),
        failure_reason_counts=dict(sorted(failure_reason_counts.items())),
    )


def _group_metrics(
    results: list[BenchmarkCaseResult],
    value_getter: Any,
    *,
    include_unknown: bool = False,
) -> dict[str, BenchmarkMetrics]:
    groups: dict[str, list[BenchmarkCaseResult]] = defaultdict(list)

    for result in results:
        value = value_getter(result)
        if value is None:
            if not include_unknown:
                continue
            value = "unknown"
        groups[str(value)].append(result)

    return {
        name: _build_metrics(group_results)
        for name, group_results in sorted(groups.items())
    }


def _build_breakdowns(results: list[BenchmarkCaseResult]) -> BenchmarkBreakdowns:
    return BenchmarkBreakdowns(
        by_supplier=_group_metrics(
            results,
            lambda result: result.metadata.supplier,
        ),
        by_source_kind=_group_metrics(
            results,
            lambda result: result.metadata.source_kind,
            include_unknown=True,
        ),
        by_layout_class=_group_metrics(
            results,
            lambda result: result.metadata.layout_class,
        ),
        by_language=_group_metrics(
            results,
            lambda result: result.metadata.language,
        ),
    )
