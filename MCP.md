# YActivePRO MCP server — project-specific notes

Everything specific to the YActivePRO MCP server (`yactivepro_mcp.py`,
branch `mcp-server` of `mdeweerd/YActivePRO`) and its Active-Pro backend.
The generic MCP server rules live in the `mcp-server-development` skill;
this document carries only the project-specific material.

## Active-Pro Automation API (the backend)

- TCP port 37800+, autodetected at startup; reachability is reported in the
  `initialize` instructions and the HTTP banner.
- Older builds answer `ERROR UNRECOGNIZEDCOMMAND` for commands they do not
  implement (the trigger suite): verify every new tool mapping against the
  live app over the raw socket before shipping. A green selftest only
  proves the command string, not that the app accepts it.
- The app answers `OK`/`YES` on success, `NO` or `ERROR...` on failure;
  record side effects only on success.
- The application cursor is quantized to 0.1 ms, but `Search` is exclusive
  and advances past each match at full internal precision on its own. Do
  NOT move the cursor after a search: setting it to the returned (rounded)
  timestamp lands back on the same match. Callers setting the cursor
  manually to a returned timestamp should add 0.0001 s.
- Timestamps in answers are rounded to 4 decimals while events have ns
  resolution; never round-trip a displayed value back as an exact position.

## File tools (project policy)

- `read_file` read policy: anything under `/tmp`, plus paths the server
  itself wrote (persisted in a state file).
- Save/export write policy: under `/tmp` only `yapd_`-prefixed files may be
  overwritten; anywhere else the file must not exist yet. Enforced on the
  realpath before converting the path for the backend host (WSL/Windows).
- `read_back: true` returns the file content in the same answer; `offset` +
  `max_chars` page through large exports (offset counts chars for text,
  bytes for binary); binary answers are base64 behind a one-line
  `<path> (<N> bytes, base64):` header.
- Server-side post-processing of an export (`decoded_only`) can shrink
  files massively; run it after the backend write, before `read_back`.

## Configuration reference

- Env prefix `YAPD_MCP_*`: `HOST` (Active-Pro host), `BIND`, `HTTP_PORT`
  (default 37880), `PUBLIC_PORT`, `STATE_DIR` (default `yapd-mcp-state`),
  `SESSION_SECRET`, `SESSION_TTL_HOURS` (8), `OAUTH_ISSUER_URL`,
  `OAUTH_REFRESH_TTL_HOURS` (720), `FEEDBACK_FILE`.
- `POST /login` returns `{"token", ...}` — the field is `token`, not
  `access_token`.
- `--remote NAME` prints and starts the
  `ssh -N -o ExitOnForwardFailure=yes -R 0.0.0.1:<public>:127.0.0.1:<http>`
  tunnel using an `~/.ssh/config` host alias.

## OAuth version history (this server)

- v0.5.12: default HTTP port 37880.
- v0.5.13: SSE on GET /mcp, 401 + WWW-Authenticate on unauthenticated GET
  (was 404), streamable HTTP on POST, protocol version negotiation.
- v0.5.14: benign client disconnects silenced in the error handler.
- v0.5.15: `/token` accepts urlencoded and JSON bodies; an omitted
  `redirect_uri` is accepted in the code exchange. Context: LM Studio posts
  a JSON body and omits `redirect_uri`; both were rejected (400) before,
  and since authorization codes are single-use the client hung after its
  loopback callback. A provided `redirect_uri` still match exactly (RFC
  6749).

## Deployment and exposure

- Repository: `mdeweerd/YActivePRO`, branch `mcp-server`. Push in one
  commit, then verify byte-exact remotely: `get_file_contents`
  blob_id/size/execute_filemode against the local git blob sha1
  (`hashlib.sha1(b'blob %d\0' % len(data) + data)`).
- Style gates: black-compatible lines ≤ 79, no trailing whitespace, EOF
  newline; README wrapped at 75 (four legacy env-table rows excepted).
- Public endpoint: https://SUBDOMAIN/mcp. Chain: OPNsense HAProxy (tcp SNI
  frontend → HTTPS frontend, first-match host map file) → backend
  `SUBDOMAIN` → the reverse tunnel on the docker host (192.168.0.190:37880,
  bound by sshd) → `ssh -R` from the machine running the server.
- Map entry `SUBDOMAIN SUBDOMAIN`; the backend contains exactly one server
  (192.168.0.190:37880). `/healthz` at the root; no path prefix anywhere
  (the /.well-known documents live at the host root).
- On the tunnel target sshd: `GatewayPorts clientspecified`
  (/etc/ssh/sshd_config.d), otherwise the 0.0.0.0 bind is silently ignored
  and the port stays on loopback.
- `YAPD_MCP_OAUTH_ISSUER_URL=https://SUBDOMAIN` — no path suffix; the
  issuer is the host root.
- LM Studio client specifics: dynamic registration, loopback callback
  `http://127.0.0.1:<port>/mcp-oauth-callback` (RFC 8252), JSON token
  requests without redirect_uri (tolerated since v0.5.15).
- Incident 2026-11-10: intermittent wrong-backend responses through HAProxy
  were two haproxy processes with different in-memory configs sharing the
  listener (stale process after a reload); HAProxy never caches. Diagnosed
  by repeated curls to the same URL plus TLS cert serial and
  response-header fingerprints; fixed by a full restart.
