#!/usr/bin/env python3
"""Valider le .env sans l'afficher et préparer les seuls fichiers envoyés à EC2."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def dotenv_value(value):
    # Préserver les dollars, guillemets et antislashs lors de la lecture par Compose.
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('$', '$$') + '"'


def main():
    domain = os.environ["PUBLIC_DOMAIN"]
    tag = os.environ["IMAGE_TAG"]
    if not re.fullmatch(r"[a-f0-9]{40}", tag):
        raise ValueError("IMAGE_TAG doit être un SHA Git complet.")
    if len(domain) > 253 or not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain) or "." not in domain:
        raise ValueError("PUBLIC_DOMAIN doit être un nom DNS sans schéma ni port.")
    private = {}
    for name in ("SECRET_KEY", "POSTGRES_PASSWORD", "CLOUDFLARE_TUNNEL_TOKEN", "CLOUDFLARE_DNS_API_TOKEN"):
        value = os.environ.get(name, "")
        if not value.strip():
            raise ValueError(f"Secret GitHub manquant : {name}.")
        if any(char in value for char in "\r\n\0"):
            raise ValueError(f"Le secret {name} doit être sur une seule ligne.")
        if name in ("SECRET_KEY", "POSTGRES_PASSWORD") and len(value) < 32:
            raise ValueError(f"Le secret {name} doit contenir au moins 32 caractères.")
        private[name] = value
    if not re.fullmatch(r"[A-Za-z0-9_-]+", private['CLOUDFLARE_DNS_API_TOKEN']):
        raise ValueError('CLOUDFLARE_DNS_API_TOKEN doit être un jeton API Cloudflare valide.')
    email = os.environ.get('LETSENCRYPT_EMAIL', '')
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError('LETSENCRYPT_EMAIL doit être une adresse courriel valide.')
    folder = Path(".deploy/release")
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    env_path = folder / ".env"
    env_path.write_text("".join(f"{name}={dotenv_value(value)}\n" for name, value in private.items()
                                if name != 'CLOUDFLARE_DNS_API_TOKEN')
                        + f"IMAGE_TAG={tag}\nPUBLIC_DOMAIN={domain}\n")
    env_path.chmod(0o600)
    shutil.copyfile("docker/compose.prod.yaml", folder / "compose.yaml")
    shutil.copyfile("infra/scripts/deploy.sh", folder / "deploy.sh")
    for source in ('infra/scripts/tls.py', 'infra/systemd/cafedolbeau-tls.service',
                   'infra/systemd/cafedolbeau-tls.timer'):
        shutil.copyfile(source, folder / Path(source).name)
    credentials = folder / 'cloudflare.ini'
    credentials.write_text('dns_cloudflare_api_token = ' + private['CLOUDFLARE_DNS_API_TOKEN'] + '\n')
    credentials.chmod(0o600)
    tls_config = folder / 'tls.json'
    tls_config.write_text(json.dumps({'domain': domain, 'email': email,
                                    'proxy_image': f'cafe-dolbeau-proxy:{tag}'}))
    tls_config.chmod(0o600)
    # Éliminer les substitutions implicites par les variables du runner.
    clean_env = {k: v for k, v in os.environ.items() if k in {"PATH", "HOME", "DOCKER_CONFIG"}}
    result = subprocess.run(["docker", "compose", "--env-file", str(env_path),
                             "-f", str(folder / "compose.yaml"), "config", "--format", "json"],
                            env=clean_env, text=True, capture_output=True)
    if result.returncode:
        raise ValueError("Configuration Compose de production invalide (détails masqués).")
    config = json.loads(result.stdout)
    secrets = config["services"]["secrets"]["environment"]
    # config échappe les dollars pour que sa sortie puisse être relue par Compose.
    expected = {name: value.replace('$', '$$') for name, value in private.items()}
    if (any(secrets.get(name) != expected[name] for name in ("SECRET_KEY", "POSTGRES_PASSWORD"))
            or config["services"]["cloudflared"]["environment"].get("TUNNEL_TOKEN") != expected["CLOUDFLARE_TUNNEL_TOKEN"]):
        raise ValueError("La lecture du .env a altéré un secret (valeurs masquées).")
    if any("build" in service for service in config["services"].values()):
        raise ValueError("Aucun build autorisé sur EC2.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
