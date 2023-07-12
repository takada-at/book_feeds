provider "google" {
  project     = var.project_name
  region      = var.region
}

resource "google_project_iam_member" "member" {
  project = var.project_name
  role = "roles/bigquery.jobUser"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_service_account" "default" {
  account_id   = "apub-bot-account"
  display_name = "ActivityPub Bot Service Account"
}

resource "google_secret_manager_secret_iam_member" "member" {
  secret_id = "mongodb_password"
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_secret_manager_secret_iam_member" "token" {
  secret_id = "apub_bot_secret_token"
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.default.email}"  
}

data "google_kms_key_ring" "default" {
  name     = "ap_key_ring"
  location = "global"
}

resource "google_kms_key_ring_iam_binding" "key_ring" {
  key_ring_id = data.google_kms_key_ring.default.id
  role        = "roles/cloudkms.cryptoOperator"

  members = [
    "serviceAccount:${google_service_account.default.email}"
  ]
}

resource "google_cloud_run_v2_service" "default" {
  name     = "apub-bot1"
  location = "us-central1"
  ingress = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.default.email
    containers {
      image = "us-central1-docker.pkg.dev/${var.project_name}/docker-repos/apub_bot"
      env {
        name = "PROJECT_NAME"
        value = var.project_name
      }
      env {
        name = "BASE_URL"
        value = "https://apub-bot1-46e33xglnq-uc.a.run.app/"
      }
      env {
        name = "BOT_ID"
        value = "bookbot"
      }
      env {
        name = "BOT_NAME"
        value = "bookbot"
      }
      env {
        name = "MONGODB_DATABASE"
        value = "ap_bot"
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_binding" "default" {
  location = google_cloud_run_v2_service.default.location
  name     = google_cloud_run_v2_service.default.name
  role     = "roles/run.invoker"
  members  = [
    "allUsers"
  ]
}

resource "google_cloud_run_v2_service_iam_member" "member" {
  project = google_cloud_run_v2_service.default.project
  location = google_cloud_run_v2_service.default.location
  name = google_cloud_run_v2_service.default.name
  role = "roles/run.developer"
  member = "serviceAccount:930396250237@cloudbuild.gserviceaccount.com"
}

resource "google_service_account_iam_member" "member" {
  service_account_id = google_service_account.default.name
  role = "roles/iam.serviceAccountUser"
  member = "serviceAccount:930396250237@cloudbuild.gserviceaccount.com"
}

data "archive_file" "book_post" {
  type        = "zip"
  source_dir  = "${local.root_path}book_post"
  output_path = "${local.root_path}/output/book_post.zip"
}

data "google_storage_bucket" "bucket" {
  name = "td-book-storage"
}

resource "google_storage_bucket_object" "book_post" {
  name   = "book_post.zip"
  bucket = "td-book-storage"
  source = data.archive_file.book_post.output_path
}

data "google_secret_manager_secret" "mongodb_password" {
  secret_id = "mongodb_password"
}

resource "google_secret_manager_secret_iam_member" "mongodb_password" {
  project = var.project_name
  secret_id = data.google_secret_manager_secret.mongodb_password.secret_id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.default.email}"
}

data "google_secret_manager_secret" "secret_token" {
  secret_id = "apub_bot_secret_token"
}

resource "google_secret_manager_secret_iam_member" "secret_token" {
  project = var.project_name
  secret_id = data.google_secret_manager_secret.secret_token.secret_id
  role = "roles/secretmanager.secretAccessor"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_cloudfunctions2_function" "book_post" {
  name = "book-post"
  location = var.region

  build_config {
    runtime = "python311"
    entry_point = "handle_request"
    source {
      storage_source {
        bucket = google_storage_bucket_object.book_post.bucket
        object = google_storage_bucket_object.book_post.name
      }
    }
  }

  service_config {
    max_instance_count  = 1
    max_instance_request_concurrency = 1
    service_account_email = google_service_account.default.email
    timeout_seconds     = 60
    available_memory    = "512M"
    secret_volumes {
      mount_path = "/etc/secrets"
      project_id = var.project_name
      secret     = data.google_secret_manager_secret.mongodb_password.secret_id
    }    
    secret_volumes {
      mount_path = "/etc/secrets_token"
      project_id = var.project_name
      secret     = data.google_secret_manager_secret.secret_token.secret_id
    }    
    environment_variables = {
        PROJECT_NAME = var.project_name
        MONGODB_DATABASE = "ap_bot"
        MONGODB_PASSWORD_PATH = "/etc/secrets/mongodb_password"
        SECRET_TOKEN_PATH = "/etc/secrets_token/apub_bot_secret_token"
        POST_URL = "${google_cloud_run_v2_service.default.uri}/hook"
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "book_post" {
  project = var.project_name
  name = google_cloudfunctions2_function.book_post.name
  location = google_cloudfunctions2_function.book_post.location
  role = "roles/run.invoker"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_bigquery_dataset_iam_member" "viewer" {
  dataset_id = "book_feed"
  role       = "roles/bigquery.dataViewer"
  member = "serviceAccount:${google_service_account.default.email}"
}

resource "google_storage_bucket_iam_member" "binding" {
  bucket  = data.google_storage_bucket.bucket.name
  member = "serviceAccount:${google_service_account.default.email}"
  role    = "roles/storage.objectViewer"
}

resource "google_cloud_scheduler_job" "post1" {
  name             = "book-post-schedule1"
  description      = "book-post-schedule1"
  schedule         = "0 9 * * *"
  time_zone        = "Asia/Tokyo"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.book_post.service_config[0].uri
    body        = base64encode("{\"mode\": \"today\"}")
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.default.email
      audience = google_cloudfunctions2_function.book_post.service_config[0].uri
    }
  }
}

resource "google_cloud_scheduler_job" "post2" {
  name             = "book-post-schedule2"
  description      = "book-post-schedule2"
  schedule         = "14 9,12,17,20,22 * * *"
  time_zone        = "Asia/Tokyo"

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.book_post.service_config[0].uri
    body        = base64encode("{\"mode\": \"random\"}")
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = google_service_account.default.email
      audience = google_cloudfunctions2_function.book_post.service_config[0].uri
    }
  }
}