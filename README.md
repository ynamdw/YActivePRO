# YActiveProApi

A set of tools by Ynamics for the Active-PRO Automation API.

## ActiveProApi.py

This script provides a command-line interface (CLI) to access the
[Active-PRO Automation API](https://www.activefirmwaretools.com/usersmanualold/main-window-d9b4x).
It allows you to control the Active-PRO application through simple commands
you can further automate.

### Features

- Connect to the Active-PRO application.
- Send commands to control the Active-PRO application.
- Receive responses from the Active-PRO application.
- Run demonstration code to test the API.

### Usage

To use the script, simply run it from the command line with the desired
command-line arguments.

The `ActiveProApi.py` script has a help option, and provides a
bash-completion script as well.

### Example Scripts

Note: The scripts suppose that `ActiveProApi.py` is present in the working
directory.

#### Export the last 10 minutes of a capture

The `exportActive10min.sh` bash script demonstrates how to export the last
10 minutes of a capture.

#### Export a range of captured data

The `exportAfterLoadAndZoom.sh` bash script demonstrates how to export a
specific range of captured data, after start the debugger and zooming.

## yactivepro_mcp.py (MCP server)

`yactivepro_mcp.py` is an MCP server (JSON-RPC 2.0, Python standard library
only) that gives an AI assistant the background knowledge for Active-PRO
work and direct access to the Active-PRO application:

- `get_skills`: embedded knowledge, one topic per call (`aft`, `adp`,
  `automation`); no arguments gives the overview and the topic list.
- `get_docs`: fetches a page of the official user manual as plain text, for
  example the [.aft format specification]
  (https://www.activefirmwaretools.com/usersmanualold/aft-format); no
  arguments lists the known pages.
- `feedback`: records a suggestion from the AI client (missing
  documentation, an idea for an additional tool) as a timestamped entry in
  `$YAPD_MCP_STATE_DIR/feedback.md` (`YAPD_MCP_FEEDBACK_FILE` overrides),
  for the maintainer to read.
- One tool per command of the Active-PRO Automation API (`start_capture`,
  `stop_capture`, `set_cursor_x1`, `zoom_from`, `export_between_cursors`,
  `list_instances`, ...), with the same semantics as `ActiveProApi.py`:
  negative times are relative to the capture end, file paths get their
  default extension (`.active`, `.csv`, `.png`) and are resolved for
  WSL/Cygwin. The tool list is the command reference.
- `read_file`: read back a file on the server machine, e.g. the .csv
  written by `export_between_cursors`, the .aft written by
  `export_ai_snapshot` or the .png written by `save_screenshot` (text files
  as bare text - no wrapper line, so the answer can be saved as-is, with a
  trailing `[read_file: ...]` note only when `offset`/truncation applies;
  other files base64-encoded; binary answers are standard base64 (RFC 4648)
  behind a one-line `<path> (<N> bytes, base64):` header). `read_file`
  takes `offset` (characters for text, bytes for binary) plus `max_chars`
  for chunked reads of large exports. The save/export tools also take
  `read_back: true` (plus `max_chars`/`offset`) to return the written
  file's content in the same tool answer, without a separate `read_file`
  call; `export_ai_snapshot` and `export_between_cursors` additionally take
  `decoded_only: true` to drop the logic/analog rows and write decoded
  device data only. `search` moves past each match itself and re-finds
  inside the same decoded item are skipped server-side, so repeated calls
  enumerate all occurrences one hit each (do not move the cursor between
  calls); the returned timestamp is rounded to 0.1 ms, so when setting the
  cursor manually to a returned value, add 0.0001 s to skip that match.
- `export_ai_snapshot`: `ExportAISnapshotBetweenCursors` - export the AI
  Snapshot (.aft firmware trace, decoded data + Analysis Context) of the
  X1/X2 range; read it back with `read_file`.
- `append_analysis_context` / `get_analysis_context` /
  `clear_analysis_context`: the briefing written into every exported .aft
  snapshot.
- further Automation API commands documented in the user manual and
  ACTIVE_PRO_MCP.md: `get_note`, `get_analog`, `get_devices_attached`,
  `select_device`, `get_cursor`, `set_theme`, `show_triggers`, `show_code`,
  `show_liveui`, `show_devices`.
- trigger suite and post-capture pipeline: `set_trigger_mode`,
  `set_trigger_source_type`, `set_trigger_channel`,
  `set_trigger_condition`, `set_trigger_threshold`,
  `set_trigger_pulse_width`, `set_trigger_text`, trigger navigation
  (`next_trigger`, `goto_trigger`, `center_trigger`, ...), `apply_changes`
  / `is_processing` / `cancel_processing`, `reprocess_triggers`.
- buffer and pre/post-trigger retention: `set_buffer_size`,
  `set_pre_trigger_mode`, `set_pre_trigger_seconds`,
  `set_post_trigger_mode`, `set_post_trigger_seconds`,
  `set_post_trigger_triggers` (with their getters).
- channel and device configuration: `logic_channel_on_off`,
  `analog_channel_on_off`, `set_threshold_level`, `set_label`,
  `set_device_mode`, `set_device_setting`, `set_device_visibility`.

File-writing tools (`export_between_cursors`, `save_screenshot`,
`save_capture`, `save_between_cursors`, `save_configuration`) enforce a
write policy: under `/tmp` only files prefixed with `yapd_` may be
overwritten (use e.g. `/tmp/yapd_export.csv`); any other path is only
writable when the file does not exist yet. `read_file` accepts any path
under `/tmp` plus paths previously written by those tools (persisted in
`$YAPD_MCP_STATE_DIR/written_files.json`).

Exports between the X1/X2 cursors answer with the range actually exported
(`exported range X1=... X2=...`; `zoom_from` changes the view only, it does
not move the cursors). The export tools also take `decoded_only` (drop the
logic/analog rows) and `device_filter` (keep only the listed rows: `.csv`
Device column, e.g. `device_filter=UART_PACKETS` for packet transaction
rows only; `.aft` source letter). The raw export written by
`export_between_cursors` encodes non-printable bytes as `[HH]` hex markers
and packet ends as `=EoP`; the server corrects the .csv file in place
(decodes them to the character or a `\r`/`\n`/`\xHH` escape); disable with
`--no-correct-csv-export` (or `YAPD_MCP_CORRECT_CSV_EXPORT=0`). `search`
takes an optional `from` timestamp: the search starts there and the shared
cursor is restored afterwards, so repeated or parallel searches are
independent; it scans the decoded device rows (packet presenter text), not
the raw byte rows.

On startup and on every new MCP connection (`initialize`), the server
probes the Active-Pro application and reports its reachability in the
`instructions` of the initialize response; the HTTP startup banner shows
the same status line.

Built-in checks (no network needed):

```bash
./yactivepro_mcp.py --selftest
```

### Run (self-contained, pipx)

The shebang runs the script through pipx (`pipx run --path`), and a PEP 723
block declares the dependencies, so an executable copy runs directly with
pipx 1.4+ resolving them into a cached environment:

```bash
./yactivepro_mcp.py --http --port 37880
```

Without the executable bit, use pipx run:

```bash
pipx run yactivepro_mcp.py
```

Force a dependency refresh with `pipx run --no-cache yactivepro_mcp.py`.

### stdio mode (default)

```bash
./yactivepro_mcp.py
```

No authentication; use it with any local stdio MCP client.

### Configuration example (any stdio MCP client)

The script is its own command (shebang; needs the executable bit):

```json
{
  "mcpServers": {
    "yactivepro": {
      "command": "/path/to/YActivePRO/yactivepro_mcp.py"
    }
  }
}
```

### HTTP mode (OAuth 2.1)

```bash
./yactivepro_mcp.py --http --port 37880
```

By default the server listens on `127.0.0.1`; `--bind ADDRESS` (overrides
`YAPD_MCP_BIND`) selects the bind address, for example `--bind 0.0.0.0` to
listen on every interface. A non-loopback bind prints a warning: the
endpoint is then reachable from the network and the consent-page
credentials are the only protection.

Two HTTP transports are served on `/mcp`. Streamable HTTP clients (POST
with `Accept: application/json`) get the JSON answer in the POST response.
Legacy HTTP+SSE clients open the `GET /mcp` event stream (it starts with an
`endpoint` event pointing at `/mcp`); a POST made with
`Accept: text/event-stream` is answered on that stream as a `message`
event. A browser GET of `/mcp` without a token returns 401 with the OAuth
challenge; `/healthz` is the unauthenticated liveness check.

HTTP mode embeds a small OAuth 2.1 authorization server: RFC 9728
protected-resource metadata (401 responses point clients at
`/.well-known/oauth-protected-resource/mcp`; the unsuffixed URL is served
too), RFC 8414 AS metadata at `/.well-known/oauth-authorization-server`
(also aliased as `/.well-known/openid-configuration`), RFC 7591 dynamic
client registration (`/register`, persisted across restarts in
`$YAPD_MCP_STATE_DIR/oauth_clients.json`) and PKCE S256 authorization-code
plus refresh-token grants (`/authorize`, `/token`). All responses carry
CORS headers and `OPTIONS` preflights are answered, so browser-based
clients can use the endpoints; `DELETE /mcp` with a valid token terminates
the session. `POST /token` accepts a urlencoded form or a JSON body, and
the `redirect_uri` parameter may be omitted in the code exchange (the URI
stored with the code was validated against the client registry at
`/authorize` time); a provided `redirect_uri` must still match exactly.
Access tokens are HMAC-signed sessions; `POST /login` with the printed
username and password returns a token for quick tests.

At startup the server prints the consent-page credentials (username,
password) and the endpoint URLs. The credentials are persisted in
`$YAPD_MCP_STATE_DIR/credentials.json` (mode 0600) and reused on the next
starts, and the HMAC session secret is persisted alongside, so session
tokens and OAuth refresh tokens survive a restart. Renew with
`--reset-credentials`: it deletes the stored credentials and session
secret, and fresh ones are created on the next `--http`/`--remote` start
(immediately when combined with one of them).

### Remote mode (ssh reverse tunnel)

```bash
./yactivepro_mcp.py --remote myvps
```

The server stays bound to `127.0.0.1` and starts the ssh reverse tunnel
itself as a child process, printing the command it runs (the connection
details for `myvps` come from `~/.ssh/config`):

```bash
ssh -N -R 0.0.0.0:37880:127.0.0.1:37880 myvps
```

Notes:

- A publicly bound `-R` port needs `GatewayPorts clientspecified` (or
  `yes`) in `sshd_config` on the remote host; without it the forwarded port
  stays on the remote loopback.
- No `ExitOnForwardFailure`: forwardings inherited from `~/.ssh/config`
  (e.g. a catch-all `Host *` `RemoteForward` stanza) may fail when the port
  is already taken on the remote; that must not abort the tunnel when the
  MCP port itself bound fine. ssh still prints a
  `Warning: remote port forwarding failed for listen port N` line for every
  failed forward, including the MCP port if that is the one that failed.
- Cloud MCP clients need https: put the usual TLS reverse proxy on the
  remote host and set `YAPD_MCP_OAUTH_ISSUER_URL` (or rely on
  `X-Forwarded-*` headers).
- Ctrl+C (or SIGTERM) stops the server and the tunnel together. If ssh
  exits immediately (wrong host name, missing key), the server keeps
  serving locally and reports the exit code.

### Ssh credentials (not handled by the server)

The server does not handle, store, or prompt for the ssh login credentials
of the remote host: `--remote NAME` only runs ssh, and ssh resolves NAME
through the regular client configuration, `~/.ssh/config`. Use key-based
login without a passphrase (or an ssh agent), otherwise ssh prompts in the
terminal at every start, and the tunnel waits for it.

Add the tunnel target to `~/.ssh/config` with an alias; the alias is the
name passed to `--remote`:

```sshconfig
# ~/.ssh/config
Host myvps
    HostName 203.0.113.10
    User deploy
    Port 22
    IdentityFile ~/.ssh/id_ed25519_myvps
```

With this entry, `--remote myvps` connects as `deploy` at `203.0.113.10`
with that key, and the alias also works for a plain `ssh myvps`. Test the
login first with `ssh myvps` (then `exit`): the server reports it if ssh
cannot connect.

### Active-Pro host (WSL)

The Active-Pro application must be reachable from where the scripts run.
Under WSL the Windows host is not `localhost`: find its IP (often the
default gateway, `ip route show default`) and give it to the scripts:

```bash
./yactivepro_mcp.py --host 172.20.16.1
# or, once for both scripts:
export YAPD_MCP_HOST=172.20.16.1
```

`YAPD_MCP_HOST` is the default host of both `yactivepro_mcp.py` (`--host`)
and `ActiveProApi.py` (`--host`), so one export covers the server and the
CLI. When nothing answers on localhost and WSL is detected, the server
prints this hint at startup. The export tool paths are converted for the
Windows application (`wslpath`), and they refer to the machine running
Active-Pro.

### Environment variables

| Variable                           | Default                    | Meaning                                           |
| ---------------------------------- | -------------------------- | ------------------------------------------------- |
| `YAPD_MCP_HOST`                    | `localhost`                | Active-Pro host, both scripts (WSL: Windows IP)   |
| `YAPD_MCP_BIND`                    | `127.0.0.1`                | HTTP bind address (--bind overrides)              |
| `YAPD_MCP_HTTP_PORT`               | `37880`                    | HTTP port (--port overrides)                      |
| `YAPD_MCP_PUBLIC_PORT`             | HTTP port                  | tunnel port in the ssh suggestion                 |
| `YAPD_MCP_STATE_DIR`               | `yapd-mcp-state`           | state: OAuth clients, credentials, session secret |
| `YAPD_MCP_SESSION_SECRET`          | random, persisted          | HMAC key of session tokens                        |
| `YAPD_MCP_OAUTH_ISSUER_URL`        | auto                       | public URL in OAuth metadata                      |
| `YAPD_MCP_SESSION_TTL_HOURS`       | `8`                        | access token lifetime                             |
| `YAPD_MCP_OAUTH_REFRESH_TTL_HOURS` | `720`                      | refresh token lifetime                            |
| `YAPD_MCP_FEEDBACK_FILE`           | `feedback.md` in state dir | feedback Markdown file                            |
| `YAPD_MCP_CORRECT_CSV_EXPORT`      | `1` (on)                   | correct the exported .csv ([HH]/=EoP markers)     |

## Disclaimer

This project is shared as a courtesy. Pull requests are accepted, but
support will be limited.

## Affiliation

Ynamics is not affiliated with Active Firmware Tools. This repository is
not an endorsement of Active Firmware Tools nor its products.

## NOTICE

https://www.ynamics.com

This product includes software developed by
[Ynamics](https://www.ynamics.com) - 50 rue de Pontoise - 95870 BEZONS -
France.

Licensed under the Apache License, Version 2.0 (the "License"); you may not
use this file except in compliance with the License. You may obtain a copy
of the License at

https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations
under the License.
