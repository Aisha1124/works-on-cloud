# Secret containers only. Values are NEVER in Terraform (they would sit in plain text in the
# state file). Add them once by hand; see infra/README.md:
#   printf '%s' 'VALUE' | gcloud secrets versions add gemini-api-key --data-file=-

locals {
  secrets = {
    GEMINI_API_KEY = "gemini-api-key"
    OWNER_KEY      = "owner-key"
  }
}

resource "google_secret_manager_secret" "app" {
  for_each  = local.secrets
  secret_id = each.value
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# Only the runtime account can read them, and only these two.
resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = google_secret_manager_secret.app
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime.member
}
