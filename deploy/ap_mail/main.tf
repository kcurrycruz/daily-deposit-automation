terraform {
  required_version = ">= 1.10, < 1.18"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "8.10.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "8.10.0"
    }
  }
}
provider "google" {
  project = var.project_id
  region  = var.region
}
provider "google-beta" {
  project = var.project_id
  region  = var.region
}
locals {
  checker_audience   = "https://ap-mail-checker.${var.project_id}.internal"
  processor_audience = "https://ap-mail-processor.${var.project_id}.internal"
  common_env = {
    AP_MAIL_SUPABASE_URL  = var.supabase_url
    AP_MAIL_WORKSPACE_ID  = var.workspace_id
    AP_MAIL_CONNECTION_ID = var.connection_id
    AP_MAIL_BUCKET        = var.private_bucket
    AP_MAIL_GMAIL_SECRET  = google_secret_manager_secret.gmail.id
    PYTHONUNBUFFERED      = "1"
  }
}
resource "google_project_service" "api" {
  for_each           = toset(["run.googleapis.com", "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com", "secretmanager.googleapis.com", "artifactregistry.googleapis.com", "iamcredentials.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
resource "google_service_account" "principal" {
  for_each     = toset(["checker", "processor", "schedule", "tasks"])
  account_id   = "${var.name_prefix}-${each.key}"
  display_name = "AP mail ${each.key}"
}
resource "google_secret_manager_secret" "gmail" {
  secret_id = var.gmail_secret_id
  replication {
    auto {}
  }
  lifecycle { prevent_destroy = true }
  depends_on = [google_project_service.api]
}
data "google_secret_manager_secret" "database" {
  secret_id = var.supabase_key_secret_id
}
resource "google_secret_manager_secret_iam_member" "gmail_read" {
  for_each  = toset(["checker", "processor"])
  secret_id = google_secret_manager_secret.gmail.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.principal[each.key].email}"
}
resource "google_secret_manager_secret_iam_member" "database_read" {
  for_each  = toset(["checker", "processor"])
  secret_id = data.google_secret_manager_secret.database.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.principal[each.key].email}"
}
resource "google_secret_manager_secret_iam_member" "owner_authorize" {
  secret_id = google_secret_manager_secret.gmail.id
  role      = "roles/secretmanager.secretVersionAdder"
  member    = var.owner_member
}
resource "google_cloud_tasks_queue" "mail" {
  name          = "${var.name_prefix}-pdf"
  location      = var.region
  desired_state = "PAUSED"
  rate_limits {
    max_concurrent_dispatches = 1
    max_dispatches_per_second = 1
  }
  retry_config {
    max_attempts       = 5
    max_retry_duration = "1800s"
    min_backoff        = "10s"
    max_backoff        = "60s"
    max_doublings      = 2
  }
  depends_on = [google_project_service.api]
}
resource "google_project_iam_custom_role" "dispatch" {
  role_id     = "${replace(var.name_prefix, "-", "_")}_dispatch"
  title       = "AP mail task dispatch"
  permissions = ["cloudtasks.tasks.create", "cloudtasks.tasks.get", "cloudtasks.queues.get"]
}
resource "google_cloud_tasks_queue_iam_member" "dispatch" {
  name     = google_cloud_tasks_queue.mail.name
  location = var.region
  role     = google_project_iam_custom_role.dispatch.name
  member   = "serviceAccount:${google_service_account.principal["checker"].email}"
}
resource "google_service_account_iam_member" "checker_act_as" {
  service_account_id = google_service_account.principal["tasks"].name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.principal["checker"].email}"
}
resource "google_project_service_identity" "tasks" {
  provider   = google-beta
  project    = var.project_id
  service    = "cloudtasks.googleapis.com"
  depends_on = [google_project_service.api]
}
resource "google_project_service_identity" "scheduler" {
  provider   = google-beta
  project    = var.project_id
  service    = "cloudscheduler.googleapis.com"
  depends_on = [google_project_service.api]
}
resource "google_service_account_iam_member" "task_token" {
  service_account_id = google_service_account.principal["tasks"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_project_service_identity.tasks.email}"
}
resource "google_service_account_iam_member" "schedule_token" {
  service_account_id = google_service_account.principal["schedule"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${google_project_service_identity.scheduler.email}"
}
resource "google_cloud_run_v2_service" "processor" {
  name                = "${var.name_prefix}-processor"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = true
  custom_audiences    = [local.processor_audience]
  template {
    service_account                  = google_service_account.principal["processor"].email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    timeout                          = "600s"
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.image_digest
      resources {
        limits   = { "cpu" = "2", "memory" = "4Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common_env, { AP_MAIL_ROLE = "processor", AP_MAIL_AUDIENCE = local.processor_audience, AP_MAIL_CALLER = google_service_account.principal["tasks"].email })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "AP_MAIL_SUPABASE_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.database.id
            version = var.supabase_key_secret_version
          }
        }
      }
    }
  }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.gmail_read, google_secret_manager_secret_iam_member.database_read]
}
resource "google_cloud_run_v2_service" "checker" {
  name                = "${var.name_prefix}-checker"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = true
  custom_audiences    = [local.checker_audience]
  template {
    service_account                  = google_service_account.principal["checker"].email
    execution_environment            = "EXECUTION_ENVIRONMENT_GEN2"
    timeout                          = "180s"
    max_instance_request_concurrency = 1
    scaling {
      min_instance_count = 0
      max_instance_count = 1
    }
    containers {
      image = var.image_digest
      resources {
        limits   = { "cpu" = "1", "memory" = "1Gi" }
        cpu_idle = true
      }
      dynamic "env" {
        for_each = merge(local.common_env, { AP_MAIL_ROLE = "checker", AP_MAIL_AUDIENCE = local.checker_audience,
          AP_MAIL_CALLER        = google_service_account.principal["schedule"].email, AP_MAIL_QUEUE = google_cloud_tasks_queue.mail.id,
          AP_MAIL_PROCESSOR_URL = "${google_cloud_run_v2_service.processor.uri}/process", AP_MAIL_TASK_CALLER = google_service_account.principal["tasks"].email,
        AP_MAIL_PROCESSOR_AUDIENCE = local.processor_audience })
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "AP_MAIL_SUPABASE_KEY"
        value_source {
          secret_key_ref {
            secret  = data.google_secret_manager_secret.database.id
            version = var.supabase_key_secret_version
          }
        }
      }
    }
  }
  depends_on = [google_project_service.api, google_secret_manager_secret_iam_member.gmail_read, google_secret_manager_secret_iam_member.database_read]
}
resource "google_cloud_run_v2_service_iam_member" "processor_invoker" {
  name     = google_cloud_run_v2_service.processor.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.principal["tasks"].email}"
}
resource "google_cloud_run_v2_service_iam_member" "checker_invoker" {
  name     = google_cloud_run_v2_service.checker.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.principal["schedule"].email}"
}
resource "google_cloud_scheduler_job" "poll" {
  name             = "${var.name_prefix}-poll"
  region           = var.region
  schedule         = "*/5 * * * *"
  time_zone        = "Etc/UTC"
  paused           = true
  attempt_deadline = "180s"
  http_target {
    http_method = "POST"
    uri         = "${google_cloud_run_v2_service.checker.uri}/poll"
    body        = base64encode("{}")
    headers     = { "Content-Type" = "application/json" }
    oidc_token {
      service_account_email = google_service_account.principal["schedule"].email
      audience              = local.checker_audience
    }
  }
  depends_on = [google_service_account_iam_member.schedule_token, google_cloud_run_v2_service_iam_member.checker_invoker]
}
