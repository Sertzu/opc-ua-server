from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asyncua import ua
from asyncua.common.utils import ServiceError
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from opc_ua_server.certificates import ManualTrustCertificateValidator


def build_test_certificate(common_name: str = "Demo Client") -> x509.Certificate:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier("urn:test:opcua:client")]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    return certificate


class ManualTrustCertificateValidatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_certificate_is_written_to_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            granted_dir = Path(temp_dir) / "clients" / "granted"
            rejected_dir = Path(temp_dir) / "clients" / "rejected"
            granted_dir.mkdir(parents=True, exist_ok=True)
            rejected_dir.mkdir(parents=True, exist_ok=True)

            validator = ManualTrustCertificateValidator(granted_dir, rejected_dir)
            certificate = build_test_certificate()
            app_description = ua.ApplicationDescription()
            app_description.ApplicationUri = "urn:test:opcua:client"

            with self.assertRaises(ServiceError):
                await validator(certificate, app_description)

            rejected_files = list(rejected_dir.iterdir())
            self.assertEqual(len(rejected_files), 1)
            self.assertEqual(rejected_files[0].suffix, ".der")

    async def test_granted_certificate_is_accepted_without_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            granted_dir = Path(temp_dir) / "clients" / "granted"
            rejected_dir = Path(temp_dir) / "clients" / "rejected"
            granted_dir.mkdir(parents=True, exist_ok=True)
            rejected_dir.mkdir(parents=True, exist_ok=True)

            validator = ManualTrustCertificateValidator(granted_dir, rejected_dir)
            certificate = build_test_certificate()
            app_description = ua.ApplicationDescription()
            app_description.ApplicationUri = "urn:test:opcua:client"

            with self.assertRaises(ServiceError):
                await validator(certificate, app_description)

            rejected_file = next(rejected_dir.iterdir())
            granted_file = granted_dir / rejected_file.name
            granted_file.write_bytes(rejected_file.read_bytes())

            await validator(certificate, app_description)

            granted_certificate = x509.load_der_x509_certificate(granted_file.read_bytes())
            self.assertEqual(
                certificate.fingerprint(hashes.SHA256()),
                granted_certificate.fingerprint(hashes.SHA256()),
            )