from datetime import datetime, timezone

from tabulate import tabulate


def _rel(ts_str: str) -> str:
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        s = int((datetime.now(timezone.utc) - ts).total_seconds())
        if s < 0:
            return f"in {-s}s"
        if s < 60:
            return f"{s}s ago"
        if s < 3600:
            return f"{s // 60}m ago"
        if s < 86400:
            return f"{s // 3600}h ago"
        return f"{s // 86400}d ago"
    except Exception:
        return ts_str or "-"


def _enrollment_status(allow_to_str: str) -> str:
    try:
        allow_to = datetime.fromisoformat(allow_to_str)
        if allow_to.tzinfo is None:
            allow_to = allow_to.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > allow_to:
            return "expired"
        return "open"
    except Exception:
        return "?"


def print_client_table(clients: list[dict]) -> None:
    if not clients:
        print("No clients registered.")
        return
    rows = []
    for c in clients:
        rows.append([
            c["id"],
            _enrollment_status(c.get("allow_to", "")),
            c.get("allow_to", "-"),
            "yes" if c.get("fingerprint") else "no",
            _rel(c.get("created_at", "")),
        ])
    print(tabulate(rows,
                   headers=["UUID", "Enrollment", "Allow-to (UTC)", "Cert", "Created"],
                   tablefmt="simple"))


def print_connected_table(rows: list[dict]) -> None:
    if not rows:
        print("No clients currently connected.")
        return
    data = [
        [r["client_id"], r.get("ip", "-"), _rel(r.get("last_seen", ""))]
        for r in rows
    ]
    print(tabulate(data, headers=["Client ID", "IP", "Last seen"], tablefmt="simple"))


def print_client_detail(client: dict, cert: dict | None, state: dict | None) -> None:
    print(f"Client ID   : {client['id']}")
    print(f"Created     : {client['created_at']}")
    enroll = _enrollment_status(client.get("allow_to", ""))
    print(f"Allow-to    : {client['allow_to']}  [{enroll}]")

    print()
    if cert:
        print("Certificate")
        print(f"  Fingerprint (SHA-256) : {cert['fingerprint']}")
        print(f"  Issued at             : {cert['approved_at']}")
        _print_cert_fields(cert["certificate"])
    else:
        print("Certificate : not issued")

    print()
    if state:
        print("Live state (Memcached)")
        print(f"  Status    : {state.get('status', '-')}")
        print(f"  IP        : {state.get('ip', '-')}")
        print(f"  Last seen : {state.get('last_seen', '-')}  [{_rel(state.get('last_seen', ''))}]")
    else:
        print("Live state  : unavailable (Memcached unreachable or client never connected)")


def _print_cert_fields(pem: str) -> None:
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_pem_x509_certificate(pem.encode(), default_backend())
        print(f"  Subject               : {cert.subject.rfc4514_string()}")
        print(f"  Issuer                : {cert.issuer.rfc4514_string()}")
        print(f"  Valid from            : {cert.not_valid_before_utc}")
        print(f"  Valid until           : {cert.not_valid_after_utc}")
        san_ext = None
        try:
            san_ext = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
        except x509.ExtensionNotFound:
            pass
        if san_ext:
            names = ", ".join(str(n.value) for n in san_ext.value)
            print(f"  SAN                   : {names}")
    except Exception as exc:
        print(f"  (could not parse certificate: {exc})")
