"""Where menu photos go: ./uploads, or a Cloud Storage bucket when GCS_BUCKET is set."""

from backend.api.config import Settings
from backend.images import GcsImageStore, LocalImageStore, get_image_store


class FakeBlob:
    def __init__(self, sink, name):
        self.sink, self.name = sink, name

    def upload_from_string(self, data, content_type):
        self.sink.append((self.name, data, content_type))


class FakeBucket:
    def __init__(self, sink, name):
        self.sink, self.name = sink, name

    def blob(self, name):
        return FakeBlob(self.sink, f"{self.name}/{name}")


class FakeGcs:
    def __init__(self):
        self.uploads = []

    def bucket(self, name):
        return FakeBucket(self.uploads, name)


def test_gcs_store_uploads_with_a_content_type():
    gcs = FakeGcs()
    path = GcsImageStore("kc-photos", client=gcs).save("shop1", b"\xff\xd8jpeg", "jpg")
    (name, data, ctype), = gcs.uploads
    assert path == f"gs://{name}" and name.startswith("kc-photos/shop1/") and name.endswith(".jpg")
    assert data == b"\xff\xd8jpeg" and ctype == "image/jpeg"


def test_bucket_setting_picks_the_store(tmp_path):
    assert isinstance(get_image_store(Settings(_env_file=None, gcs_bucket="b")), GcsImageStore)
    # Firestore without a bucket still works (photos on local disk), instead of failing.
    local = get_image_store(Settings(_env_file=None, store_backend="firestore",
                                     uploads_dir=tmp_path / "up"))
    assert isinstance(local, LocalImageStore)
    assert local.save("s", b"x", "jpg").startswith("up/s/")
