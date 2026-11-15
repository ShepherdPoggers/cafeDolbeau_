import os

bind = "0.0.0.0:8000"
chdir = "/app/src"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
accesslog = "-"
errorlog = "-"
capture_output = True
forwarded_allow_ips = "*"  # Gunicorn est accessible uniquement sur le réseau interne.
