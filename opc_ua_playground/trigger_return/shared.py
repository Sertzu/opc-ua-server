from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable

from asyncua import ua


REQUEST_NODE_ID = "trigger_return.request"
REQUEST_TIMESTAMP_NODE_ID = "trigger_return.request_timestamp"
ACKNOWLEDGE_NODE_ID = "trigger_return.acknowledge"
ACKNOWLEDGE_TIMESTAMP_NODE_ID = "trigger_return.acknowledge_timestamp"


@dataclass(slots=True)
class TriggerReturnNodes:
    request: object
    request_timestamp: object
    acknowledge: object
    acknowledge_timestamp: object


@dataclass(slots=True)
class TriggerReturnState:
    request: int = 0
    request_timestamp: datetime | None = None
    acknowledge: int = 0
    acknowledge_timestamp: datetime | None = None


async def resolve_nodes(client, namespace_uri: str) -> TriggerReturnNodes:
    namespace_index = await client.get_namespace_index(namespace_uri)
    return TriggerReturnNodes(
        request=client.get_node(ua.NodeId(REQUEST_NODE_ID, namespace_index)),
        request_timestamp=client.get_node(ua.NodeId(REQUEST_TIMESTAMP_NODE_ID, namespace_index)),
        acknowledge=client.get_node(ua.NodeId(ACKNOWLEDGE_NODE_ID, namespace_index)),
        acknowledge_timestamp=client.get_node(ua.NodeId(ACKNOWLEDGE_TIMESTAMP_NODE_ID, namespace_index)),
    )


class TriggerReturnSubscriptionHandler:
    def __init__(self, nodes: TriggerReturnNodes):
        self._nodes = nodes
        self._condition = asyncio.Condition()
        self._state = TriggerReturnState()
        self._field_by_nodeid = {
            nodes.request.nodeid: "request",
            nodes.request_timestamp.nodeid: "request_timestamp",
            nodes.acknowledge.nodeid: "acknowledge",
            nodes.acknowledge_timestamp.nodeid: "acknowledge_timestamp",
        }

    async def initialize(self) -> None:
        await self.set_local(
            request=int(await self._nodes.request.read_value()),
            request_timestamp=await self._nodes.request_timestamp.read_value(),
            acknowledge=int(await self._nodes.acknowledge.read_value()),
            acknowledge_timestamp=await self._nodes.acknowledge_timestamp.read_value(),
        )

    async def datachange_notification(self, node, val, _data) -> None:
        field_name = self._field_by_nodeid.get(node.nodeid)
        if field_name is None:
            return

        normalized_value = int(val) if field_name in {"request", "acknowledge"} else val
        await self.set_local(**{field_name: normalized_value})

    async def set_local(self, **values) -> None:
        async with self._condition:
            for field_name, value in values.items():
                setattr(self._state, field_name, value)
            self._condition.notify_all()

    async def snapshot(self) -> TriggerReturnState:
        async with self._condition:
            return replace(self._state)

    async def wait_for(
        self,
        predicate: Callable[[TriggerReturnState], bool],
        description: str,
        timeout: float | None,
    ) -> TriggerReturnState:
        async def _wait() -> TriggerReturnState:
            async with self._condition:
                while not predicate(self._state):
                    await self._condition.wait()
                return replace(self._state)

        if timeout is None or timeout <= 0:
            return await _wait()

        try:
            return await asyncio.wait_for(_wait(), timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"Timed out waiting for {description}.") from exc


async def create_subscription_handler(client, nodes: TriggerReturnNodes, interval_ms: float):
    handler = TriggerReturnSubscriptionHandler(nodes)
    subscription = await client.create_subscription(interval_ms, handler)
    await subscription.subscribe_data_change(
        [
            nodes.request,
            nodes.request_timestamp,
            nodes.acknowledge,
            nodes.acknowledge_timestamp,
        ],
        sampling_interval=interval_ms,
    )
    await handler.initialize()
    return subscription, handler


async def wait_for_idle(handler: TriggerReturnSubscriptionHandler, timeout: float) -> TriggerReturnState:
    return await handler.wait_for(
        lambda state: state.request == 0 and state.acknowledge == 0,
        "Request=0 and Acknowledge=0",
        timeout,
    )