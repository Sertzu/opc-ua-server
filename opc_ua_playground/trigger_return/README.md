# Trigger Return

This example contains two clients that exchange a request and acknowledge handshake through the OPC UA server.

## Cycle

1. Sender writes `Request = 1` and updates `RequestTimestamp`.
2. Receiver receives the `Request` data change through an OPC UA subscription, accepts the action, writes `AcknowledgeTimestamp`, and sets `Acknowledge = 1`.
3. Sender receives the `Acknowledge` data change through an OPC UA subscription and resets `Request = 0`.
4. Receiver receives the `Request = 0` data change and resets `Acknowledge = 0`.
5. Both clients are back at idle and ready for the next cycle.

## Nodes

- `trigger_return.request`
- `trigger_return.request_timestamp`
- `trigger_return.acknowledge`
- `trigger_return.acknowledge_timestamp`

## Implementations

- Python runtime example: `sender.py` and `receiver.py` use `asyncua` subscriptions and can be run directly.
- Unified Automation C++ SDK sketch: `unified_automation_cpp_sdk/` shows the same handshake using `UaSession`, `UaSessionCallback`, `UaSubscription`, and `UaSubscriptionCallback`. It is illustrative only and is not intended to compile as-is.

## Run

Start the server:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_server --config opc_ua_playground/trigger_return/server.config.yaml
```

Start the receiver:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.trigger_return.receiver --cycles 1
```

Start the sender:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.trigger_return.sender --cycles 1
```

Use `--subscription-interval-ms` on either Python client if you want a different publishing interval.

The shared certificates for both runtime clients live under `opc_ua_playground/certs/client_identities/`.