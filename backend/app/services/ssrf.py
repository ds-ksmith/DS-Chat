import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeWebhookUrlError(Exception):
    pass


def validate_target_url(url: str) -> None:
    """Creation-time-only SSRF check: rejects non-http(s) schemes and any
    target whose hostname resolves to a private/loopback/link-local/
    reserved/multicast address. Not re-checked per delivery, so this doesn't
    defend against DNS rebinding between creation and a later send -- a
    documented known limitation, not an oversight.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeWebhookUrlError()
    if not parsed.hostname:
        raise UnsafeWebhookUrlError()

    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise UnsafeWebhookUrlError() from exc

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
            raise UnsafeWebhookUrlError()
