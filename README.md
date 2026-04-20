# OPC UA Server

This repository contains a small asyncua-based OPC UA server that is configured from one YAML file at startup.

## What it does

- Loads endpoint settings, namespace information, and nodes from `config.yaml`.
- Requires secure OPC UA endpoints only. `NoSecurity` is intentionally disabled in this first version.
- Keeps `asyncua` framework logging at `WARNING` by default so normal startup and connection logs stay readable.
- Uses a manual certificate trust flow for client application certificates:
  - Unknown client certificates are written to `./certs/clients/rejected/`.
  - After an operator moves a certificate file into `./certs/clients/granted/`, that client can connect.
  - The granted directory is checked on each connection attempt, so a restart is not required after moving a file.
- Does not implement granular authorization in this version. Any granted client certificate is treated the same.

## Layout

At startup the app creates this directory structure under `certificates.root`:

```text
certs/
  server/
  clients/
    granted/
    rejected/
```

Place the server certificate and private key in `certs/server/` or update the paths in `config.yaml`.

## Server certificate

The server expects these files by default:

- `certs/server/server_cert.pem`
- `certs/server/server_key.pem`

One way to generate them is:

```bash
openssl req \
  -x509 \
  -newkey rsa:2048 \
  -keyout certs/server/server_key.pem \
  -out certs/server/server_cert.pem \
  -days 365 \
  -nodes \
  -subj "/CN=Configurable AsyncUA Server" \
  -addext "subjectAltName=DNS:localhost,URI:urn:example:configurable:opcua:server"
```

If you protect the key with a password, set `certificates.private_key_password_env` in the YAML and export that environment variable before startup.
If clients connect through a different hostname or IP, include matching DNS or IP subject alternative names in the certificate as well.

## Run

Validate the configuration without starting the server:

```bash
python -m opc_ua_server --config config.yaml --check-config
```

Start the server:

```bash
python -m opc_ua_server --config config.yaml
```

## YAML model

The `address_space.nodes` section supports `folder`, `object`, and `variable` entries.

The `logging` section supports:

- `level`: this application's log level
- `asyncua_level`: framework log level for the underlying asyncua library

Each node supports:

- `type`: `folder`, `object`, or `variable`
- `browse_name`: display name inside the OPC UA address space
- `node_id`: optional. If omitted, a string node id is generated from the path.
- `children`: allowed on folders and objects

Variables also support:

- `value`: initial value
- `variant_type`: optional asyncua variant type name such as `Boolean`, `Double`, `Int32`, or `String`
- `writable`: mark the variable writable for clients

## Notes

- This first version keeps user identity handling simple and uses the trusted client application certificate as the access gate.
- Unknown client certificates are saved as DER files so they can be moved directly from `rejected` to `granted`.

## Playground

Runnable client examples live under `opc_ua_playground/`.
The first example demonstrates a trigger and return trigger handshake with sender and receiver clients plus a dedicated server config.