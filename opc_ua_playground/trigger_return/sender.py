from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Sequence

from ..common import (
    TRIGGER_SENDER_IDENTITY,
    configure_logging,
    connect_secure_client,
    format_timestamp,
    load_server_settings,
    utc_now,
    write_datetime,
    write_int16,
)
from .shared import create_subscription_handler, resolve_nodes, wait_for_idle


LOGGER = logging.getLogger(__name__)


async def run_sender(args) -> None:
    server_settings = load_server_settings(args.config)

    async with connect_secure_client(TRIGGER_SENDER_IDENTITY, server_settings) as client:
        nodes = await resolve_nodes(client, server_settings.namespace_uri)
        subscription, handler = await create_subscription_handler(client, nodes, args.subscription_interval_ms)

        try:
            for cycle_number in range(1, args.cycles + 1):
                idle_state = await wait_for_idle(handler, args.timeout)
                previous_acknowledge_timestamp = idle_state.acknowledge_timestamp

                request_timestamp = utc_now()
                await write_datetime(nodes.request_timestamp, request_timestamp)
                await write_int16(nodes.request, 1)
                await handler.set_local(request_timestamp=request_timestamp, request=1)
                LOGGER.info(
                    "Cycle %s: set Request=1 at %s",
                    cycle_number,
                    format_timestamp(request_timestamp),
                )

                acknowledged_state = await handler.wait_for(
                    lambda state: state.acknowledge == 1
                    and state.acknowledge_timestamp != previous_acknowledge_timestamp,
                    "Acknowledge=1 with a new acknowledge timestamp",
                    args.timeout,
                )
                LOGGER.info(
                    "Cycle %s: observed Acknowledge=1 at %s",
                    cycle_number,
                    format_timestamp(acknowledged_state.acknowledge_timestamp),
                )

                await write_int16(nodes.request, 0)
                await handler.set_local(request=0)
                LOGGER.info("Cycle %s: reset Request=0", cycle_number)

                await wait_for_idle(handler, args.timeout)
                LOGGER.info("Cycle %s: handshake returned to idle", cycle_number)

                if cycle_number < args.cycles and args.pause_between_cycles > 0:
                    await asyncio.sleep(args.pause_between_cycles)
        finally:
            await subscription.delete()


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Trigger sender example client.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("server.config.yaml"),
        help="Path to the example server config.",
    )
    parser.add_argument("--cycles", type=int, default=1, help="How many trigger cycles to execute.")
    parser.add_argument(
        "--subscription-interval-ms",
        type=float,
        default=100.0,
        help="Subscription publishing interval in milliseconds.",
    )
    parser.add_argument(
        "--pause-between-cycles",
        type=float,
        default=0.5,
        help="Seconds to wait between cycles.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds for each handshake phase.",
    )
    parser.add_argument("--log-level", default="INFO", help="Sender log level.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        asyncio.run(run_sender(args))
        return 0
    except TimeoutError as exc:
        LOGGER.error(str(exc))
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())