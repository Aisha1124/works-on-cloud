# Persistent data, used once STORE_BACKEND=firestore (FirestoreStore + GcsImageStore).

resource "google_firestore_database" "main" {
  name                              = "(default)"
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED" # 7-day recovery window
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  deletion_policy                   = "ABANDON" # `terraform destroy` never deletes the data
  depends_on                        = [google_project_service.apis]
}

resource "google_storage_bucket" "uploads" {
  name     = "${var.project_id}-uploads"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced" # photos are served through the app, never public

  versioning {
    enabled = true
  }
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }
  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "runtime_uploads" {
  bucket = google_storage_bucket.uploads.name
  role   = "roles/storage.objectUser"
  member = google_service_account.runtime.member
}
