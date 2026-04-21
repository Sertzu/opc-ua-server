from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator, Callable, TypeVar

import yaml
from asyncua import Client, ua
from asyncua.crypto import security_policies


LOGGER = logging.getLogger(__name__)
PLAYGROUND_ROOT = Path(__file__).resolve().parent
CERTS_ROOT = PLAYGROUND_ROOT / "certs"
T = TypeVar("T")


@dataclass(slots=True)
class ClientIdentity:
    name: str
    application_uri: str
    certificate: Path
    private_key: Path


@dataclass(slots=True)
class ServerSettings:
    config_path: Path
    endpoint: str
    application_uri: str
    namespace_uri: str
    server_certificate: Path


TRIGGER_SENDER_IDENTITY = ClientIdentity(
    name="trigger_sender",
    application_uri="urn:example:opcua:playground:trigger-sender",
    certificate=CERTS_ROOT / "client_identities" / "trigger_sender_cert.pem",
    private_key=CERTS_ROOT / "client_identities" / "trigger_sender_key.pem",
)

TRIGGER_RECEIVER_IDENTITY = ClientIdentity(
    name="trigger_receiver",
    application_uri="urn:example:opcua:playground:trigger-receiver",
    certificate=CERTS_ROOT / "client_identities" / "trigger_receiver_cert.pem",
    private_key=CERTS_ROOT / "client_identities" / "trigger_receiver_key.pem",
)

THREE_TRIGGERS_MASTER_IDENTITY = ClientIdentity(
    name="three_triggers_master",
    application_uri="urn:example:opcua:playground:three-triggers:master",
    certificate=CERTS_ROOT / "client_identities" / "three_triggers_master_cert.pem",
    private_key=CERTS_ROOT / "client_identities" / "three_triggers_master_key.pem",
)

THREE_TRIGGERS_SLAVE_IDENTITY = ClientIdentity(
    name="three_triggers_slave",
    application_uri="urn:example:opcua:playground:three-triggers:slave",
    certificate=CERTS_ROOT / "client_identities" / "three_triggers_slave_cert.pem",
    private_key=CERTS_ROOT / "client_identities" / "three_triggers_slave_key.pem",
)


def configure_logging(level_name: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level_name.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("asyncua").setLevel(logging.WARNING)


def load_server_settings(config_path: Path) -> ServerSettings:
    resolved_config_path = config_path.resolve()
    raw_data = yaml.safe_load(resolved_config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Server config at {resolved_config_path} must be a mapping.")

    server_data = raw_data.get("server") or {}
    certificates_data = raw_data.get("certificates") or {}
    if not isinstance(server_data, dict) or not isinstance(certificates_data, dict):
        raise ValueError(f"Server config at {resolved_config_path} has an invalid structure.")

    certificates_root = _resolve_path(
        resolved_config_path.parent,
        str(certificates_data.get("root", "../certs")),
    )
    server_certificate = _resolve_path(
        certificates_root,
        str(certificates_data.get("server_certificate", "server/server_cert.pem")),
    )

    return ServerSettings(
        config_path=resolved_config_path,
        endpoint=str(server_data["endpoint"]),
        application_uri=str(server_data["application_uri"]),
        namespace_uri=str(server_data["namespace_uri"]),
        server_certificate=server_certificate,
    )


@asynccontextmanager
async def connect_secure_client(
    identity: ClientIdentity,
    server_settings: ServerSettings,
) -> AsyncIterator[Client]:
    client = Client(url=server_settings.endpoint)
    client.application_uri = identity.application_uri
    await client.set_security(
        security_policies.SecurityPolicyBasic256Sha256,
        identity.certificate,
        identity.private_key,
        server_certificate=server_settings.server_certificate,
        mode=ua.MessageSecurityMode.SignAndEncrypt,
    )

    connected = False
    try:
        await client.connect()
        connected = True
        yield client
    finally:
        if connected:
            await client.disconnect()


async def wait_for_value(
    node,
    predicate: Callable[[T], bool],
    description: str,
    poll_interval: float,
    timeout: float,
) -> T:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout if timeout > 0 else None

    while True:
        value = await node.read_value()
        if predicate(value):
            return value
        if deadline is not None and loop.time() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description}.")
        await asyncio.sleep(poll_interval)


async def write_int16(node, value: int) -> None:
    await node.write_value(ua.Variant(value, ua.VariantType.Int16))


async def write_double(node, value: float) -> None:
    await node.write_value(ua.Variant(value, ua.VariantType.Double))


async def write_string(node, value: str) -> None:
    await node.write_value(ua.Variant(value, ua.VariantType.String))


async def write_datetime(node, value: datetime) -> None:
    await node.write_value(ua.Variant(value, ua.VariantType.DateTime))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_timestamp(value: object) -> str:
    if value is None:
        return "<unset>"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _resolve_path(base: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate.resolve()
    return (base / candidate).resolve()