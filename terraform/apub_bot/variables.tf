variable "project_name" {
  default = "peak-bit-229907"
}

variable "region" {
  default = "us-central1"
}

locals {
  root_path = "${path.module}/../../"
}
