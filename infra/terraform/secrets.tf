# Secret containers only. Values are NEVER in Terraform (they would sit in plain text in the
# state file). Add them once by hand; see infra/README.md:
#   printf '%s' 'VALUE' | gcloud secrets versions add owner-key --data-file=-
#
# Gemini needs no secret: production uses Vertex AI with the runtime service account.

locals {
  # env var name -> secret id
  secrets = {
    OWNER_KEY     = "owner-key"     # backup key of the sample shop mak-kuih only
    SMTP_USER     = "smtp-user"     # Gmail address
    SMTP_PASSWORD = "smtp-password" # Gmail app password
  }
  # Which secrets the service reads. A referenced secret with no version makes the revision fail,
  # so the SMTP ones are attached only once smtp_enabled = true (after both have a value).
  attached_secrets = {
    for env, id in local.secrets : env => id
    if env == "OWNER_KEY" || var.smtp_enabled
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

# Only the runtime account can read them.
resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each  = google_secret_manager_secret.app
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.runtime.member
}
