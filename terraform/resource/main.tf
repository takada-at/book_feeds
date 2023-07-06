provider "google" {
  project     = var.project_name
  region      = var.region
}

resource "google_service_account" "default" {
  account_id   = "book-service-account"
  display_name = "Book Service Account"
}

resource "google_storage_bucket" "data_storage" {
  name     = "td-book-storage"
  location = var.region
}

resource "google_storage_bucket_iam_binding" "binding" {
  bucket  = google_storage_bucket.data_storage.name
  members = [
    "serviceAccount:${google_service_account.default.email}"
  ]
  role    = "roles/storage.objectAdmin"
}

data "archive_file" "sample_function" {
  type        = "zip"
  source_dir  = "${local.root_path}fetch_feeds"
  output_path = "${local.root_path}/output/fetch_feeds.zip"
}

resource "google_storage_bucket_object" "object" {
  name   = "fetch_feeds.zip"
  bucket = google_storage_bucket.data_storage.name
  source = "fetch_feeds.zip"
}

resource "google_cloudfunctions2_function" "function" {
  name = "fetch-feeds"
  location = var.region

  build_config {
    runtime = "python311"
    entry_point = "handle_request"
    environment_variables = {
        BASE_URL = "https://www.hanmoto.com/ci/bd/search/sdate/today/edate/+1month/order/desc/vw/rss20"
        BUCKET = google_storage_bucket.data_storage.name
    }
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
    timeout_seconds     = 120
  }
}

resource "google_cloud_run_service_iam_binding" "binding" {
  project = var.project_name
  service = google_cloudfunctions2_function.function.name
  location = google_cloudfunctions2_function.function.location
  role = "roles/run.invoker"
  members = [
    "serviceAccount:${google_service_account.default.email}"
  ]
}
