"""Tests for remote-access authorization (the 'super secure from anywhere' invariant).

Local/direct requests are always allowed. Remote (proxied) requests must pass Cloudflare-Access SSO
(matching email) OR the shared secret. A configured-but-unsatisfied request must be REJECTED.

Run:  .venv/bin/python tests/test_auth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from daemon import config
from daemon.server import _authorized

PROXY = {"cf-connecting-ip": "1.2.3.4"}              # marks a request as remote/tunneled
SSO = {**PROXY, "cf-access-authenticated-user-email": "ben@example.com"}
SSO_BAD = {**PROXY, "cf-access-authenticated-user-email": "evil@bad.com"}


def setcfg(**kw):
    config._state = dict(config.DEFAULTS)
    config._state.update(kw)


def test_local_always_allowed():
    setcfg(access_email="ben@example.com", shared_secret="s3cret")
    assert _authorized({}, "") is True                    # no proxy headers = local


def test_sso_match_allowed_mismatch_rejected():
    setcfg(access_email="ben@example.com")
    assert _authorized(SSO, "") is True
    assert _authorized(SSO_BAD, "") is False
    assert _authorized(PROXY, "") is False                # no SSO header at all


def test_secret_path():
    setcfg(shared_secret="s3cret")
    assert _authorized(PROXY, "s3cret") is True
    assert _authorized(PROXY, "wrong") is False


def test_nothing_configured_is_open():
    setcfg()                                              # no access_email, no secret
    assert _authorized(PROXY, "") is True


if __name__ == "__main__":
    test_local_always_allowed()
    test_sso_match_allowed_mismatch_rejected()
    test_secret_path()
    test_nothing_configured_is_open()
    config._state = {}
    print("ok — all auth tests passed")
