from __future__ import annotations

import logging
import re
from pathlib import Path

from asyncua import ua
from asyncua.common.utils import ServiceError
from asyncua.crypto import uacrypto
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.oid import NameOID


LOGGER = logging.getLogger(__name__)
CERTIFICATE_SUFFIXES = {".der", ".pem", ".cer"}


def certificate_fingerprint(certificate: x509.Certificate) -> str:
    return certificate.fingerprint(hashes.SHA256()).hex()


def rejected_certificate_filename(certificate: x509.Certificate) -> str:
    fingerprint = certificate_fingerprint(certificate)
    common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    common_name = common_names[0].value if common_names else "unknown-client"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", common_name).strip("-") or "unknown-client"
    return f"{fingerprint}__{safe_name}.der"


class ManualTrustCertificateValidator:
    """Reject unknown client certificates until an operator grants them."""

    def __init__(self, granted_dir: Path, rejected_dir: Path):
        self.granted_dir = granted_dir
        self.rejected_dir = rejected_dir

    async def __call__(self, certificate: x509.Certificate, app_description: ua.ApplicationDescription) -> None:
        fingerprint = certificate_fingerprint(certificate)
        application_uri = app_description.ApplicationUri or "<missing-application-uri>"

        if await self._is_granted(certificate):
            LOGGER.info(
                "Accepted OPC UA client certificate %s for application URI %s",
                fingerprint,
                application_uri,
            )
            return

        rejected_path = self.rejected_dir / rejected_certificate_filename(certificate)
        if not rejected_path.exists():
            rejected_path.write_bytes(certificate.public_bytes(serialization.Encoding.DER))
            LOGGER.warning(
                "Rejected untrusted OPC UA client certificate %s from %s and wrote it to %s. "
                "Move that file into %s to grant future connections.",
                fingerprint,
                application_uri,
                rejected_path,
                self.granted_dir,
            )
        else:
            LOGGER.warning(
                "Rejected untrusted OPC UA client certificate %s from %s. It is already present at %s.",
                fingerprint,
                application_uri,
                rejected_path,
            )

        raise ServiceError(ua.StatusCodes.BadCertificateUntrusted)

    async def _is_granted(self, certificate: x509.Certificate) -> bool:
        expected_fingerprint = certificate_fingerprint(certificate)

        for granted_path in self._iter_certificate_files(self.granted_dir):
            trusted_certificate = await self._load_certificate(granted_path)
            if trusted_certificate is None:
                continue
            if certificate_fingerprint(trusted_certificate) == expected_fingerprint:
                return True

        return False

    async def _load_certificate(self, path: Path) -> x509.Certificate | None:
        try:
            return await uacrypto.load_certificate(path)
        except Exception as exc:
            LOGGER.warning("Skipping unreadable certificate file %s: %s", path, exc)
            return None

    @staticmethod
    def _iter_certificate_files(folder: Path) -> list[Path]:
        if not folder.exists():
            return []
        return sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and (path.suffix.lower() in CERTIFICATE_SUFFIXES or not path.suffix)
        )