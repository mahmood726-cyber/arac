"""Resolve-package smoke: importable, no module-level side effects."""

from __future__ import annotations


def test_resolve_package_importable() -> None:
    import arac.resolve  # noqa: F401


def test_resolve_dependencies_present() -> None:
    import httpx  # noqa: F401
    import yaml  # noqa: F401
