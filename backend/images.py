"""Where uploaded photos live: ./uploads in dev, a GCS bucket in prod."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from backend.api.config import Settings
from backend.models import new_id

log = logging.getLogger(__name__)


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


CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


class GcsImageStore(ImageStore):
    """Photos in a Cloud Storage bucket (private), as gs://bucket/<shop id>/<id>.<ext>.
    Credentials: the Cloud Run service account (ADC)."""

    def __init__(self, bucket: str, project: str = "", client=None):
        self.bucket = bucket
        self.project = project
        self._client = client

    def save(self, shop_id: str, data: bytes, ext: str) -> str:
        if self._client is None:
            from google.cloud import storage  # only needed in production

            self._client = storage.Client(project=self.project or None)
        ext = ext.lstrip(".").lower() or "bin"
        name = f"{shop_id}/{new_id()}.{ext}"
        self._client.bucket(self.bucket).blob(name).upload_from_string(
            data, content_type=CONTENT_TYPES.get(ext, "application/octet-stream"))
        return f"gs://{self.bucket}/{name}"


def get_image_store(settings: Settings) -> ImageStore:
    """GCS when GCS_BUCKET is set. Without it, photos go to ./uploads (on Cloud Run that folder
    is wiped on restart; the menu itself is in the store, so only the photo copies are lost)."""
    if settings.gcs_bucket.strip():
        return GcsImageStore(settings.gcs_bucket.strip(), settings.gcp_project_id)
    if settings.store_backend == "firestore":
        log.warning("GCS_BUCKET is empty: menu photos are kept only on this instance's disk")
    return LocalImageStore(settings.uploads_dir)
