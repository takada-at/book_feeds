provider "google" {
  project     = var.project_name
  region      = var.region
}

resource "google_service_account" "default" {
  account_id   = "apub-bot-account"
  display_name = "ActivityPub Bot Service Account"
}

data "google_secret_manager_secret_version" "mongodb" {
  secret = "mongodb_password"
}

resource "google_secret_manager_secret_iam_binding" "binding" {
  project = data.google_secret_manager_secret_version.mongodb.project
  secret_id = data.google_secret_manager_secret_version.mongodb.secret
  role = "roles/secretmanager.secretAccessor"
  members = [
    "serviceAccount:${google_service_account.default.email}"
  ]
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
        value = "ap_bot_test"
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
  member = "serviceAccount:930396250237-compute@developer.gserviceaccount.com"
}