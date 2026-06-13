"""AACT connection resolution — now backed by the shared ``aact-kit`` package.

This module previously held arac's own copy of the AACT backend resolver. That
logic was extracted verbatim into ``aact-kit`` (``aact_kit.location``) and is
shared with cardiotrialaudit / africa-tb-atlas / AlBurhan. This file is kept as
a thin compatibility shim so existing imports keep working:

    from arac.classify._aact_path import AACTBackend, AACTLocation, resolve_aact_location

``aact-kit`` adds a fifth backend (ZIP) beyond arac's original four; arac only
ever resolves POSTGRES / SQLITE / TSV_DIR / CSV_DIR via env vars or snapshot
auto-discovery, so behavior for arac is unchanged.

Install: ``pip install aact-kit`` (or ``pip install -e`` against a local checkout).
"""

from __future__ import annotations

from aact_kit import (  # noqa: F401  (re-exported for backward compatibility)
    AACTBackend,
    AACTLocation,
    location_from_path,
    resolve_aact_location,
)

__all__ = [
    "AACTBackend",
    "AACTLocation",
    "resolve_aact_location",
    "location_from_path",
]
