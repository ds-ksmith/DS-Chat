import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(Exception):
    pass


def validate_target_url(url: str) -> None:
    """One-shot SSRF check: rejects non-http(s) schemes and any target whose
    hostname resolves to a private/loopback/link-local/reserved/multicast
    address. Shared by two callers with different re-check needs: webhook
    subscriptions validate once at creation time and reuse the URL for many
    future deliveries (a real but accepted DNS-rebinding gap, documented
    here), while link_preview_service calls this fresh before *every* hop of
    a redirect chain for a one-shot fetch, which closes that gap for its own
    use case.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError()
    if not parsed.hostname:
        raise UnsafeUrlError()

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError() from exc

    for *_rest, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeUrlError()
