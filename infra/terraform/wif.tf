# Workload Identity Federation: GitHub Actions gets short-lived Google tokens through OIDC.
# No service-account keys exist anywhere.

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  depends_on                = [google_project_service.apis]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"        = "assertion.sub"
    "attribute.repository"  = "assertion.repository"
    "attribute.ref"         = "assertion.ref"
    "attribute.environment" = "assertion.environment"
    # "owner/repo@refs/heads/main": lets bindings target one branch of one repo.
    "attribute.repo_ref" = "assertion.repository + '@' + assertion.ref"
    # "production@refs/heads/main": environment AND branch, so apply access doesn't depend on
    # GitHub environment settings alone (a missing environment is auto-created unprotected).
    "attribute.env_ref" = "(has(assertion.environment) ? assertion.environment : 'none') + '@' + assertion.ref"
  }

  # Only tokens from this repo are accepted at all; every other GitHub repo is rejected here.
  attribute_condition = "assertion.repository == '${var.github_repo}'"
}

locals {
  wif_pool = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}"
}

# Deploys: only workflows running on main.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "${local.wif_pool}/attribute.repo_ref/${var.github_repo}@refs/heads/main"
}

# Terraform apply: only jobs in the GitHub "production" environment AND on main. GitHub's
# environment protection (required reviewer) adds the human approval on top.
resource "google_service_account_iam_member" "terraform_wif" {
  service_account_id = google_service_account.terraform.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "${local.wif_pool}/attribute.env_ref/production@refs/heads/main"
}

# Terraform plan (read-only): any workflow in the repo, e.g. PR plans.
resource "google_service_account_iam_member" "tf_plan_wif" {
  service_account_id = google_service_account.tf_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "${local.wif_pool}/attribute.repository/${var.github_repo}"
}
