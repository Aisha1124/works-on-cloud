# Values the GitHub workflows need (set them as repository variables, see infra/README.md).

output "service_url" {
  value = google_cloud_run_v2_service.app.uri
}

output "base_url" {
  value = local.base_url
}

output "image_repo" {
  value = local.image_repo
}

output "wif_provider" {
  description = "GitHub variable WIF_PROVIDER"
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "GitHub variable DEPLOYER_SA"
  value       = google_service_account.deployer.email
}

output "terraform_service_account" {
  description = "GitHub variable TERRAFORM_SA"
  value       = google_service_account.terraform.email
}

output "tf_plan_service_account" {
  description = "GitHub variable TF_PLAN_SA"
  value       = google_service_account.tf_plan.email
}

output "runtime_service_account" {
  value = google_service_account.runtime.email
}
