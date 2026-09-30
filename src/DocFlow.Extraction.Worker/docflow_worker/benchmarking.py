import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from docflow_worker.pdf_content_extractor import PdfContentExtractor
from docflow_worker.structured_pipeline import extract_structured_document


class BenchmarkExpectation(BaseModel):
    document_type: Literal["supplier_quotation", "supplier_invoice"]
    validation_status: Literal["valid", "invalid", "incomplete"] | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    id: str
    file: str
    document_type: Literal["auto", "supplier_quotation", "supplier_invoice"] = "auto"
    expected: BenchmarkExpectation

    @field_validator("id", "file")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
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
    field_comparisons: list[FieldComparison] = Field(default_factory=list)
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


class BenchmarkReport(BaseModel):
    manifest_version: int
    manifest_path: str
    metrics: BenchmarkMetrics
    documents: list[BenchmarkCaseResult]


def load_manifest(path: str | Path) -> BenchmarkManifest:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return BenchmarkManifest.model_validate(payload)


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
                    field_comparisons=comparisons,
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
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    report = BenchmarkReport(
        manifest_version=manifest.version,
        manifest_path=str(manifest_path),
        metrics=_build_metrics(results),
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
    )
