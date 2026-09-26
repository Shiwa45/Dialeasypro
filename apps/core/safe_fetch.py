"""
TeleCRM Backend — apps/core/safe_fetch.py

Fetching a URL that came from outside, without letting it point inward.

The call-recording download took `RecordingUrl` straight from an
unauthenticated webhook and ran `requests.get` on it — so anyone could make
the server fetch cloud metadata or an internal service and store the answer as
a "recording". It also read the whole body into memory at once.

`fetch_public_url` refuses anything that is not plain http(s) to a public
address, re-checks every redirect hop (a public URL may redirect to
169.254.169.254), and stops reading at a size limit.

Residual risk, stated plainly: the address is checked when the name is
resolved and the connection is made a moment later, so a DNS-rebinding
attacker with a very short TTL could in principle slip between the two. Closing
that fully means pinning the connection to the checked IP.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

DEFAULT_MAX_BYTES = 100 * 1024 * 1024   # 100 MB — generous for a call recording
DEFAULT_TIMEOUT = 60
MAX_REDIRECTS = 3


class UnsafeURL(ValueError):
    """The URL is not one this server should fetch."""


def _check_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURL(f"Only http(s) URLs may be fetched, not {parsed.scheme!r}.")
    host = parsed.hostname
    if not host:
        raise UnsafeURL("The URL has no host.")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURL(f"Could not resolve {host}: {exc}") from exc

    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified
        ):
            raise UnsafeURL(f"{host} resolves to a non-public address ({address}).")


def fetch_public_url(url: str, *, max_bytes: int = DEFAULT_MAX_BYTES,
                     timeout: int = DEFAULT_TIMEOUT) -> tuple[bytes, str]:
    """
    GET a public URL and return (body, content_type).

    Raises UnsafeURL for a non-public destination or an oversized body, and
    requests exceptions for ordinary network failures.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        _check_public(current)
        response = requests.get(current, timeout=timeout, stream=True, allow_redirects=False)

        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location", "")
            response.close()
            if not location:
                raise UnsafeURL("Redirect without a Location header.")
            current = urljoin(current, location)
            continue

        response.raise_for_status()
        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            response.close()
            raise UnsafeURL(f"The file is {declared} bytes; the limit is {max_bytes}.")

        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            total += len(chunk)
            if total > max_bytes:
                response.close()
                raise UnsafeURL(f"The file is larger than the {max_bytes}-byte limit.")
            chunks.append(chunk)
        return b"".join(chunks), response.headers.get("Content-Type", "")

    raise UnsafeURL(f"More than {MAX_REDIRECTS} redirects.")
