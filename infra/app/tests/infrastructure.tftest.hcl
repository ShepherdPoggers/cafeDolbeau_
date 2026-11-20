mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
  mock_data "aws_ami" {
    defaults = {
      id = "ami-0123456789abcdef0"
    }
  }
}

variables {
  ssh_allowed_cidrs = ["203.0.113.10/32"]
  ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKeyOnly"
}

run "ubuntu_small_encrypted_disk" {
  command = plan
  assert {
    condition     = aws_instance.main.instance_type == "t3.small"
    error_message = "L'instance doit rester une t3.small."
  }
  assert {
    condition     = aws_instance.main.root_block_device[0].volume_size == 30 && aws_instance.main.root_block_device[0].encrypted && aws_instance.main.root_block_device[0].volume_type == "gp3"
    error_message = "Le disque doit être un gp3 chiffré de 30 Gio."
  }
  assert {
    condition     = aws_instance.main.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 est obligatoire."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.http.from_port == 80 && aws_vpc_security_group_ingress_rule.http.to_port == 80
    error_message = "Seul HTTP doit être ouvert publiquement."
  }
}

run "reject_public_ssh" {
  command = plan
  variables {
    ssh_allowed_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [var.ssh_allowed_cidrs]
}

run "reject_empty_ssh" {
  command = plan
  variables {
    ssh_allowed_cidrs = []
  }
  expect_failures = [var.ssh_allowed_cidrs]
}

run "reject_ipv6_ssh" {
  command = plan
  variables {
    ssh_allowed_cidrs = ["2001:db8::1/32"]
  }
  expect_failures = [var.ssh_allowed_cidrs]
}
