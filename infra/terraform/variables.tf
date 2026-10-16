variable "project_id" {
  type    = string
  default = "kampungcart-prod"
}

variable "region" {
  type    = string
  default = "asia-southeast1"
}

variable "service_name" {
  type    = string
  default = "kampungcart"
}

variable "github_repo" {
  description = "owner/name of the GitHub repo allowed to deploy via Workload Identity Federation."
  type        = string
  default     = "Aisha1124/works-on-cloud"
}

variable "billing_account" {
  description = "Billing account id (for the budget alert)."
  type        = string
}

variable "alert_email" {
  description = "Where uptime and budget alerts go."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget, in the billing account's currency. Alerts at 50%, 90%, 100%."
  type        = number
  default     = 50
}

variable "gemini_model" {
  type    = string
  default = "gemini-3.8-flash"
}

variable "store_backend" {
  description = "local until FirestoreStore/GcsImageStore are implemented, then firestore."
  type        = string
  default     = "local"
  validation {
    condition     = contains(["local", "firestore"], var.store_backend)
    error_message = "store_backend must be local or firestore."
  }
}

variable "max_instances" {
  description = "Must stay 1 while store_backend = local (data lives on the instance)."
  type        = number
  default     = 1
}

variable "min_instances" {
  type    = number
  default = 1
}

variable "custom_base_url" {
  description = "Set if a custom domain is mapped. Default: the deterministic run.app URL."
  type        = string
  default     = ""
}
