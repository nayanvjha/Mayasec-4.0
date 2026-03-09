"""TLS termination utilities for HTTPS ingress handling."""

from __future__ import annotations

import ssl


def create_ssl_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """Create an SSL context for aiohttp HTTPS listener."""
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=cert_file, keyfile=key_file)
    context.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3  # harden legacy protocol usage
    return context
