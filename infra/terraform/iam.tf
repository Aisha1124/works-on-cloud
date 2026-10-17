# Four service accounts, each with only what it needs:
#   kampungcart-run   the Cloud Run service itself
#   gh-deployer       GitHub Actions on main: push image + roll out a new revision
#   gh-tf-plan        GitHub Actions on any branch/PR: read-only terraform plan
#   gh-terraform      GitHub Actions in the "production" environment only: terraform apply

# --- Runtime ---------------------------------------------------------------------------------

resource "google_service_account" "runtime" {
  account_id   = "kampungcart-run"
  display_name = "KampungCart Cloud Run runtime"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "runtime" {
  for_each = toset([
    "roles/datastore.user",  # Firestore read/write
    "roles/aiplatform.user", # Gemini via Vertex AI
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.runtime.member
}
# Secret access and the uploads bucket are granted on those resources (secrets.tf, data.tf).

# --- CI: deploy ------------------------------------------------------------------------------

resource "google_service_account" "deployer" {
  account_id   = "gh-deployer"
  display_name = "GitHub Actions: build and deploy"
  depends_on   = [google_project_service.apis]
}

resource "google_artifact_registry_repository_iam_member" "deployer_push" {
  location   = google_artifact_registry_repository.app.location
  repository = google_artifact_registry_repository.app.name
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

# run.developer: create revisions and shift traffic, but not change IAM on the service.
resource "google_project_iam_member" "deployer_run" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = google_service_account.deployer.member
}

# A new revision runs as kampungcart-run, so the deployer must be allowed to "act as" it.
resource "google_service_account_iam_member" "deployer_actas_runtime" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}

# --- CI: terraform ---------------------------------------------------------------------------

resource "google_service_account" "terraform" {
  account_id   = "gh-terraform"
  display_name = "GitHub Actions: terraform plan/apply"
  depends_on   = [google_project_service.apis]
}

# Terraform manages IAM, APIs, secrets, Run, storage, Firestore and monitoring, so it needs
# admin on those. This account can only be used from the GitHub "production" environment
# (apply, with a required reviewer) or for read-only plans; see wif.tf.
resource "google_project_iam_member" "terraform" {
  for_each = toset([
    "roles/editor",
    "roles/resourcemanager.projectIamAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.workloadIdentityPoolAdmin",
    "roles/secretmanager.admin",
    "roles/run.admin",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/artifactregistry.admin",
    "roles/monitoring.admin",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.terraform.member
}

# The budget lives on the billing account, not the project.
resource "google_billing_account_iam_member" "terraform_budget" {
  billing_account_id = var.billing_account
  role               = "roles/billing.costsManager"
  member             = google_service_account.terraform.member
}

# --- CI: terraform plan (read-only) ------------------------------------------------------------

resource "google_service_account" "tf_plan" {
  account_id   = "gh-tf-plan"
  display_name = "GitHub Actions: terraform plan (read-only)"
  depends_on   = [google_project_service.apis]
}

resource "google_project_iam_member" "tf_plan" {
  for_each = toset([
    "roles/viewer",
    "roles/iam.securityReviewer", # read IAM policies during refresh
    "roles/secretmanager.viewer", # secret metadata only, never values
    "roles/serviceusage.serviceUsageConsumer",
  ])
  project = var.project_id
  role    = each.value
  member  = google_service_account.tf_plan.member
}

resource "google_billing_account_iam_member" "tf_plan_budget" {
  billing_account_id = var.billing_account
  role               = "roles/billing.viewer"
  member             = google_service_account.tf_plan.member
}

# Plans take a state lock (a small object in the bucket), so plan needs write on objects there.
resource "google_storage_bucket_iam_member" "tf_plan_state" {
  bucket = "${var.project_id}-tfstate" # created by infra/bootstrap
  role   = "roles/storage.objectUser"
  member = google_service_account.tf_plan.member
}
