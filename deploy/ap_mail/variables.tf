variable "project_id" {
  type        = string
  description = "Explicit Google Cloud project ID; no production default."
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,62}$", var.project_id))
    error_message = "Supply the approved Google Cloud project ID."
  }
}
variable "region" { type = string }
variable "workspace_id" {
  type = string
  validation {
    condition     = can(regex("^[a-f0-9-]{36}$", var.workspace_id))
    error_message = "Supply the approved AP workspace UUID."
  }
}
variable "connection_id" { type = string }
variable "private_bucket" { type = string }
variable "supabase_url" {
  type = string
  validation {
    condition     = can(regex("^https://[a-z0-9.-]+$", var.supabase_url))
    error_message = "Use the approved HTTPS Supabase origin only."
  }
}
variable "supabase_key_secret_id" { type = string }
variable "supabase_key_secret_version" {
  type = string
  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.supabase_key_secret_version))
    error_message = "Pin the existing server key's Secret Manager version number."
  }
}
variable "gmail_secret_id" { type = string }
variable "owner_member" {
  type = string
  validation {
    condition     = can(regex("^(user|serviceAccount):[^ ]+@[^ ]+$", var.owner_member))
    error_message = "Name the specific owner principal allowed to authorize Gmail."
  }
}
variable "image_digest" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9.-]+/[A-Za-z0-9/_-]+@sha256:[a-f0-9]{64}$", var.image_digest))
    error_message = "Use an immutable approved Artifact Registry image digest."
  }
}
variable "name_prefix" {
  type    = string
  default = "ap-mail"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{3,11}$", var.name_prefix))
    error_message = "Use a short service account-safe prefix."
  }
}
