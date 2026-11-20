mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = {
      account_id = "123456789012"
    }
  }
}

variables {
  state_bucket               = "test-state-bucket"
  existing_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
}

run "trust_only_production_repository" {
  command = plan
  assert {
    condition     = jsondecode(aws_iam_role.github.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:ShepherdPoggers@146887969/cafeDolbeau_@1383926134:environment:production"
    error_message = "Le rôle doit être restreint au dépôt et à l'environnement production."
  }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Le fournisseur existant doit être réutilisé."
  }
}

run "reject_invalid_repository_id" {
  command = plan
  variables {
    github_repository_id = "*"
  }
  expect_failures = [var.github_repository_id]
}

run "reject_invalid_owner_id" {
  command = plan
  variables {
    github_owner_id = "*"
  }
  expect_failures = [var.github_owner_id]
}
