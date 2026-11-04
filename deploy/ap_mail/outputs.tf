output "checker_url" { value = google_cloud_run_v2_service.checker.uri }
output "processor_url" { value = google_cloud_run_v2_service.processor.uri }
output "queue" { value = google_cloud_tasks_queue.mail.id }
output "schedule" { value = google_cloud_scheduler_job.poll.id }
output "gmail_secret" { value = google_secret_manager_secret.gmail.id }
output "schedule_caller" { value = google_service_account.principal["schedule"].email }
output "task_caller" { value = google_service_account.principal["tasks"].email }
