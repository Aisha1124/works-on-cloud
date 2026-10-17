locals {
  # Cloud Run URLs are deterministic, so BASE_URL can be set on the service itself without a
  # dependency cycle. The MCP server only accepts this host; the UCP profile advertises it.
  run_url  = "https://${var.service_name}-${data.google_project.this.number}.${var.region}.run.app"
  base_url = var.custom_base_url != "" ? var.custom_base_url : local.run_url
}

resource "google_cloud_run_v2_service" "app" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = true

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "120s"
    max_instance_request_concurrency = 40

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      # Only the first image. After that CI owns the image (see lifecycle below).
      image = "${local.image_repo}/app:initial"

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
        # CPU stays allocated between requests: risk explanations run as background tasks
        # after the response is sent and would stall with throttled CPU.
        cpu_idle          = false
        startup_cpu_boost = true
      }

      env {
        name  = "GEMINI_MODEL"
        value = var.gemini_model
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      env {
        name  = "GEMINI_LOCATION"
        value = var.gemini_location
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "BASE_URL"
        value = local.base_url
      }
      env {
        name  = "STORE_BACKEND"
        value = var.store_backend
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.uploads.name
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = google_firestore_database.main.name
      }
      env {
        name  = "ADMIN_EMAIL"
        value = var.admin_email != "" ? var.admin_email : var.alert_email
      }
      env {
        name  = "SAMPLE_OWNER_EMAIL"
        value = var.sample_owner_email
      }
      env {
        name  = "EMAIL_PROVIDER"
        value = "smtp"
      }
      env {
        name  = "SMTP_HOST"
        value = "smtp.gmail.com"
      }
      env {
        name  = "SMTP_PORT"
        value = "587"
      }

      dynamic "env" {
        for_each = local.attached_secrets
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.app[env.key].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = "/api/health"
        }
        period_seconds    = 3
        timeout_seconds   = 2
        failure_threshold = 20
      }
      liveness_probe {
        http_get {
          path = "/api/health"
        }
        period_seconds    = 30
        timeout_seconds   = 5
        failure_threshold = 3
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  lifecycle {
    # CI deploys new images and may pin traffic to an older revision on rollback. Terraform
    # must not undo either, so these fields are owned by the pipeline, not by Terraform.
    ignore_changes = [
      client,
      client_version,
      template[0].containers[0].image,
      template[0].revision,
      template[0].labels,
      template[0].annotations,
      traffic,
    ]
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.runtime,
    google_project_iam_member.runtime,
  ]
}

# Public: AI agents and shoppers call it without Google auth. Owner routes are protected in the
# app by X-Owner-Key.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.app.name
  location = google_cloud_run_v2_service.app.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
