import ssl

from .config import config


def build_server_ssl_context() -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=config.server_cert, keyfile=config.server_key)
    ctx.load_verify_locations(cafile=config.ca_cert)
    # CERT_OPTIONAL: enrollment clients connect without a client cert;
    # persistent clients present one. Both share this single port and context.
    # The application layer (handler.py) checks getpeercert() to route accordingly.
    ctx.verify_mode = ssl.CERT_OPTIONAL
    return ctx
