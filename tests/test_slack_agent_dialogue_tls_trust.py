"""A2 must use the existing C1 trust source under sealed macOS Python."""
from types import SimpleNamespace
import ssl

import pytest

from integrations.slack_agent_dialogue.metadata_verifier import UrllibSlackAuthTestTransport
from integrations.slack_agent_dialogue.slack_web_api import UrllibSlackHttpTransport
from integrations.slack_executive import slack_web_api as c1


@pytest.fixture(params=[UrllibSlackAuthTestTransport, UrllibSlackHttpTransport])
def transport_type(request):
    return request.param


def test_sealed_macos_without_default_ca_uses_system_trust(monkeypatch, transport_type):
    trusted = ssl.create_default_context()
    assert trusted.cert_store_stats()["x509_ca"] > 0
    monkeypatch.setattr(c1, "sys", SimpleNamespace(platform="darwin"))

    def context_factory(*, cafile=None):
        if cafile == "/etc/ssl/cert.pem":
            return trusted
        # The signed PSF runtime has no post-install certifi roots. Context
        # creation succeeds, but a later Slack TLS handshake cannot validate.
        assert cafile is None
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    monkeypatch.setattr(ssl, "create_default_context", context_factory)
    context = transport_type()._ssl_context
    assert context.cert_store_stats()["x509_ca"] > 0
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True


def test_missing_system_trust_refuses_without_fallback(monkeypatch, transport_type):
    monkeypatch.setattr(c1, "sys", SimpleNamespace(platform="darwin"))
    calls = []

    def unavailable(**kwargs):
        calls.append(kwargs)
        raise OSError("private host diagnostic")

    monkeypatch.setattr(ssl, "create_default_context", unavailable)
    with pytest.raises(RuntimeError, match="^SLACK_TLS_TRUST_UNAVAILABLE$"):
        transport_type()
    assert calls == [{"cafile": "/etc/ssl/cert.pem"}]


def test_explicit_context_preserved_without_loading_defaults(monkeypatch, transport_type):
    context = ssl.create_default_context()

    def unexpected(**kwargs):
        raise AssertionError("explicit context must not load ambient trust")

    monkeypatch.setattr(ssl, "create_default_context", unexpected)
    assert transport_type(ssl_context=context)._ssl_context is context


def test_other_platform_keeps_default_trust(monkeypatch, transport_type):
    context = ssl.create_default_context()
    monkeypatch.setattr(c1, "sys", SimpleNamespace(platform="linux"))
    calls = []

    def default_context(**kwargs):
        calls.append(kwargs)
        return context

    monkeypatch.setattr(ssl, "create_default_context", default_context)
    assert transport_type()._ssl_context is context
    assert calls == [{}]
