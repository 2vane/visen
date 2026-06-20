"""Locate packaged resource files (policy YAMLs, seed data).

Resolves files bundled inside the installed ``vsentinel`` package so the
framework works when imported from anywhere, not only from the source repo.
"""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_ROOT = files("vsentinel") / "resources"


def resource_path(*parts: str) -> Path:
    """Absolute filesystem path to a packaged resource under ``resources/``."""
    return Path(str(_ROOT.joinpath(*parts)))


def policy_file(name: str) -> Path:
    """Path to a packaged policy file, e.g. ``policy_file('legal_policy.yml')``."""
    return resource_path("policy", name)


def data_file(name: str) -> Path:
    """Path to a packaged data file, e.g. ``data_file('decree_articles.json')``."""
    return resource_path("data", name)
