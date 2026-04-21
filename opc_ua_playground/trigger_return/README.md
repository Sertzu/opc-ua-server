# Trigger Return

This example contains two clients that exchange a request and acknowledge handshake through the OPC UA server.

## Cycle

1. Sender writes `Request = 1` and updates `RequestTimestamp`.
2. Receiver receives the `Request` data change through an OPC UA subscription, accepts the action, writes `AcknowledgeTimestamp`, and sets `Acknowledge = 1`.
3. Sender receives the `Acknowledge` data change through an OPC UA subscription and resets `Request = 0`.
4. Receiver receives the `Request = 0` data change and resets `Acknowledge = 0`.
5. Both clients are back at idle and ready for the next cycle.

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

Use `--subscription-interval-ms` on either client if you want a different publishing interval.# Trigger Return

This example contains two clients that exchange a request and acknowledge handshake through the OPC UA server.

## Cycle

1. Sender writes `Request = 1` and updates `RequestTimestamp`.
2. Receiver sees `Request = 1`, accepts the action, writes `AcknowledgeTimestamp`, and sets `Acknowledge = 1`.
3. Sender sees `Acknowledge = 1` and resets `Request = 0`.
4. Receiver sees `Request = 0` and resets `Acknowledge = 0`.
5. Both clients are back at idle and ready for the next cycle.

## Nodes

- `trigger_return.request`
- `trigger_return.request_timestamp`
- `trigger_return.acknowledge`
- `trigger_return.acknowledge_timestamp`

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

The shared certificates for both clients live under `opc_ua_playground/certs/client_identities/`.