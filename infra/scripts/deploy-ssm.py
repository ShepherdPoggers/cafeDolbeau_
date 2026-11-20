#!/usr/bin/env python3
"""Transférer une release privée et attendre son déploiement via SSM."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time


def aws(*args, check=True):
    return subprocess.run(["aws", *args, "--output", "json"], check=check,
                          text=True, capture_output=True)


def result(*args):
    return json.loads(aws(*args).stdout)


def wait_for_online(instance):
    for _ in range(120):
        data = result("ssm", "describe-instance-information", "--filters",
                      json.dumps([{"Key": "InstanceIds", "Values": [instance]}]))
        if any(item["PingStatus"] == "Online" for item in data["InstanceInformationList"]):
            return
        time.sleep(10)
    raise RuntimeError("SSM indisponible après 20 minutes.")


def main():
    outputs = json.loads(Path(".deploy/outputs.json").read_text())
    bucket = outputs["artifact_bucket"]["value"]
    instance = outputs["instance_id"]["value"]
    release = f"{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    prefix = f"releases/{release}/"
    source = f"s3://{bucket}/{prefix}"
    folder = f"/opt/cafedolbeau/releases/{release}"
    terminal = False
    sent = False
    try:
        aws("s3", "cp", ".deploy/release/", source, "--recursive", "--only-show-errors", "--sse", "AES256")
        wait_for_online(instance)
        # Aucun contenu du .env ne figure dans les paramètres de la commande.
        command = "\n".join([
            "set -eu", "umask 077",
            "cloud-init status --wait >/dev/null",
            "systemctl is-active --quiet docker",
            "docker compose version >/dev/null",
            f"install -d -m 0700 {shlex.quote(folder)}",
            f"aws s3 cp {shlex.quote(source)} {shlex.quote(folder + '/')} --recursive --only-show-errors",
            f"cd {shlex.quote(folder)}",
            "chmod 0600 .env",
            "sha256sum --check SHA256SUMS",
            "bash deploy.sh",
        ])
        data = result("ssm", "send-command", "--instance-ids", instance,
                      "--document-name", "AWS-RunShellScript", "--timeout-seconds", "600",
                      "--parameters", json.dumps({"commands": [command], "executionTimeout": ["2400"]}))
        command_id = data["Command"]["CommandId"]
        sent = True
        print(f"Commande SSM : {command_id}", flush=True)
        deadline = time.monotonic() + 3100
        while time.monotonic() < deadline:
            response = aws("ssm", "get-command-invocation", "--command-id", command_id,
                           "--instance-id", instance, check=False)
            if response.returncode:
                if "InvocationDoesNotExist" in response.stderr:
                    time.sleep(5)
                    continue
                raise RuntimeError("Impossible de consulter la commande SSM.")
            status = json.loads(response.stdout)["Status"]
            if status == "Success":
                terminal = True
                return
            if status in {"Failed", "Cancelled", "TimedOut"}:
                terminal = True
                raise RuntimeError(f"Déploiement SSM : {status}. Consulter la commande {command_id} dans AWS.")
            time.sleep(10)
        raise RuntimeError("Délai SSM dépassé ; vérifier la commande dans AWS avant de relancer.")
    finally:
        # Une commande encore en cours doit pouvoir terminer son téléchargement.
        if terminal or not sent:
            cleaned = aws("s3", "rm", source, "--recursive", "--only-show-errors", check=False)
            if cleaned.returncode:
                print("Nettoyage S3 incomplet ; expiration automatique après un jour.", flush=True)


if __name__ == "__main__":
    main()
