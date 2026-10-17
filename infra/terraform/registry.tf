resource "google_artifact_registry_repository" "app" {
  repository_id = var.service_name
  location      = var.region
  format        = "DOCKER"
  description   = "KampungCart images. Tagged with the git SHA by CI."

  # Keep the 10 newest images (rollback targets); delete untagged/older ones after 7 days.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "604800s"
    }
  }

  depends_on = [google_project_service.apis]
}

locals {
  image_repo = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app.repository_id}"
}
