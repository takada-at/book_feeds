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
    containers {
      image = "us-central1-docker.pkg.dev/${var.project_name}/docker-repos/apub_bot"
      env {
        name = "PROJECT_NAME"
        value = var.project_name
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