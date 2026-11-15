"""Configuration locale explicite, jamais sélectionnée par compose.yaml."""
from .settings import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
AUTH_PASSWORD_VALIDATORS = []
