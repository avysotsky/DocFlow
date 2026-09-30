import shutil
from pathlib import Path

import fitz
import pytest

from docflow_worker.corpus_inventory import build_corpus_inventory


def _create_pdf(path: Path, page_texts: list[str | None]) -> None:
    document = fitz.open()
    try:
        for page_text in page_texts:
            page = document.new_page()
            if page_text:
                page.insert_text((72, 72), page_text)
        document.save(path)
    finally:
        document.close()


def test_inventory_classifies_digital_scanned_and_mixed_pdfs(tmp_path: Path) -> None:
    _create_pdf(tmp_path / "digital.pdf", ["Supplier quotation"])
    _create_pdf(tmp_path / "scanned.pdf", [None])
    _create_pdf(tmp_path / "mixed.pdf", ["Native text", None])

    inventory = build_corpus_inventory(tmp_path)
    by_file = {document.file: document for document in inventory.documents}

    assert inventory.documents_total == 3
    assert inventory.unique_contents == 3
    assert inventory.duplicates == 0
    assert inventory.errors == 0

    assert by_file["digital.pdf"].page_count == 1
    assert by_file["digital.pdf"].native_text_pages == 1
    assert by_file["digital.pdf"].source_kind == "digital"

    assert by_file["scanned.pdf"].page_count == 1
    assert by_file["scanned.pdf"].native_text_pages == 0
    assert by_file["scanned.pdf"].source_kind == "scanned"

    assert by_file["mixed.pdf"].page_count == 2
    assert by_file["mixed.pdf"].native_text_pages == 1
    assert by_file["mixed.pdf"].source_kind == "mixed"


def test_inventory_detects_duplicate_pdf_contents(tmp_path: Path) -> None:
    original = tmp_path / "supplier-a.pdf"
    duplicate = tmp_path / "nested" / "supplier-a-copy.pdf"
    duplicate.parent.mkdir()

    _create_pdf(original, ["Same supplier document"])
    shutil.copyfile(original, duplicate)

    inventory = build_corpus_inventory(tmp_path)

    assert inventory.documents_total == 2
    assert inventory.unique_contents == 1
    assert inventory.duplicates == 1

    canonical_documents = [
        document for document in inventory.documents if document.duplicate_of is None
    ]
    duplicate_documents = [
        document for document in inventory.documents if document.duplicate_of is not None
    ]

    assert len(canonical_documents) == 1
    assert len(duplicate_documents) == 1

    canonical = canonical_documents[0]
    duplicate_entry = duplicate_documents[0]

    assert duplicate_entry.duplicate_of == canonical.suggested_id
    assert duplicate_entry.sha256 == canonical.sha256
    assert {canonical.file, duplicate_entry.file} == {
        "supplier-a.pdf",
        "nested/supplier-a-copy.pdf",
    }


def test_inventory_records_invalid_pdf_without_aborting(tmp_path: Path) -> None:
    _create_pdf(tmp_path / "good.pdf", ["Valid PDF"])
    (tmp_path / "broken.pdf").write_bytes(b"this is not a valid pdf")

    inventory = build_corpus_inventory(tmp_path)
    by_file = {document.file: document for document in inventory.documents}

    assert inventory.documents_total == 2
    assert inventory.errors == 1
    assert by_file["good.pdf"].error is None

    broken = by_file["broken.pdf"]
    assert broken.sha256
    assert broken.size_bytes > 0
    assert broken.page_count is None
    assert broken.native_text_pages is None
    assert broken.source_kind == "unknown"
    assert broken.error is not None


def test_inventory_ids_are_stable_for_same_path_and_content(tmp_path: Path) -> None:
    pdf_path = tmp_path / "supplier.pdf"
    _create_pdf(pdf_path, ["Stable document"])

    first = build_corpus_inventory(tmp_path)
    second = build_corpus_inventory(tmp_path)

    assert first.documents[0].suggested_id == second.documents[0].suggested_id
    assert first.documents[0].suggested_id.startswith("doc-")


def test_inventory_rejects_missing_or_non_directory_corpus(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_corpus_inventory(tmp_path / "missing")

    file_path = tmp_path / "not-a-directory"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        build_corpus_inventory(file_path)
