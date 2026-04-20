from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Sequence

from ..common import (
    TRIGGER_RECEIVER_IDENTITY,
    configure_logging,
    connect_secure_client,
    format_timestamp,
    load_server_settings,
    utc_now,
    write_datetime,
    write_int16,
)
from .shared import create_subscription_handler, resolve_nodes


LOGGER = logging.getLogger(__name__)


async def run_receiver(args) -> None:
    server_settings = load_server_settings(args.config)
    completed_cycles = 0

    async with connect_secure_client(TRIGGER_RECEIVER_IDENTITY, server_settings) as client:
        nodes = await resolve_nodes(client, server_settings.namespace_uri)
        subscription, handler = await create_subscription_handler(client, nodes, args.subscription_interval_ms)
        LOGGER.info("Receiver is waiting for Request=1")

        try:
            while args.cycles is None or completed_cycles < args.cycles:
                active_state = await handler.wait_for(
                    lambda state: state.request == 1 and state.acknowledge == 0,
                    "Request=1 while Acknowledge=0",
                    None,
                )
                acknowledge_timestamp = utc_now()
                await write_datetime(nodes.acknowledge_timestamp, acknowledge_timestamp)
                await write_int16(nodes.acknowledge, 1)
                await handler.set_local(acknowledge_timestamp=acknowledge_timestamp, acknowledge=1)
                LOGGER.info(
                    "Accepted request timestamp %s and set Acknowledge=1 at %s",
                    format_timestamp(active_state.request_timestamp),
                    format_timestamp(acknowledge_timestamp),
                )

                await handler.wait_for(
                    lambda state: state.request == 0 and state.acknowledge == 1,
                    "Request=0 while Acknowledge=1",
                    None,
                )
                await write_int16(nodes.acknowledge, 0)
                await handler.set_local(acknowledge=0)
                completed_cycles += 1
                LOGGER.info("Cycle %s: reset Acknowledge=0", completed_cycles)
        finally:
            await subscription.delete()


def parse_args(argv: Sequence[str] | None = None):
    parser = argparse.ArgumentParser(description="Trigger receiver example client.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).with_name("server.config.yaml"),
        help="Path to the example server config.",
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=None,
        help="How many cycles to process before exiting. Omit to run forever.",
    )
    parser.add_argument(
        "--subscription-interval-ms",
        type=float,
        default=100.0,
        help="Subscription publishing interval in milliseconds.",
    )
    parser.add_argument("--log-level", default="INFO", help="Receiver log level.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    try:
        asyncio.run(run_receiver(args))
        return 0
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())