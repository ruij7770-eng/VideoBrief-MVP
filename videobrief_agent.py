"""Compatibility facade for the modular smart-analysis adapter.

New code should import from ``videobrief.infrastructure.analysis``.  Historical
imports remain stable while the architecture migration is in progress.
"""
from videobrief.domain.taxonomy import (
    CONTENT_MODEL_ROLE_ORDER,
    CONTENT_MODEL_ROLES,
    CONTENT_TYPE_LABELS,
    CONTENT_TYPES,
)
from videobrief.infrastructure.analysis.audit import _content_template, _merge_agent_output
from videobrief.infrastructure.analysis.deepseek import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    _config,
    _http_transport,
    _parse_content,
    agent_status,
    enhance_brief,
)
from videobrief.infrastructure.analysis.prompts import _audit_prompt, _prompt

__all__ = [
    "CONTENT_MODEL_ROLE_ORDER",
    "CONTENT_MODEL_ROLES",
    "CONTENT_TYPE_LABELS",
    "CONTENT_TYPES",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "_audit_prompt",
    "_config",
    "_content_template",
    "_http_transport",
    "_merge_agent_output",
    "_parse_content",
    "_prompt",
    "agent_status",
    "enhance_brief",
]
