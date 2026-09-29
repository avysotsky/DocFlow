from pathlib import Path

import pytest

from docflow_worker.storage import LocalStorageReader


def test_resolves_existing_file_inside_storage(tmp_path: Path) -> None:
    stored_file = tmp_path / "2026" / "09" / "document.pdf"
    stored_file.parent.mkdir(parents=True)
    stored_file.write_bytes(b"%PDF-test")

    reader = LocalStorageReader(tmp_path)

    assert reader.resolve("2026/09/document.pdf") == stored_file.resolve()


def test_rejects_path_outside_storage(tmp_path: Path) -> None:
    reader = LocalStorageReader(tmp_path)

    with pytest.raises(ValueError):
        reader.resolve("../outside.pdf")
