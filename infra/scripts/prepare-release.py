#!/usr/bin/env python3
"""Valider le .env sans l'afficher et préparer les seuls fichiers envoyés à EC2."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    domain = os.environ["PUBLIC_DOMAIN"]
    tag = os.environ["IMAGE_TAG"]
    if not re.fullmatch(r"[a-f0-9]{40}", tag):
        raise ValueError("IMAGE_TAG doit être un SHA Git complet.")
    if len(domain) > 253 or not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain:
        raise ValueError("PUBLIC_DOMAIN doit être un nom DNS sans schéma ni port.")
    folder = Path(".deploy/release")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    env_path = folder / ".env"
    env_path.write_text(os.environ["PRODUCTION_ENV"].rstrip() + "\n"
                        + f"IMAGE_TAG={tag}\nPUBLIC_DOMAIN={domain}\n")
    env_path.chmod(0o600)
    shutil.copyfile("docker/compose.prod.yaml", folder / "compose.yaml")
    shutil.copyfile("infra/scripts/deploy.sh", folder / "deploy.sh")
    # Éliminer les substitutions implicites par les variables du runner.
    clean_env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "DOCKER_CONFIG"}}
    result = subprocess.run(["docker", "compose", "--env-file", str(env_path),
                             "-f", str(folder / "compose.yaml"), "config", "--format", "json"],
                            env=clean_env, text=True, capture_output=True)
    if result.returncode:
        raise ValueError("Configuration Compose de production invalide (détails masqués).")
    config = json.loads(result.stdout)
    secrets = config["services"]["secrets"]["environment"]
    if any(not secrets.get(name) or len(secrets[name]) < 32 for name in ("SECRET_KEY", "POSTGRES_PASSWORD")):
        raise ValueError("SECRET_KEY et POSTGRES_PASSWORD doivent contenir au moins 32 caractères.")
    if not config["services"]["cloudflared"]["environment"].get("TUNNEL_TOKEN"):
        raise ValueError("CLOUDFLARE_TUNNEL_TOKEN est requis.")
    if any("build" in service for service in config["services"].values()):
        raise ValueError("Aucun build autorisé sur EC2.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
