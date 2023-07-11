variable "project_name" {
}

variable "region" {
  default = "us-central1"
}

locals {
  root_path = "${path.module}/../../"
}
