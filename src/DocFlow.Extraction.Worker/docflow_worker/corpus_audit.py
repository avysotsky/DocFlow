import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from docflow_worker.benchmarking import BenchmarkManifest, load_manifest
from docflow_worker.corpus_inventory import CorpusInventory, CorpusInventoryEntry


AuditSeverity = Literal["error", "warning"]


class CorpusAuditIssue(BaseModel):
    severity: AuditSeverity
    code: str
    message: str
    document_id: str | None = None
    file: str | None = None


class CorpusAuditReport(BaseModel):
    inventory_path: str
    manifest_path: str
    errors: int
    warnings: int
    inventory_documents: int
    inventory_unique_contents: int
    manifest_documents: int
    represented_unique_contents: int
    issues: list[CorpusAuditIssue] = Field(default_factory=list)


def load_inventory(path: str | Path) -> CorpusInventory:
    inventory_path = Path(path)
    return CorpusInventory.model_validate_json(
        inventory_path.read_text(encoding="utf-8")
    )


def _resolved_inventory_entries(
    inventory: CorpusInventory,
) -> dict[Path, CorpusInventoryEntry]:
    root = Path(inventory.corpus_root).resolve()
    return {
        (root / entry.file).resolve(): entry
        for entry in inventory.documents
    }


def _issue(
    issues: list[CorpusAuditIssue],
    severity: AuditSeverity,
    code: str,
    message: str,
    *,
    document_id: str | None = None,
    file: str | None = None,
) -> None:
    issues.append(
        CorpusAuditIssue(
            severity=severity,
            code=code,
            message=message,
            document_id=document_id,
            file=file,
        )
    )


def audit_corpus(
    inventory_path: str | Path,
    manifest_path: str | Path,
) -> CorpusAuditReport:
    inventory_path = Path(inventory_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    inventory = load_inventory(inventory_path)
    manifest: BenchmarkManifest = load_manifest(manifest_path)
    manifest_directory = manifest_path.parent
    inventory_by_path = _resolved_inventory_entries(inventory)
    inventory_hashes = {entry.sha256 for entry in inventory.documents}
    issues: list[CorpusAuditIssue] = []

    for entry in inventory.documents:
        if entry.error is not None:
            _issue(
                issues,
                "error",
                "inventory_pdf_error",
                entry.error,
                file=entry.file,
            )
        if entry.duplicate_of is not None:
            _issue(
                issues,
                "warning",
                "duplicate_content_present",
                f"PDF content duplicates inventory id '{entry.duplicate_of}'.",
                file=entry.file,
            )

    manifest_paths = [
        (manifest_directory / case.file).resolve()
        for case in manifest.documents
    ]
    path_counts = Counter(manifest_paths)
    for path, count in path_counts.items():
        if count > 1:
            _issue(
                issues,
                "error",
                "duplicate_manifest_file",
                f"The same PDF path appears {count} times in the manifest.",
                file=str(path),
            )

    represented_hashes: list[str] = []

    for case, resolved_path in zip(manifest.documents, manifest_paths, strict=True):
        entry = inventory_by_path.get(resolved_path)
        if entry is None:
            _issue(
                issues,
                "error",
                "manifest_file_not_in_inventory",
                "Manifest PDF is not present in the supplied corpus inventory.",
                document_id=case.id,
                file=case.file,
            )
            continue

        represented_hashes.append(entry.sha256)

        if case.sha256 is None:
            _issue(
                issues,
                "error",
                "missing_sha256",
                "Real-corpus manifest entry must pin the PDF SHA-256 digest.",
                document_id=case.id,
                file=case.file,
            )
        elif case.sha256 != entry.sha256:
            _issue(
                issues,
                "error",
                "sha256_mismatch",
                f"Manifest SHA-256 {case.sha256} differs from inventory {entry.sha256}.",
                document_id=case.id,
                file=case.file,
            )

        if case.metadata.source_kind == "unknown" and entry.source_kind != "unknown":
            _issue(
                issues,
                "warning",
                "source_kind_not_recorded",
                f"Inventory classified the PDF as '{entry.source_kind}'.",
                document_id=case.id,
                file=case.file,
            )
        elif (
            case.metadata.source_kind != "unknown"
            and entry.source_kind != "unknown"
            and case.metadata.source_kind != entry.source_kind
        ):
            _issue(
                issues,
                "error",
                "source_kind_mismatch",
                (
                    f"Manifest source_kind '{case.metadata.source_kind}' differs from "
                    f"inventory '{entry.source_kind}'."
                ),
                document_id=case.id,
                file=case.file,
            )

        if not case.expected.fields:
            _issue(
                issues,
                "warning",
                "no_expected_fields",
                "Document has no field-level ground truth; field accuracy will not measure it.",
                document_id=case.id,
                file=case.file,
            )

        for attribute, code in (
            (case.metadata.supplier, "supplier_not_recorded"),
            (case.metadata.layout_class, "layout_class_not_recorded"),
            (case.metadata.language, "language_not_recorded"),
        ):
            if attribute is None:
                _issue(
                    issues,
                    "warning",
                    code,
                    "Recommended real-corpus metadata is missing.",
                    document_id=case.id,
                    file=case.file,
                )

    manifest_hash_counts = Counter(represented_hashes)
    for sha256, count in manifest_hash_counts.items():
        if count > 1:
            _issue(
                issues,
                "error",
                "duplicate_manifest_content",
                f"The manifest benchmarks the same PDF content {count} times (SHA-256 {sha256}).",
            )

    represented_unique_hashes = set(represented_hashes)
    for sha256 in sorted(inventory_hashes - represented_unique_hashes):
        representative = next(
            entry for entry in inventory.documents if entry.sha256 == sha256
        )
        _issue(
            issues,
            "error",
            "corpus_content_not_in_manifest",
            "Unique corpus PDF content is not represented in the benchmark manifest.",
            file=representative.file,
        )

    errors = sum(issue.severity == "error" for issue in issues)
    warnings = sum(issue.severity == "warning" for issue in issues)

    return CorpusAuditReport(
        inventory_path=str(inventory_path),
        manifest_path=str(manifest_path),
        errors=errors,
        warnings=warnings,
        inventory_documents=inventory.documents_total,
        inventory_unique_contents=inventory.unique_contents,
        manifest_documents=len(manifest.documents),
        represented_unique_contents=len(represented_unique_hashes),
        issues=issues,
    )


def write_audit_report(report: CorpusAuditReport, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
