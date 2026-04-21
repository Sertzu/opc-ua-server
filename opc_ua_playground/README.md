# OPC UA Playground

This directory contains runnable example clients that talk to the server in this repository.

## Layout

- `certs/server/`: shared server certificate and key for playground server configs
- `certs/client_identities/`: client certificates and private keys used by the examples
- `certs/clients/granted/`: copies of example client certificates that are already trusted by the server configs
- `certs/clients/rejected/`: where the server writes unknown client certificates if you remove them from `granted`

The example client certificates are pre-copied into `clients/granted` so the examples run immediately.
If you want to test the manual trust flow, remove a client certificate from `clients/granted`, start the server, and let that client connect once so its certificate lands in `clients/rejected`.

## Examples

- `trigger_return`: sender and receiver clients implementing a request and acknowledge cycle with timestamps
- `three_triggers`: master and slave clients running watchdog, material change, and material prediction trigger-return channels in parallel

Start the example server:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_server --config opc_ua_playground/trigger_return/server.config.yaml
```

Run the receiver:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.trigger_return.receiver --cycles 100
```

Run the sender:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.trigger_return.sender --cycles 10
```

Both clients now use OPC UA data change subscriptions for the trigger and acknowledge nodes instead of periodic polling.

Run the three-trigger slave:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.three_triggers.slave
```

Run the three-trigger master:

```bash
/home/spark/tools/opc-ua-server/.venv/bin/python -m opc_ua_playground.three_triggers.master
```