terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.7"
    }
  }
  # Created by infra/bootstrap.
  backend "gcs" {
    bucket = "kampungcart-prod-tfstate"
    prefix = "main"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  # Billing Budgets and some IAM APIs need a quota project when called with user credentials.
  user_project_override = true
  billing_project       = var.project_id

  default_labels = {
    app        = "kampungcart"
    managed_by = "terraform"
  }
}

data "google_project" "this" {
  project_id = var.project_id
}
