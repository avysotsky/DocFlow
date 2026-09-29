from pathlib import Path


class LocalStorageReader:
    """Resolves DocFlow local-storage keys without allowing path traversal."""

    def __init__(self, root_path: str | Path) -> None:
        self._root_path = Path(root_path).expanduser().resolve()

    @property
    def root_path(self) -> Path:
        return self._root_path

    def resolve(self, storage_key: str) -> Path:
        if not storage_key or not storage_key.strip():
            raise ValueError("Storage key is required.")

        candidate = (self._root_path / storage_key).resolve()

        try:
            candidate.relative_to(self._root_path)
        except ValueError as exc:
            raise ValueError("Storage key resolves outside the storage root.") from exc

        if not candidate.is_file():
            raise FileNotFoundError(f"Stored document was not found: {storage_key}")

        return candidate
