#!/usr/bin/env python3
"""Amorçage local : python3 infra/scripts/bootstrap.py --state-bucket NOM-UNIQUE."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def aws(*args, check=True):
    return subprocess.run(["aws", *args, "--output", "json"], check=check,
                          text=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-bucket", required=True)
    parser.add_argument("--region", default="us-east-2", choices=["us-east-2"])
    parser.add_argument("--repository", default="ShepherdPoggers/cafeDolbeau_")
    parser.add_argument("--owner-id", default="146887969")
    parser.add_argument("--repository-id", default="1383926134")
    args = parser.parse_args()
    missing = [tool for tool in ("aws", "terraform") if shutil.which(tool) is None]
    if missing:
        parser.error("Outils introuvables dans le PATH : " + ", ".join(missing)
                     + ". Installer AWS CLI v2 et Terraform >= 1.11 avant de relancer.")
    account = json.loads(aws("sts", "get-caller-identity").stdout)["Account"]
    bucket = args.state_bucket
    exists = aws("s3api", "head-bucket", "--bucket", bucket,
                 "--expected-bucket-owner", account, check=False)
    if exists.returncode:
        # Une erreur d'accès n'est pas une autorisation de modifier un autre bucket.
        if "404" not in exists.stderr and "Not Found" not in exists.stderr:
            raise RuntimeError(exists.stderr)
        aws("s3api", "create-bucket", "--bucket", bucket, "--region", args.region,
            "--create-bucket-configuration", f"LocationConstraint={args.region}")
    aws("s3api", "put-public-access-block", "--bucket", bucket,
        "--public-access-block-configuration", json.dumps({
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True}))
    aws("s3api", "put-bucket-versioning", "--bucket", bucket,
        "--versioning-configuration", "Status=Enabled")
    aws("s3api", "put-bucket-encryption", "--bucket", bucket,
        "--server-side-encryption-configuration", json.dumps({"Rules": [{
            "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}))
    aws("s3api", "put-bucket-policy", "--bucket", bucket, "--policy", json.dumps({
        "Version": "2012-10-17", "Statement": [{
            "Effect": "Deny", "Principal": "*", "Action": "s3:*",
            "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}}}]}))
    # Préserver le choix initial lorsqu'un fournisseur OIDC a été créé par cet état.
    key = "bootstrap/terraform.tfstate"
    state = aws("s3api", "head-object", "--bucket", bucket, "--key", key, check=False)
    existing_arn = ""
    if state.returncode:
        if "404" not in state.stderr and "Not Found" not in state.stderr:
            raise RuntimeError(state.stderr)
        providers = json.loads(aws("iam", "list-open-id-connect-providers").stdout)
        for item in providers["OpenIDConnectProviderList"]:
            if item["Arn"].endswith(":oidc-provider/token.actions.githubusercontent.com"):
                existing_arn = item["Arn"]
    else:
        previous = json.loads(aws("s3", "cp", f"s3://{bucket}/{key}", "-").stdout)
        existing_arn = previous.get("outputs", {}).get("existing_oidc_provider_arn", {}).get("value", "")
    env = os.environ | {
        "TF_VAR_region": args.region, "TF_VAR_state_bucket": bucket,
        "TF_VAR_github_repository": args.repository,
        "TF_VAR_github_owner_id": args.owner_id,
        "TF_VAR_github_repository_id": args.repository_id,
        "TF_VAR_existing_oidc_provider_arn": existing_arn,
    }
    root = Path(__file__).resolve().parents[1] / "bootstrap"
    subprocess.run(["terraform", f"-chdir={root}", "init", "-input=false", "-lockfile=readonly",
                    f"-backend-config=bucket={bucket}", f"-backend-config=region={args.region}"], check=True, env=env)
    subprocess.run(["terraform", f"-chdir={root}", "apply"], check=True, env=env)


if __name__ == "__main__":
    main()
