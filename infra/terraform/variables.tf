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

variable "gemini_location" {
  description = "Vertex AI location. The Gemini Interactions API is served from global only."
  type        = string
  default     = "global"
}

variable "store_backend" {
  description = "firestore in production (data survives deploys, shared by all instances)."
  type        = string
  default     = "firestore"
  validation {
    condition     = contains(["local", "firestore"], var.store_backend)
    error_message = "store_backend must be local or firestore."
  }
}

variable "max_instances" {
  description = "Cost cap. Only 1 is safe with store_backend = local."
  type        = number
  default     = 10
}

variable "min_instances" {
  description = "1 keeps an instance warm: no cold start, and the 5-minute background jobs keep running."
  type        = number
  default     = 1
}

variable "custom_base_url" {
  description = "Set if a custom domain is mapped. Default: the deterministic run.app URL."
  type        = string
  default     = ""
}

variable "admin_email" {
  description = "Gets 'report this shop' messages; shown on /privacy. Default: alert_email."
  type        = string
  default     = ""
}

variable "sample_owner_email" {
  description = "Optional owner email of the sample shop mak-kuih (gets its order emails)."
  type        = string
  default     = ""
}

variable "smtp_enabled" {
  description = "Attach the smtp-user / smtp-password secrets. Turn on only after both have a value."
  type        = bool
  default     = false
}
