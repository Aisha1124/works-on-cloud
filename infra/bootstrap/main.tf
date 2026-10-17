# Bootstrap: the only Terraform run by hand, once per project.
#
# Creates the GCS bucket that stores the state of infra/terraform, and enables the APIs that
# Terraform itself needs. Starts with local state, then moves its own state into the bucket
# (see infra/README.md, "Bootstrap").

terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.7"
    }
  }
  # Commented out for the very first apply (the bucket doesn't exist yet), then enabled and
  # migrated with `terraform init -migrate-state`.
  backend "gcs" {
    bucket = "kampungcart-prod-tfstate"
    prefix = "bootstrap"
  }
}

variable "project_id" {
  type    = string
  default = "kampungcart-prod"
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# APIs Terraform needs before it can manage anything else. The rest are in infra/terraform.
resource "google_project_service" "base" {
  for_each = toset([
    "serviceusage.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "tfstate" {
  name     = "${var.project_id}-tfstate"
  location = var.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Every state write is kept, so a bad apply can be rolled back to an earlier state file.
  versioning {
    enabled = true
  }
  lifecycle_rule {
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  lifecycle {
    prevent_destroy = true
  }

  labels     = { app = "kampungcart", managed_by = "terraform" }
  depends_on = [google_project_service.base]
}

output "state_bucket" {
  value = google_storage_bucket.tfstate.name
}
