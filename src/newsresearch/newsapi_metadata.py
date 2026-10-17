"""Versioned metadata projections without transport or storage side effects.

Historical proofs use version 1's exact field set. Version 2 additionally retains
the provider's eventUri field only when it exists, preserving null and malformed
values rather than interpreting them as absent or as valid event assignments.
"""
from __future__ import annotations

from .common import Json, ResearchError


def project_article_metadata(article: Json, *, version: int = 2) -> Json:
    """Project permitted metadata while keeping provider event-field fidelity."""
    if type(version) is not int or version not in (1, 2):
        raise ResearchError("Unknown article metadata projection version")
    if article.get("body") not in (None, ""):
        raise ResearchError("Unexpected article body in metadata-only resolution")
    result = {key: article.get(key) for key in ("uri", "title", "url", "date", "lang", "source")}
    if version == 2 and "eventUri" in article:
        result["eventUri"] = article["eventUri"]
    return result
