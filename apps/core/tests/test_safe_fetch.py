"""
Fetching a URL that came from outside.

The call-recording download ran `requests.get` on the RecordingUrl posted to
an unauthenticated webhook. Anyone could make the server read cloud metadata
(169.254.169.254) or an internal service and store the answer as a recording.
It also read the whole body into memory.

These tests fake DNS and HTTP, so they never touch the network.
"""
from unittest import mock

import pytest

from apps.core import safe_fetch
from apps.core.safe_fetch import UnsafeURL, fetch_public_url


def _resolves_to(ip):
    return mock.patch.object(
        safe_fetch.socket, "getaddrinfo",
        return_value=[(2, 1, 6, "", (ip, 443))],
    )


class _Response:
    def __init__(self, status=200, headers=None, body=b"audio", redirect=None):
        self.status_code = status
        self.headers = headers or {}
        self._body = body
        self.is_redirect = redirect is not None
        self.is_permanent_redirect = False
        if redirect:
            self.headers["Location"] = redirect

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def iter_content(self, chunk_size):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self):
        pass


# ---- Refused -----------------------------------------------------------

@pytest.mark.parametrize("ip", [
    "169.254.169.254",   # cloud metadata
    "127.0.0.1",          # this machine
    "10.0.0.5",           # private network
    "192.168.1.10",
    "172.16.0.1",
    "::1",
])
def test_an_internal_address_is_refused(ip):
    with _resolves_to(ip), mock.patch.object(safe_fetch.requests, "get") as get:
        with pytest.raises(UnsafeURL):
            fetch_public_url("https://recordings.example.com/a.mp3")
        get.assert_not_called()


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://example.com/",
    "ftp://example.com/a.mp3",
])
def test_non_http_schemes_are_refused(url):
    with pytest.raises(UnsafeURL):
        fetch_public_url(url)


def test_a_public_url_that_redirects_inward_is_refused():
    """A public host can redirect to the metadata address; every hop is checked."""
    responses = iter([_Response(status=302, redirect="http://169.254.169.254/latest/")])
    resolves = iter([[(2, 1, 6, "", ("93.184.216.34", 443))],
                     [(2, 1, 6, "", ("169.254.169.254", 80))]])
    with mock.patch.object(safe_fetch.socket, "getaddrinfo", side_effect=lambda *a, **k: next(resolves)), \
         mock.patch.object(safe_fetch.requests, "get", side_effect=lambda *a, **k: next(responses)):
        with pytest.raises(UnsafeURL):
            fetch_public_url("https://recordings.example.com/a.mp3")


def test_an_oversized_body_is_refused_without_reading_it_all():
    big = _Response(headers={"Content-Length": str(10 * 1024 * 1024)})
    with _resolves_to("93.184.216.34"), mock.patch.object(safe_fetch.requests, "get", return_value=big):
        with pytest.raises(UnsafeURL):
            fetch_public_url("https://recordings.example.com/a.mp3", max_bytes=1024)


def test_a_body_that_lies_about_its_size_is_still_capped():
    liar = _Response(headers={}, body=b"x" * 5000)
    with _resolves_to("93.184.216.34"), mock.patch.object(safe_fetch.requests, "get", return_value=liar):
        with pytest.raises(UnsafeURL):
            fetch_public_url("https://recordings.example.com/a.mp3", max_bytes=1024)


# ---- Allowed -----------------------------------------------------------

def test_a_public_recording_is_fetched():
    ok = _Response(headers={"Content-Type": "audio/mpeg"}, body=b"ID3fakeaudio")
    with _resolves_to("93.184.216.34"), mock.patch.object(safe_fetch.requests, "get", return_value=ok):
        body, content_type = fetch_public_url("https://recordings.example.com/a.mp3")

    assert body == b"ID3fakeaudio"
    assert content_type == "audio/mpeg"


def test_a_redirect_between_public_hosts_is_followed():
    responses = iter([
        _Response(status=302, redirect="https://cdn.example.com/a.mp3"),
        _Response(headers={"Content-Type": "audio/mpeg"}, body=b"audio"),
    ])
    with _resolves_to("93.184.216.34"), \
         mock.patch.object(safe_fetch.requests, "get", side_effect=lambda *a, **k: next(responses)):
        body, _ = fetch_public_url("https://recordings.example.com/a.mp3")

    assert body == b"audio"
