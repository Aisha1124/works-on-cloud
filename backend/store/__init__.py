from backend.api.config import Settings
from backend.store.base import Store
from backend.store.firestore import FirestoreStore
from backend.store.local_json import LocalJsonStore

__all__ = ["Store", "LocalJsonStore", "FirestoreStore", "get_store"]


def get_store(settings: Settings) -> Store:
    if settings.store_backend == "firestore":
        return FirestoreStore(settings.gcp_project_id, settings.firestore_database)
    return LocalJsonStore(settings.data_dir)
