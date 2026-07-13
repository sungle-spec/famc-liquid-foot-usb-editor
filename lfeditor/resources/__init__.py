"""Bundled, shippable resources (factory-default backups, etc.) + path resolution that works
both in a dev checkout and inside a PyInstaller bundle."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Factory-default backups bundled with the app, mirroring the original editor's
# File → "Load Factory Defaults (…) into Editor" entries. (label, filename)
FACTORY_DEFAULTS: list[tuple[str, str]] = [
    ("Liquid Foot+ Mini", "Factory_DefaultsMini.syx"),
    ("Liquid Foot+ JR+", "Factory_DefaultsJR.syx"),
    ("Liquid Foot+ 12 / 12+", "Factory_Defaults12.syx"),
    ("Liquid Foot+ Pro+", "Factory_DefaultsPro.syx"),
]

# "Load Special Factory Programming" — device-specific templates.
FACTORY_SPECIAL: list[tuple[str, str]] = [
    ("Axe-Fx (II) Basic", "Factory_DefaultsAXEFX.syx"),
    ("Axe-Fx III Basic", "Factory_AXEFXIII_Basic.syx"),
    ("Kemper Defaults", "Factory_DefaultsKEMPER.syx"),
    ("Kemper Performance Template", "Factory_Kemper_Perf_Template.syx"),
]


def resource_path(*parts: str) -> str:
    """Absolute path to a bundled resource (PyInstaller-aware)."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, "lfeditor", "resources", *parts)
    return str(Path(__file__).resolve().parent.joinpath(*parts))


def factory_path(filename: str) -> str:
    return resource_path("factory", filename)
