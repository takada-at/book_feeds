provider "google" {
  project     = var.project_name
  region      = var.region
}

terraform {
  backend "gcs" {
    bucket = "td-book-storage"
    prefix  = "terraform/resource/state"
  }
}

resource "google_service_account" "default" {
  account_id   = "book-service-account"
  display_name = "Book Service Account"
}

resource "google_project_iam_member" "bigquery" {
  project = var.project_name
  role = "roles/bigquery.jobUser"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_storage_bucket" "data_storage" {
  name     = "td-book-storage"
  location = var.region
  lifecycle_rule {
    condition {
      age = 50
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "member" {
  bucket  = google_storage_bucket.data_storage.name
  member = "serviceAccount:${google_service_account.default.email}"
  role    = "roles/storage.objectAdmin"
}

resource "google_storage_bucket_iam_member" "member2" {
  bucket  = google_storage_bucket.data_storage.name
  member = "serviceAccount:${google_service_account.default.email}"
  role    = "roles/storage.legacyBucketReader"
}

data "archive_file" "sample_function" {
  type        = "zip"
  source_dir  = "${local.root_path}fetch_book_feeds"
  output_path = "${local.root_path}/output/fetch_book_feeds.zip"
}

resource "google_storage_bucket_object" "object" {
  name   = "fetch_book_feeds.zip"
  bucket = google_storage_bucket.data_storage.name
  source = data.archive_file.sample_function.output_path

}

resource "google_cloudfunctions2_function" "function" {
  name = "fetch-book-feeds"
  location = var.region

  build_config {
    runtime = "python311"
    entry_point = "handle_request"
    source {
      storage_source {
        bucket = google_storage_bucket.data_storage.name
        object = google_storage_bucket_object.object.name
      }
    }
  }

  service_config {
    max_instance_count  = 1
    max_instance_request_concurrency = 1
    service_account_email = google_service_account.default.email
    timeout_seconds     = 1200
    environment_variables = {
        PROJECT_NAME = var.project_name
        BUCKET_NAME = google_storage_bucket.data_storage.name
    }
  }
}

resource "google_cloud_run_service_iam_member" "member" {
  project = var.project_name
  service = google_cloudfunctions2_function.function.name
  location = google_cloudfunctions2_function.function.location
  role = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_cloud_scheduler_job" "job1" {
  for_each = {
    1 = {
      schedule = "14 0 * * *"
      days = 7
    }
    2 = {
      schedule = "24 0 * * *"
      days = 14
    }
    3 = {
      schedule = "34 0 * * *"
      days = 30
    }
    4 = {
      schedule = "44 0 * * *"
      days = 60
    }
  }
  name             = "fetch-book-feeds-daily${each.key}"
  description      = "fetch-book-feeds-daily${each.key}"
  schedule         = each.value.schedule
  time_zone        = "Asia/Tokyo"
  attempt_deadline = "1600s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.function.service_config[0].uri
    body        = base64encode("{\"days\": ${each.value.days}}")
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.default.email
      audience = google_cloudfunctions2_function.function.service_config[0].uri
    }
  }
}

resource "google_bigquery_dataset" "dataset" {
  dataset_id                  = "book_feed"
  location                    = "US"
}

resource google_bigquery_table table {
  dataset_id = google_bigquery_dataset.dataset.dataset_id
  deletion_protection=false
  table_id = "external_new_books"
  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    compression = "GZIP"
    autodetect    = true
    schema = file("${local.root_path}/terraform/scripts/new_books.json")
    hive_partitioning_options {
      mode = "CUSTOM"
      source_uri_prefix = "gs://${google_storage_bucket.data_storage.name}/new_books/{date:DATE}/"
      require_partition_filter = false
    }
    source_uris = ["gs://${google_storage_bucket.data_storage.name}/new_books/*"]
  }
}

resource google_bigquery_table table2 {
  dataset_id = google_bigquery_dataset.dataset.dataset_id
  deletion_protection = false
  table_id = "external_categorized"
  external_data_configuration {
    source_format = "NEWLINE_DELIMITED_JSON"
    compression = "GZIP"
    autodetect    = true
    schema = file("${local.root_path}/terraform/scripts/categorized.json")
    hive_partitioning_options {
      mode = "CUSTOM"
      source_uri_prefix = "gs://${google_storage_bucket.data_storage.name}/categorized/{date:DATE}/"
      require_partition_filter = false
    }
    source_uris = ["gs://${google_storage_bucket.data_storage.name}/categorized/*"]
  }
}

data "archive_file" "categorize" {
  type        = "zip"
  source_dir  = "${local.root_path}categorize"
  output_path = "${local.root_path}/output/categorize.zip"
}

resource "google_storage_bucket_object" "categorize" {
  name   = "categorize.zip"
  bucket = google_storage_bucket.data_storage.name
  source = data.archive_file.categorize.output_path

}

resource "google_cloudfunctions2_function" "categorize" {
  name = "categorize-book-feeds"
  location = var.region

  build_config {
    runtime = "python311"
    entry_point = "handle_request"
    source {
      storage_source {
        bucket = google_storage_bucket.data_storage.name
        object = google_storage_bucket_object.categorize.name
      }
    }
  }


  service_config {
    max_instance_count  = 1
    max_instance_request_concurrency = 1
    timeout_seconds     = 1200
    available_memory    = "512M"
    service_account_email = google_service_account.default.email
    secret_volumes {
      mount_path = "/etc/secrets"
      project_id = var.project_name
      secret     = data.google_secret_manager_secret.openai.secret_id
    }    
    environment_variables = {
        PROJECT_NAME = var.project_name
        SECRET_KEY_PATH = "/etc/secrets/openai_api_key"
        BUCKET_NAME = google_storage_bucket.data_storage.name
    }
  }
}

resource "google_cloud_run_service_iam_member" "categorize" {
  project = var.project_name
  service = google_cloudfunctions2_function.categorize.name
  location = google_cloudfunctions2_function.categorize.location
  role = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_bigquery_table_iam_member" "member" {
  project = google_bigquery_table.table.project
  dataset_id = google_bigquery_table.table.dataset_id
  table_id = google_bigquery_table.table.table_id
  role = "roles/bigquery.dataViewer"
  member = "serviceAccount:${google_service_account.default.email}"
}

data "google_secret_manager_secret" "openai" {
  secret_id = "openai_api_key"
}

resource "google_secret_manager_secret_iam_member" "member" {
  project = var.project_name
  secret_id = data.google_secret_manager_secret.openai.secret_id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_cloud_scheduler_job" "job_categorize1" {
  for_each = {
    1 = {
      schedule = "40 0 * * *"
      days = 7
    }
    2 = {
      schedule = "50 0 * * *"
      days = 14
    }
    3 = {
      schedule = "0 1 * * *"
      days = 30
    }
    4 = {
      schedule = "10 1 * * *"
      days = 60
    }
  }
  name             = "categorize-book-feeds-daily${each.key}"
  description      = "categorize-book-feeds-daily${each.key}"
  schedule         = each.value.schedule
  time_zone        = "Asia/Tokyo"
  attempt_deadline = "1600s"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.categorize.service_config[0].uri
    body        = base64encode("{\"days\": ${each.value.days}}")
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.default.email
      audience = google_cloudfunctions2_function.categorize.service_config[0].uri
    }
  }
}
