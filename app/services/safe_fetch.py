"""
Fetch a user-supplied public URL without becoming an SSRF proxy.

The old guard resolved the hostname, checked the addresses, then handed
the URL to trafilatura — which resolved it again (a DNS-rebinding window)
and followed redirects on its own (so `https://evil.example/` → 302 →
`http://127.0.0.1:5001/…` sailed through). Here every hop is checked and
the connection goes to the exact address that passed the check:

- only http/https, no IP literals or hostnames in private/loopback/
  link-local/multicast/reserved space (any bad A/AAAA record fails the
  whole host);
- redirects are not followed by the HTTP client; each Location is
  re-validated and fetched as a new hop, at most MAX_REDIRECTS times;
- the TCP connection is opened to the validated IP, with the original
  hostname in the Host header and for TLS SNI / certificate checking;
- the body is capped at `max_bytes`.

Blocking (socket + urllib3): call it from a threadpool, not the event loop.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import urllib3

MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = urllib3.Timeout(connect=10.0, read=20.0)
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_USER_AGENT = "Mozilla/5.0 (compatible; Qingdu article import)"


class UnsafeUrlError(ValueError):
    """The URL (or a redirect target) is malformed or points inward."""


class FetchFailed(Exception):
    """The remote site couldn't be fetched (network, HTTP error, redirect loop)."""


@dataclass
class FetchResult:
    url: str  # final URL after redirects
    body: bytes
    content_type: str | None


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def check_url(url: str) -> tuple[str, str, int, str, str]:
    """Validate `url` and resolve it to one public IP.

    Returns (scheme, hostname, port, ip, path_and_query). Raises
    UnsafeUrlError for anything that must not be fetched.
    """
    try:
        parsed = urlparse(url.strip())
        port = parsed.port
    except ValueError as e:
        raise UnsafeUrlError(f"Malformed URL: {e}") from e

    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only http and https URLs are allowed.")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL is missing a hostname.")
    port = port or (443 if parsed.scheme == "https" else 80)

    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        if _is_blocked(literal):
            raise UnsafeUrlError("Won't fetch internal/private addresses.")
        addresses = [literal]
    else:
        try:
            infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as e:
            raise UnsafeUrlError(f"Could not resolve {hostname!r}.") from e
        addresses = []
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if _is_blocked(ip):
                raise UnsafeUrlError(
                    f"{hostname} resolves into a private/internal IP range; refusing to fetch."
                )
            addresses.append(ip)
        if not addresses:
            raise UnsafeUrlError(f"Could not resolve {hostname!r}.")

    # Prefer IPv4: plenty of hosts publish AAAA records the server can't route.
    addresses.sort(key=lambda ip: ip.version)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return parsed.scheme, hostname, port, str(addresses[0]), path


def _open(scheme: str, ip: str, port: int, host: str, path: str, timeout) -> urllib3.HTTPResponse:
    """One GET to `ip`, presenting `host` (Host header, SNI, cert check).
    Redirects are returned, not followed."""
    default_port = 443 if scheme == "https" else 80
    headers = {
        "Host": host if port == default_port else f"{host}:{port}",
        "User-Agent": _USER_AGENT,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    }
    if scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            ip,
            port,
            timeout=timeout,
            retries=False,
            cert_reqs="CERT_REQUIRED",
            server_hostname=host,
            assert_hostname=host,
        )
    else:
        pool = urllib3.HTTPConnectionPool(ip, port, timeout=timeout, retries=False)
    return pool.urlopen(
        "GET",
        path,
        headers=headers,
        redirect=False,
        retries=False,
        preload_content=False,
    )


def fetch(url: str, *, max_bytes: int = MAX_BYTES, timeout=TIMEOUT) -> FetchResult:
    """GET a public URL, validating and IP-pinning every redirect hop."""
    current = url.strip()
    for _hop in range(MAX_REDIRECTS + 1):
        scheme, host, port, ip, path = check_url(current)
        try:
            response = _open(scheme, ip, port, host, path, timeout)
        except urllib3.exceptions.HTTPError as e:
            raise FetchFailed(f"Couldn't reach {host}.") from e
        try:
            status = response.status
            if status in _REDIRECT_STATUSES:
                location = response.headers.get("Location")
                if not location:
                    raise FetchFailed("Redirect without a target.")
                current = urljoin(current, location)
                continue
            if status >= 400:
                raise FetchFailed(f"The site answered HTTP {status}.")
            try:
                body = response.read(max_bytes)
            except urllib3.exceptions.HTTPError as e:
                raise FetchFailed(f"Couldn't read the page from {host}.") from e
            return FetchResult(
                url=current,
                body=body[:max_bytes],
                content_type=response.headers.get("Content-Type"),
            )
        finally:
            response.close()
    raise FetchFailed("Too many redirects.")


__all__ = ["FetchFailed", "FetchResult", "UnsafeUrlError", "check_url", "fetch"]
