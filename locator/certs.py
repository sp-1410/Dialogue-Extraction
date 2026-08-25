"""
Supplemental CA bundle for a real, observed TLS misconfiguration on
ok.ru's video CDN (roadmap risk flagged in the architecture plan: "ok.ru
extractor breaks or is geo-restricted").

What's actually happening (diagnosed, not guessed): the CDN host serving
video segments (e.g. `vd346.okcdn.ru`) sends only its leaf certificate
during the TLS handshake, omitting the intermediate certificate
("HARICA DV TLS ECC") needed to build a chain up to a root CA. The root
itself -- HARICA TLS ECC Root CA 2021 -- is a long-standing, publicly
trusted CA and *is* already in certifi's bundle. Browsers tolerate the
missing intermediate because they cache intermediates they've seen before
and/or fetch it automatically via the certificate's Authority Information
Access (AIA) extension. Python's `ssl` module (via certifi, which is what
this project's HTTPS calls use -- see acquire.py) does neither, so the
handshake fails with CERTIFICATE_VERIFY_FAILED even though the actual
chain of trust is legitimate.

The fix here is to supply the missing intermediate, not disable
certificate verification. Silently turning verification off would also
accept a genuinely malicious certificate; completing an otherwise-valid
chain does not. The intermediate below was fetched once from the
certificate's own AIA "CA Issuers" URL
(http://crt.harica.gr/HARICA-DV-TLS-Sub-E1.cer) and is embedded here so no
extra network round trip is needed at runtime, and so this doesn't depend
on that URL staying reachable.
"""

from __future__ import annotations

from pathlib import Path

import certifi

# NOTE: yt-dlp calls certifi.where() directly (see
# yt_dlp/networking/_helper.py::ssl_load_certs) rather than deferring to the
# SSL_CERT_FILE/SSL_CERT_DIR environment variables OpenSSL normally honors.
# Setting SSL_CERT_FILE (tried first, and left in place for every other
# library in this project that *does* respect it) has no effect on yt-dlp
# specifically. patch_certifi() below monkeypatches certifi.where() itself,
# which is the one call yt-dlp actually makes -- since Python module
# imports are singletons, every "import certifi; certifi.where()" anywhere
# in the process, including inside yt-dlp, resolves to the same patched
# function.

# Intermediate: "HARICA DV TLS ECC", issued by "HARICA TLS ECC Root CA 2021"
# (already trusted in certifi's bundle). Verified in approach.md section 13
# with `openssl x509 -in harica_sub.cer -noout -issuer -subject`.
_HARICA_DV_TLS_ECC_INTERMEDIATE = """-----BEGIN CERTIFICATE-----
MIIDczCCAvigAwIBAgIQYhFm53o2Wyr/+S7JIy1TaDAKBggqhkjOPQQDAzBsMQsw
CQYDVQQGEwJHUjE3MDUGA1UECgwuSGVsbGVuaWMgQWNhZGVtaWMgYW5kIFJlc2Vh
cmNoIEluc3RpdHV0aW9ucyBDQTEkMCIGA1UEAwwbSEFSSUNBIFRMUyBFQ0MgUm9v
dCBDQSAyMDIxMB4XDTIxMDMxOTA5MjIzM1oXDTM2MDMxNTA5MjIzMlowYjELMAkG
A1UEBhMCR1IxNzA1BgNVBAoMLkhlbGxlbmljIEFjYWRlbWljIGFuZCBSZXNlYXJj
aCBJbnN0aXR1dGlvbnMgQ0ExGjAYBgNVBAMMEUhBUklDQSBEViBUTFMgRUNDMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAE6CvSreH/yHFTsmv44Rd2eOYXiYeMsNpO3VXx
UpUqQyaetnuFwsl4cwzury4KmGPQA3e4zmpJ8L2CH3xJk+K6THlRWhRNcozi5c2b
O7HPgB50aaUugVkkQB1LxK/S9L8do4IBZzCCAWMwEgYDVR0TAQH/BAgwBgEB/wIB
ADAfBgNVHSMEGDAWgBTJG1OBEv4E1RbRqryab7eglRluyjBUBggrBgEFBQcBAQRI
MEYwRAYIKwYBBQUHMAKGOGh0dHA6Ly9yZXBvLmhhcmljYS5nci9jZXJ0cy9IQVJJ
Q0EtVExTLVJvb3QtMjAyMS1FQ0MuY2VyMEQGA1UdIAQ9MDswOQYEVR0gADAxMC8G
CCsGAQUFBwIBFiNodHRwOi8vcmVwby5oYXJpY2EuZ3IvZG9jdW1lbnRzL0NQUzAd
BgNVHSUEFjAUBggrBgEFBQcDAgYIKwYBBQUHAwEwQgYDVR0fBDswOTA3oDWgM4Yx
aHR0cDovL2NybC5oYXJpY2EuZ3IvSEFSSUNBLVRMUy1Sb290LTIwMjEtRUNDLmNy
bDAdBgNVHQ4EFgQU24IfMU5Hid4JfAqUY1QViGuWTZEwDgYDVR0PAQH/BAQDAgGG
MAoGCCqGSM49BAMDA2kAMGYCMQDcXjqcOyf4zkWBjPxkWSUfeUGlHlOXhZaqxDaL
pAq4pj2fEwx/W280rRXUs/a36zcCMQDJ7dvkYdtad4cTZW2fNatW2G5Gk7/noRbG
sp6wWwoAdOT3oVYa3hC4l4TYbtcVnTo=
-----END CERTIFICATE-----
"""

_KNOWN_MISSING_INTERMEDIATES = [_HARICA_DV_TLS_ECC_INTERMEDIATE]


def combined_ca_bundle() -> str:
    """Path to certifi's bundle plus the known-missing intermediate(s)
    above, built once and cached alongside certifi's own bundle file."""
    cache_path = Path(certifi.where()).with_name("cacert_plus_known_intermediates.pem")
    if not cache_path.exists():
        base = Path(certifi.where()).read_text(encoding="utf-8")
        extra = "\n".join(_KNOWN_MISSING_INTERMEDIATES)
        cache_path.write_text(base + "\n" + extra, encoding="utf-8")
    return str(cache_path)


_patched = False


def patch_certifi() -> None:
    """Make certifi.where() itself return the combined bundle, so callers
    that call it directly (yt-dlp) get the completed chain too, not just
    callers that respect SSL_CERT_FILE."""
    global _patched
    if _patched:
        return
    bundle = combined_ca_bundle()
    certifi.where = lambda: bundle
    _patched = True
