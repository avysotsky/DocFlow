import json
from pathlib import Path

from docflow_worker.corpus_audit import audit_corpus
from docflow_worker.corpus_inventory import CorpusInventory, CorpusInventoryEntry


def _write_inventory(
    path: Path,
    corpus_root: Path,
    entries: list[CorpusInventoryEntry],
) -> None:
    inventory = CorpusInventory(
        corpus_root=str(corpus_root.resolve()),
        documents_total=len(entries),
        unique_contents=sum(entry.duplicate_of is None for entry in entries),
        duplicates=sum(entry.duplicate_of is not None for entry in entries),
        errors=sum(entry.error is not None for entry in entries),
        documents=entries,
    )
    path.write_text(inventory.model_dump_json(indent=2), encoding="utf-8")


def _write_manifest(path: Path, documents: list[dict]) -> None:
    path.write_text(
        json.dumps({"version": 1, "documents": documents}, indent=2),
        encoding="utf-8",
    )


def _complete_case(
    *,
    document_id: str,
    file: str,
    sha256: str | None,
    source_kind: str = "digital",
) -> dict:
    case = {
        "id": document_id,
        "file": file,
        "metadata": {
            "supplier": "supplier-a",
            "source_kind": source_kind,
            "layout_class": "table",
            "language": "en",
        },
        "document_type": "auto",
        "expected": {
            "document_type": "supplier_invoice",
            "validation_status": "valid",
            "fields": {"data.total": "100.00"},
        },
    }
    if sha256 is not None:
        case["sha256"] = sha256
    return case


def test_audit_accepts_complete_consistent_real_corpus(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    digest = "a" * 64

    inventory_path = tmp_path / "inventory.json"
    _write_inventory(
        inventory_path,
        corpus_root,
        [
            CorpusInventoryEntry(
                suggested_id="doc-a",
                file="invoice.pdf",
                sha256=digest,
                size_bytes=100,
                page_count=1,
                native_text_pages=1,
                source_kind="digital",
            )
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            _complete_case(
                document_id="invoice-a",
                file="corpus/invoice.pdf",
                sha256=digest,
            )
        ],
    )

    report = audit_corpus(inventory_path, manifest_path)

    assert report.errors == 0
    assert report.warnings == 0
    assert report.inventory_unique_contents == 1
    assert report.manifest_documents == 1
    assert report.represented_unique_contents == 1
    assert report.issues == []


def test_audit_rejects_missing_sha_and_unrepresented_unique_pdf(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    inventory_path = tmp_path / "inventory.json"
    _write_inventory(
        inventory_path,
        corpus_root,
        [
            CorpusInventoryEntry(
                suggested_id="doc-a",
                file="a.pdf",
                sha256="a" * 64,
                size_bytes=100,
                source_kind="digital",
            ),
            CorpusInventoryEntry(
                suggested_id="doc-b",
                file="b.pdf",
                sha256="b" * 64,
                size_bytes=200,
                source_kind="digital",
            ),
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            _complete_case(
                document_id="a",
                file="corpus/a.pdf",
                sha256=None,
            )
        ],
    )

    report = audit_corpus(inventory_path, manifest_path)
    codes = {issue.code for issue in report.issues}

    assert report.errors == 2
    assert "missing_sha256" in codes
    assert "corpus_file_not_in_manifest" in codes
    assert report.represented_unique_contents == 1


def test_audit_rejects_duplicate_content_in_manifest(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    digest = "c" * 64

    inventory_path = tmp_path / "inventory.json"
    _write_inventory(
        inventory_path,
        corpus_root,
        [
            CorpusInventoryEntry(
                suggested_id="doc-canonical",
                file="canonical.pdf",
                sha256=digest,
                size_bytes=100,
                source_kind="digital",
            ),
            CorpusInventoryEntry(
                suggested_id="doc-copy",
                file="copy.pdf",
                sha256=digest,
                size_bytes=100,
                source_kind="digital",
                duplicate_of="doc-canonical",
            ),
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            _complete_case(
                document_id="canonical",
                file="corpus/canonical.pdf",
                sha256=digest,
            ),
            _complete_case(
                document_id="copy",
                file="corpus/copy.pdf",
                sha256=digest,
            ),
        ],
    )

    report = audit_corpus(inventory_path, manifest_path)
    codes = [issue.code for issue in report.issues]

    assert report.errors == 1
    assert report.warnings == 1
    assert "manifest_uses_duplicate_content" in codes
    assert "duplicate_content_present" in codes
    assert report.represented_unique_contents == 1


def test_audit_reports_source_kind_mismatch_and_metadata_warnings(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    digest = "d" * 64

    inventory_path = tmp_path / "inventory.json"
    _write_inventory(
        inventory_path,
        corpus_root,
        [
            CorpusInventoryEntry(
                suggested_id="doc-d",
                file="scan.pdf",
                sha256=digest,
                size_bytes=100,
                page_count=1,
                native_text_pages=0,
                source_kind="scanned",
            )
        ],
    )

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "id": "scan",
                "file": "corpus/scan.pdf",
                "sha256": digest,
                "metadata": {"source_kind": "digital"},
                "expected": {
                    "document_type": "supplier_invoice",
                    "validation_status": "valid",
                    "fields": {},
                },
            }
        ],
    )

    report = audit_corpus(inventory_path, manifest_path)
    codes = {issue.code for issue in report.issues}

    assert report.errors == 1
    assert report.warnings == 4
    assert "source_kind_mismatch" in codes
    assert "no_expected_fields" in codes
    assert "supplier_not_recorded" in codes
    assert "layout_class_not_recorded" in codes
    assert "language_not_recorded" in codes


def test_audit_rejects_manifest_file_missing_from_inventory(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()

    inventory_path = tmp_path / "inventory.json"
    _write_inventory(inventory_path, corpus_root, [])

    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        [
            _complete_case(
                document_id="missing",
                file="corpus/missing.pdf",
                sha256="e" * 64,
            )
        ],
    )

    report = audit_corpus(inventory_path, manifest_path)

    assert report.errors == 1
    assert report.issues[0].code == "manifest_file_not_in_inventory"
