import hashlib
from pathlib import Path
from typing import Literal

import fitz
from pydantic import BaseModel, Field


SourceKind = Literal["digital", "scanned", "mixed", "unknown"]


class CorpusInventoryEntry(BaseModel):
    suggested_id: str
    file: str
    sha256: str
    size_bytes: int
    page_count: int | None = None
    native_text_pages: int | None = None
    source_kind: SourceKind = "unknown"
    duplicate_of: str | None = None
    error: str | None = None


class CorpusInventory(BaseModel):
    documents_total: int
    unique_contents: int
    duplicates: int
    errors: int
    documents: list[CorpusInventoryEntry] = Field(default_factory=list)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_stream:
        for chunk in iter(lambda: file_stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _suggested_id(relative_path: Path, digest: str) -> str:
    path_digest = hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()
    return f"doc-{digest[:12]}-{path_digest[:6]}"


def _inspect_pdf(path: Path) -> tuple[int, int, SourceKind]:
    with fitz.open(path) as document:
        page_count = document.page_count
        native_text_pages = sum(
            1
            for page in document
            if page.get_text("text").strip()
        )

    if page_count == 0:
        source_kind: SourceKind = "unknown"
    elif native_text_pages == 0:
        source_kind = "scanned"
    elif native_text_pages == page_count:
        source_kind = "digital"
    else:
        source_kind = "mixed"

    return page_count, native_text_pages, source_kind


def build_corpus_inventory(corpus_root: str | Path) -> CorpusInventory:
    root = Path(corpus_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Corpus path is not a directory: {root}")

    pdf_paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() == ".pdf"
        ),
        key=lambda path: path.relative_to(root).as_posix().lower(),
    )

    documents: list[CorpusInventoryEntry] = []
    first_id_by_digest: dict[str, str] = {}

    for path in pdf_paths:
        relative_path = path.relative_to(root)
        digest = _sha256_file(path)
        suggested_id = _suggested_id(relative_path, digest)
        duplicate_of = first_id_by_digest.get(digest)
        if duplicate_of is None:
            first_id_by_digest[digest] = suggested_id

        try:
            page_count, native_text_pages, source_kind = _inspect_pdf(path)
            error = None
        except Exception as exc:
            page_count = None
            native_text_pages = None
            source_kind = "unknown"
            error = f"{type(exc).__name__}: {exc}"

        documents.append(
            CorpusInventoryEntry(
                suggested_id=suggested_id,
                file=relative_path.as_posix(),
                sha256=digest,
                size_bytes=path.stat().st_size,
                page_count=page_count,
                native_text_pages=native_text_pages,
                source_kind=source_kind,
                duplicate_of=duplicate_of,
                error=error,
            )
        )

    return CorpusInventory(
        documents_total=len(documents),
        unique_contents=len(first_id_by_digest),
        duplicates=sum(document.duplicate_of is not None for document in documents),
        errors=sum(document.error is not None for document in documents),
        documents=documents,
    )
