resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com", # WIF: GitHub -> short-lived SA tokens
    "sts.googleapis.com",            # WIF token exchange
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudbilling.googleapis.com", # IAM on the billing account (budget permissions)
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "aiplatform.googleapis.com", # Gemini through Vertex AI (service account, no API key)
  ])
  service            = each.value
  disable_on_destroy = false
}
