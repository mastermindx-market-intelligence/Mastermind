"""Narrow HAE extension: direct Z.ai GLM-5.3 native effort choices.

Copied into a staged HAE payload as mastermind_zai.py. This is not a plugin,
router, credential reader, request writer, or model execution path. The existing
HAE middleware owns all scoring, turn reuse, manual mode and request mutation.
"""
from __future__ import annotations
from http.client import HTTPS_PORT
from urllib.parse import urlsplit

LEVELS = ("low", "high", "max")


def direct_zai_levels(provider, model, api_mode, base_url):
    """Return named choices only for the exact documented direct route.

    A matching model name on a proxy, a different provider, or a neighboring
    model/API is not positive evidence. Upstream behavior elsewhere is unchanged.
    """
    if (provider, model, api_mode) != ("zai", "glm-5.3", "chat_completions"):
        return ()
    if type(base_url) is not str or any(c.isspace() for c in base_url):
        return ()
    try:
        url = urlsplit(base_url)
        if (url.scheme != "https" or url.hostname != "api.z.ai"
                or url.port not in (None, HTTPS_PORT) or url.username is not None
                or url.password is not None or url.query or url.fragment
                or url.path.rstrip("/") not in (
                    "/api/paas/v4", "/api/coding/paas/v4")):
            return ()
    except ValueError:
        return ()
    return LEVELS


def direct_zai_request_allowed(provider, model, api_mode, base_url):
    """Fence every request, including a same-turn endpoint change.

    HAE's existing turn identity does not include base_url. A prior native
    decision must not authorize a different endpoint under the same model.
    Other provider/model families keep upstream behavior.
    """
    if (provider, model) != ("zai", "glm-5.3"):
        return True
    return bool(direct_zai_levels(provider, model, api_mode, base_url))
