variable "region" {
  type    = string
  default = "us-east-2"
  validation {
    condition     = var.region == "us-east-2"
    error_message = "Ce projet AWS utilise us-east-2."
  }
}

variable "ssh_allowed_cidrs" {
  type = set(string)
  validation {
    condition = length(var.ssh_allowed_cidrs) > 0 && alltrue([
      for cidr in var.ssh_allowed_cidrs : can(cidrnetmask(cidr)) && can(regex("/32$", cidr))
    ])
    error_message = "Fournir au moins une IPv4 /32 pour SSH ; aucun réseau ouvert à tous."
  }
}

variable "ssh_public_key" {
  type    = string
  default = ""
  validation {
    condition     = var.ssh_public_key == "" || can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+( .*)?$", trimspace(var.ssh_public_key)))
    error_message = "Fournir une clé publique SSH RSA ou Ed25519."
  }
}

variable "ssh_public_keys" {
  type    = list(string)
  default = []
  validation {
    condition     = length(var.ssh_public_keys) > 0 || trimspace(var.ssh_public_key) != ""
    error_message = "Fournir au moins une clé dans SSH_PUBLIC_KEYS ou SSH_PUBLIC_KEY."
  }
  validation {
    condition = alltrue([
      for key in var.ssh_public_keys : can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+( .*)?$", trimspace(key)))
    ])
    error_message = "Chaque clé SSH doit être une clé publique RSA ou Ed25519 sur une seule ligne."
  }
}

locals {
  ssh_public_keys = distinct(concat(
    trimspace(var.ssh_public_key) != "" ? [trimspace(var.ssh_public_key)] : [],
    [for key in var.ssh_public_keys : trimspace(key)]
  ))
}
