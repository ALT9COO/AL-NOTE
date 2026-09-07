"""Create a self-signed HTTPS cert covering localhost and LAN IPs."""

from __future__ import annotations

import datetime
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
CERT_DIR = ROOT / "frontend" / "certs"
CERT_PEM = CERT_DIR / "dev-cert.pem"
KEY_PEM = CERT_DIR / "dev-key.pem"
META = CERT_DIR / "sans.txt"


def lan_ips() -> list[str]:
    found: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in found:
                found.append(ip)
    except OSError:
        pass
    extra = [a.strip() for a in sys.argv[1:] if a.strip()]
    for ip in extra:
        try:
            parsed = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if parsed.is_loopback or parsed.is_link_local:
            continue
        text = str(parsed)
        if text not in found:
            found.append(text)
    return found


def san_lines(ips: list[str]) -> str:
    names = ["DNS:localhost", "IP:127.0.0.1"] + [f"IP:{ip}" for ip in ips]
    return "\n".join(sorted(set(names))) + "\n"


def main() -> None:
    ips = lan_ips()
    wanted = san_lines(ips)
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    if CERT_PEM.exists() and KEY_PEM.exists() and META.exists():
        if META.read_text(encoding="ascii") == wanted:
            return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    names: list[x509.GeneralName] = [
        x509.DNSName("localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    ]
    for ip in ips:
        names.append(x509.IPAddress(ipaddress.ip_address(ip)))

    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AL-Note")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365 * 5))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    KEY_PEM.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    CERT_PEM.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    META.write_text(wanted, encoding="ascii")


if __name__ == "__main__":
    main()
