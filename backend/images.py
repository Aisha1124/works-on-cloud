"""Where uploaded photos live: ./uploads in dev, a GCS bucket in prod."""

from abc import ABC, abstractmethod
from pathlib import Path

from backend.api.config import Settings
from backend.models import new_id


class ImageStore(ABC):
    @abstractmethod
    def save(self, shop_id: str, data: bytes, ext: str) -> str:
        """Store one image and return its path/URI."""


class LocalImageStore(ImageStore):
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, shop_id: str, data: bytes, ext: str) -> str:
        folder = self.root / shop_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{new_id()}.{ext.lstrip('.').lower() or 'bin'}"
        path.write_bytes(data)
        return path.relative_to(self.root.parent).as_posix()


class GcsImageStore(ImageStore):
    def __init__(self, bucket: str):
        self.bucket = bucket

    def save(self, shop_id: str, data: bytes, ext: str) -> str:
        raise NotImplementedError("GcsImageStore is not implemented yet. Use STORE_BACKEND=local.")


def get_image_store(settings: Settings) -> ImageStore:
    if settings.store_backend == "firestore":
        return GcsImageStore(settings.gcs_bucket)
    return LocalImageStore(settings.uploads_dir)
