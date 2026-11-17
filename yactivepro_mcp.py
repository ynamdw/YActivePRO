#!/usr/bin/env -S pipx run --path
# PYTHON_ARGCOMPLETE_OK
"""
Provides an MCP server for the Active-Pro application.

Tools: get_skills and get_docs (Active-Pro knowledge and the official
user manual), plus one tool per command of the Active-Pro Automation
API (see ActiveProApi.py).

Transports:
  stdio (default, local, no authentication)
  HTTP  (--http or --remote, Bearer token or OAuth 2.1 with an
         embedded authorization server): streamable HTTP (POST
         /mcp, JSON answers) and the older HTTP+SSE transport
         (GET /mcp opens the event stream)

With --remote NAME, the credentials of the consent page and an ssh -R
command are printed locally; ~/.ssh/config holds the credentials of
NAME.

Usage (self-contained; the dependencies are declared in the PEP 723
block near the top of this file, and the shebang runs pipx):
  ./yactivepro_mcp.py [options]         (shebang: pipx run --path,
                                          pipx 1.4+ in PATH)
  pipx run yactivepro_mcp.py [options]  (same, without needing the
                                          executable bit)

@copyright Copyright (c) 2026 Ynamics SARL - France
@license Apache License, Version 2.0
@link https://www.ynamics.com/
@author MDW / YNAMICS

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# pylint: disable=too-many-lines,pointless-string-statement

# /// script
# requires-python = ">=3.8"
# dependencies = ["argcomplete"]
# ///

import argparse
import base64
import csv
import hashlib
import hmac
import html
import http.client
import json
import os
import queue
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

VERSION = "0.5.23"
SERVER_NAME = "yactivepro-mcp"
# MCP protocol versions are date-stamped specification revisions, not
# the server's build date; the newest spec release is 2025-11-25.
MCP_PROTOCOL_VERSION = "2025-11-25"
# initialize answers an older requested protocol version when the
# client asks for one that is supported (legacy HTTP+SSE clients)
SUPPORTED_PROTOCOL_VERSIONS = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
DOCS_BASE = "https://www.activefirmwaretools.com/usersmanualold/"
DEFAULT_MAX_CHARS = 20000


def env(name: str, default: str = "") -> str:
    """Read an environment variable, empty or unset falls back."""
    value = os.environ.get(name)
    return default if value is None or value == "" else value


CONF: Dict[str, Any] = {
    "app_host": env("YAPD_MCP_HOST", "localhost"),
    "correct_csv_export": env("YAPD_MCP_CORRECT_CSV_EXPORT", "1").lower()
    not in ("0", "false", "no", "off"),
    "bind": env("YAPD_MCP_BIND", "127.0.0.1"),
    "http_port": int(env("YAPD_MCP_HTTP_PORT", "37880")),
    "public_port": int(env("YAPD_MCP_PUBLIC_PORT", "0")),
    "session_secret": env("YAPD_MCP_SESSION_SECRET"),
    "session_ttl_h": float(env("YAPD_MCP_SESSION_TTL_HOURS", "8")),
    "oauth_issuer": env("YAPD_MCP_OAUTH_ISSUER_URL").rstrip("/"),
    "oauth_refresh_ttl_h": float(
        env("YAPD_MCP_OAUTH_REFRESH_TTL_HOURS", "720")
    ),
    "oauth_clients_file": os.path.join(
        env("YAPD_MCP_STATE_DIR", "yapd-mcp-state"), "oauth_clients.json"
    ),
    "credentials_file": os.path.join(
        env("YAPD_MCP_STATE_DIR", "yapd-mcp-state"), "credentials.json"
    ),
    "session_secret_file": os.path.join(
        env("YAPD_MCP_STATE_DIR", "yapd-mcp-state"), "session_secret"
    ),
    "written_files_file": os.path.join(
        env("YAPD_MCP_STATE_DIR", "yapd-mcp-state"), "written_files.json"
    ),
    "feedback_file": env(
        "YAPD_MCP_FEEDBACK_FILE",
        os.path.join(
            env("YAPD_MCP_STATE_DIR", "yapd-mcp-state"), "feedback.md"
        ),
    ),
    "oauth_code_ttl_s": 600,
}

# ------------------------------------------------------------- knowledge

# Known manual pages: stable key -> (slug, title). The slugs of the site
# are not stable, the keys are; they are verified on 2026-11-09.
PAGES = {
    "aft-format": ("aft-format", "The .aft Format (trace format spec)"),
    "overview": ("overview-1", "Overview"),
    "getting-started": ("getting-started", "Getting Started"),
    "license-agreement": ("license-agreement", "License Agreement"),
    "safety-guidelines": ("main-window-dr6f3", "Safety Guidelines"),
    "devices": ("main-window-5skjp", "Devices"),
    "main-window": ("main-window-6fn6j", "Main Window"),
    "channels-and-signals": ("main-window-clwkz", "Channels and Signals"),
    "capture": ("main-window-dbk49", "Capture"),
    "waveform-view": ("main-window-g23z4", "Waveform View"),
    "buffers-and-triggers": ("triggers", "Buffers & Triggers"),
    "markers": ("main-window-jgz58-hr26b", "Markers"),
    "adp-firmware-integration": (
        "main-window-stbtg",
        "Active Debug Port - Firmware Integration",
    ),
    "notifications-from-firmware": (
        "notifications-from-firmware",
        "Notifications from Firmware",
    ),
    "ai-snapshot": ("main-window-amxnk", "AI Snapshot"),
    "protocol-decoding": ("main-window-nxh86", "Protocol Decoding"),
    "custom-decoders": ("custom-decoders", "Custom Decoders"),
    "packetpresenter": ("main-window-24hr5", "PacketPresenter"),
    "source-code-integration": (
        "main-window-nr5t4",
        "Source Code Integration",
    ),
    "automation-api": ("main-window-d9b4x", "Automation API"),
}

# Upstream URL quirks: this page is served under a misspelled slug on
# activefirmwaretools.com (the correctly spelled slug 404s). PAGES
# keeps the correct spelling; page_url repairs the fetch URL.
SLUG_FIXUPS: Dict[str, str] = {"license-agreement": "liscence-agreement"}

# The second line of every .aft export is this fixed descriptor; it
# is one physical line in real exports (kept unwrapped so the worked
# example in the aft skill stays byte-faithful to the specification).
_AFT_FIXED_LINE = (
    "Timestamped firmware debug capture. Sources: embedded devices, "
    "logic, analog — interleaved chronologically. Analyze as a "
    "firmware engineer.\n"
)

SKILLS: Dict[str, str] = {
    "overview": """\
YActivePRO / Active-Pro Debugger knowledge base.

Every command of the Active-Pro application API is exposed as its own
MCP tool (start_capture, stop_capture, is_capturing, zoom_from,
export_between_cursors, export_ai_snapshot, ...); the tool list is the
command reference.

Call get_skills again with a "topic" argument for the details:
- aft: the .aft firmware trace format - header block, sections, event
  rows, quoting rules, and a complete worked example. Read this
  before analyzing an .aft trace.
- adp: the Active Debug Port wire protocol - packets, ACTIVEValue /
  ACTIVEText encoding, UART / SPI / GPIO modes.
- automation: the Active-Pro tool workflow - time conventions,
  cursors and zoom, exports (.csv, .png, .active), capture lifecycle.
  Read this before using the Active-Pro tools.

get_docs fetches the official user manual as plain text; call it
without arguments for the page list (the aft-format and
automation-api pages hold the full specifications behind the aft and
automation topics).""",
    "aft": """\
.aft - Active Firmware Trace format (v1.5)

Plain-text, UTF-8 trace of what a running firmware did, exported by
the Active-Pro application to the clipboard ("Copy AI Snapshot" /
Ctrl+C on a selected time range; nothing is written to disk). It is
not the .active binary capture and not the .csv export.

Structure:
1. Header block:
   - two fixed first lines ("Active-Pro Firmware Trace (.aft)" plus a
     fixed descriptor line);
   - [ANALYSIS CONTEXT]: freeform briefing from the engineer, read it
     first;
   - [DEVICE SOURCES]: "code, label" rows - A/B/C/D (capture devices:
     an Active Debug Port device or a bus decoder), AN (analog),
     L (logic);
   - [DEVICE A/B/C/D CHANNELS], [LOGIC CHANNELS], [ANALOG CHANNELS]:
     "number, label" rows, only for visible channels; empty sections
     are omitted entirely.
2. The line ---DATA--- on its own line.
3. Event data: column header "timestamp, source, channel, data", then
   one row per event, all sources interleaved, sorted by timestamp.
   A window export (X1/X2) may prepend one context row per channel:
   the last event before the window. Its timestamp is smaller than
   the window start (X1) - treat rows with timestamp < X1 as context,
   not as in-window events.

Row fields:
- timestamp: seconds since capture start, 9 decimal places.
- source: A, B, C, D, AN or L.
- channel: 0..63 per device, bit index 0..7 for L, channel index for
  AN.
- data: see below.

Data field content:
- device (A-D): human-readable text ("state=IDLE"), decoded bus
  traffic ("START addr=0x48 W ACK"), or a numeric value; mixed-mode
  channels emit both, tell them apart by the content.
- AN: sampled value with its engineering unit appended ("1.24V",
  "142mA").
- L: change-only rows, value 0 or 1; a stable signal produces no row.

Quoting (CSV-like): no comma in the data -> unquoted; comma present ->
wrapped in double quotes; a double quote inside a quoted field is
escaped by doubling it. Parse rule: split on the first three commas,
everything after the third is the data field; if it starts with a
double quote, strip the outer quotes and unescape doubled quotes.
Lines starting with # are comments, ignore them anywhere.

Analysis method: read [ANALYSIS CONTEXT] first, build the
source+channel -> label map from the legend sections, then read the
rows chronologically; the device labels are firmware variable, state
machine and log names.

Worked example (complete, from the official specification; note the
quoted data field, the mixed text and numeric rows on channel A/1,
the change-only logic rows, and the sensor NACK at 0.000817000 while
MOTOR_EN is high):

Active-Pro Firmware Trace (.aft)
"""
    + _AFT_FIXED_LINE
    + """\
[ANALYSIS CONTEXT]
Investigating intermittent I2C NACK failures on sensor board.
Failure rate roughly 1 in 50 transactions, appears correlated with
motor activity. Board is rev D.
[DEVICE SOURCES]
A, ADP
B, I2C Decoder
AN, ANALOG
L, LOGIC
[DEVICE A CHANNELS]
0, fw_state
1, i2c_retry_count
2, motor_cmd
5, error_flags
[DEVICE B CHANNELS]
0, I2C Bus
[LOGIC CHANNELS]
0, MOTOR_EN
[ANALOG CHANNELS]
0, VCC_3V3
1, MOTOR_CURRENT_mA
---DATA---
timestamp, source, channel, data
0.000100000, A, 0, state=INIT
0.000102340, AN, 0, 3.31V
0.000102340, AN, 1, 0mA
0.000105000, L, 0, 0
0.000200000, A, 0, state=SENSOR_POLL
0.000201000, B, 0, START addr=0x48 W ACK
0.000209000, B, 0, DATA 0x01 ACK
0.000217000, B, 0, RESTART addr=0x48 R ACK
0.000225000, B, 0, DATA 0xFF ACK
0.000233000, B, 0, STOP
0.000234000, A, 1, 0
0.000300000, A, 0, state=MOTOR_START
0.000301000, A, 2, cmd=FORWARD speed=128
0.000302000, L, 0, 1
0.000400000, AN, 0, 3.29V
0.000400000, AN, 1, 203mA
0.000800000, A, 0, state=SENSOR_POLL
0.000801000, B, 0, START addr=0x48 W ACK
0.000809000, B, 0, DATA 0x01 ACK
0.000817000, B, 0, RESTART addr=0x48 R NACK
0.000818000, A, 0, state=I2C_ERROR
0.000818500, A, 5, "err=I2C_NACK, retry=1"
0.000819000, A, 1, 1
0.000820000, B, 0, STOP
0.000900000, AN, 0, 3.28V
0.000900000, AN, 1, 211mA
0.001400000, A, 2, cmd=STOP
0.001401000, L, 0, 0
0.001550000, AN, 0, 3.31V
0.001600000, A, 0, state=SENSOR_POLL
0.001601000, B, 0, START addr=0x48 W ACK
0.001609000, B, 0, DATA 0x01 ACK
0.001617000, B, 0, RESTART addr=0x48 R ACK
0.001625000, B, 0, DATA 0xFF ACK
0.001633000, B, 0, STOP
0.001634000, A, 1, 0

Full specification: get_docs {"page": "aft-format"}.""",
    "adp": """\
Active Debug Port (ADP) wire protocol

How instrumented firmware talks to an Active-Pro capture device.

Transports:
- 1-wire UART: 8N1, any exact divide-down of 30 MHz (3,000,000 baud
  typical).
- 2-wire SPI: up to 40 MHz, fastest mode (~1.75 us per ACTIVEValue()
  call at 33 MHz).
- 2-wire GPIO: bit-banged CLOCK/DATA lines, MSB first.

Packet (max 255 bytes):
- byte 0: sync 0x7F, every packet starts with it.
- byte 1: bits 7-6 packet type (00 = value, 01 = text), bits 5-0
  channel number 0..63.

Value packet (ACTIVEValue):
- payload: base-64 variable-length integer, 6 bits per byte in the
  low bits, the MSB (0x40) is the continuation flag (0 = more bytes
  follow, 1 = last byte); positive and negative values.

Text packet (ACTIVEText):
- ASCII data, null terminator; non-printable characters escaped as
  \\a \\b \\t \\n \\r or \\xHH.

SWV compatibility: SWV output carries 2 bytes per character, Active-Pro
reads the ADP data from the second byte only.

In an .aft export, the decoded output of ADP devices appears on device
channels (sources A-D). Firmware-side integration details:
get_docs {"page": "adp-firmware-integration"}.""",
    "automation": """\
Active-Pro tools: workflow, conventions, exports

The Active-Pro application must run on the machine running this
server (under WSL: on the Windows host, reached through --host or
YAPD_MCP_HOST); each tool sends one command to it and returns its
answer ("YES"/"NO", a value), or fails as a tool error (application
not reachable, or the application answered an error). When tools
report the application as not reachable, call list_instances to see
what is actually up.

Time conventions (set_cursor_current, set_cursor_x1, set_cursor_x2,
zoom_from):
- times are seconds since the capture start; a negative time counts
  back from the capture end: set_cursor_x1 -600 with set_cursor_x2 0
  selects the last 10 minutes of the capture.
- get_capture_time gives the capture duration, get_capture_size the
  number of samples captured.

Exports - the way to hand data over for analysis:
The export range is always the X1/X2 cursors: set them with
set_cursor_x1/set_cursor_x2 (zoom_from frames the view only, it does
not move the cursors), and every export answer echoes the range
actually exported ("exported range X1=... X2=...").
- export_between_cursors: .csv of the data between the X1/X2 cursors.
  The .csv has three row levels in the Device column: UART_PACKETS
  transaction rows (e.g. 'TX=AT+CRESET[D]=EoP'), decoded text rows
  per device channel, and raw byte rows (columns: Seconds, Output,
  Device, Channel). For the decoded serial transactions, use this
  .csv - not the .aft, which is the byte-level trace. The raw export
  encodes non-printable bytes as [HH] hex markers and packet ends as
  =EoP; the server decodes those markers in the written file (disable
  with --no-correct-csv-export).
- save_between_cursors: same range as a .active capture file;
  save_capture writes the whole capture; open_capture loads one back
  (a running capture is stopped first).
- save_screenshot: .png of the current view.
- export_ai_snapshot: the AI Snapshot (.aft firmware trace) of the
  X1/X2 range - byte-level, one row per event ("timestamp, source,
  channel, data"), plus the Analysis Context; read the .aft back
  with read_file (text). The .aft and the .csv are different formats:
  .aft is the byte-level trace, .csv carries the transaction/decoded/
  byte row levels described above.
- save_configuration / open_configuration: save/load the .active
  configuration file.
- append_analysis_context / get_analysis_context /
  clear_analysis_context: the briefing written into every .aft
  snapshot (test name, firmware version, what to investigate) - set
  it before an automated run.
- export_ai_snapshot and export_between_cursors take decoded_only=true
  to write only the decoded device rows (A-D); the logic/analog rows
  are dropped from the file, which makes AI analysis much cheaper.
  device_filter="LABEL,..." keeps only the listed rows instead:
  .csv filters on the Device column (e.g. device_filter=UART_PACKETS
  keeps only the packet transaction rows), .aft on the source letter
  (A-D). The answer reports how many rows were dropped; the count is
  per format (.aft: L/AN source rows, .csv: LOGIC/ANALOG device rows),
  so the two formats report different counts for the same range.
  A window .aft export may still start with one context row per
  channel (the last event before X1; timestamp < X1).
File paths are used on the machine running the Active-Pro
application. Writes are restricted: under /tmp only yapd_-prefixed
files may be overwritten (use e.g. /tmp/yapd_export.csv or
/tmp/yapd_snapshot.aft); any other path is only writable when the
file does not exist yet. Set read_back=true on the save/export tool
to get the file content in the same answer (text for .csv and .aft,
base64 for .png, truncated at max_chars); without it, read the export
back with read_file, which accepts any path under /tmp or a path
written by a save/export tool. Text content comes back bare - no
wrapper line - so the answer can be saved as-is; a trailing
"[read_file: ...]" note appears only when offset or truncation
applies. Binary files come as a one-line header
"<path> (<N> bytes, base64):" followed by standard base64 (RFC 4648),
so strip the header before base64 -d. Page through large text exports
with offset (characters) + max_chars; for binary files offset counts
bytes.

Find, then inspect: search returns the timestamp of a string in the
decoded device data (packet presenter rows; strings that exist only
in raw byte rows return NOTFOUND); consecutive search calls enumerate
all occurrences (the application moves past each match itself, at
full internal precision - do not move the cursor between calls;
re-finds inside the same decoded item are skipped server-side, so one
occurrence returns one hit). The returned timestamp is rounded to
0.1 ms, so when you set_cursor_current to a returned timestamp
manually, add 0.0001 s to skip that match. Pass from=<timestamp> to
search from a given time without touching the shared cursor (it is
restored after the call), which makes repeated or parallel searches
independent. Give a timestamp to set_cursor_current or use it in
a zoom_from range to frame the moment, then export.

Triggers and the post-capture pipeline: set_trigger_mode /
set_trigger_source_type / set_trigger_channel /
set_trigger_condition / set_trigger_threshold (plus
set_trigger_pulse_width and set_trigger_text for the matching
conditions) configure the trigger; is_triggered, get_trigger_count
and the navigation tools (next_trigger, prev_trigger, first_trigger,
last_trigger, goto_trigger, get/set_trigger_cursor, center_trigger)
walk the fired triggers. set_buffer_size, set_pre_trigger_mode /
set_pre_trigger_seconds and set_post_trigger_mode /
set_post_trigger_seconds / set_post_trigger_triggers control how much
is kept around a trigger. apply_changes re-runs the decoder /
packet-presenter / trigger pipeline over the captured buffer
(blocking; poll is_processing, cancel with cancel_processing),
reprocess_triggers re-scans with the trigger settings only.

Channel and device configuration: logic_channel_on_off and
analog_channel_on_off switch capture channels, set_threshold_level
sets the digital threshold, set_label renames a logic/analog channel
or a device port, set_device_mode / set_device_setting pick the
decoder mode and rate of a device port (A-D), set_device_visibility
shows or hides a device's rows.

Zoom and cursors change the view, not the captured data; the export
range is the X1/X2 cursors regardless of the zoom. new_capture clears
for a fresh recording; the capture note (append_note, clear_note,
show_notes) carries the remarks to remember. exit closes the
application.

The full command reference behind the tools:
get_docs {"page": "automation-api"}.""",
}


class _TextExtractor(HTMLParser):
    """Collect the visible text of an HTML page."""

    _SKIP = frozenset({"script", "style", "noscript", "svg", "iframe"})
    _BLOCK = frozenset(
        {
            "p",
            "div",
            "br",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "pre",
            "table",
            "section",
            "article",
            "ul",
            "ol",
        }
    )

    def __init__(self) -> None:
        """Initialize the extractor."""
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        """Start of a tag: break the line on block tags."""
        # pylint: disable=unused-argument
        if tag in self._SKIP:
            self._skip += 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        """End of a tag: break the line on block tags."""
        if tag in self._SKIP and self._skip:
            self._skip -= 1
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        """Text content: keep it unless inside a skipped block."""
        if not self._skip:
            self.parts.append(data)


def html_to_text(html_source: str) -> str:
    """Extract the visible text of an HTML page."""
    extractor = _TextExtractor()
    extractor.feed(html_source)
    text = "".join(extractor.parts)
    # invisible characters (soft hyphen, zero-width, BOM) would block
    # the blank-line collapsing below
    text = re.sub(r"[\u00ad\u200b\u200c\u200d\u2060\ufeff]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    # Cookie-consent boilerplate at the top of every page of the site
    text = re.sub(
        r"By using this website.*?privacy policy\.\s*",
        "",
        text,
        count=1,
        flags=re.S,
    )
    return text.strip()


# Navigation boilerplate repeated around every page of the manual site
_NAV_LINES = frozenset(
    {
        "Skip to Content",
        "Open Menu",
        "Close Menu",
        "Download",
        "User's Manual",
        "Blog",
        "About",
        "Store",
        "Buy Now",
    }
)


def clean_site_text(text: str) -> str:
    """Drop the site navigation boilerplate around the page content."""
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped in _NAV_LINES:
            continue
        if re.match(r"^Active-Pro .* pre-orders", stripped):
            continue  # site-wide promotion banner
        kept.append(line)
    # removing the navigation lines leaves blank separators behind
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept))


def page_url(page: str) -> str:
    """Resolve a page key or a full URL to the URL to fetch."""
    if page.startswith("http"):
        if "activefirmwaretools.com" not in page:
            raise ValueError("only activefirmwaretools.com URLs are fetched")
        return page
    if page not in PAGES:
        raise ValueError(
            "unknown page: %s (call get_docs without arguments to "
            "list the known pages)" % page
        )
    slug = PAGES[page][0]
    return DOCS_BASE + SLUG_FIXUPS.get(slug, slug)


def page_list() -> str:
    """List the known manual pages (get_docs without arguments)."""
    lines = ["Known get_docs pages (key: title):"]
    lines += [
        "- {}: {}".format(key, title)
        for key, (_, title) in sorted(PAGES.items())
    ]
    lines.append(
        "A full activefirmwaretools.com URL is accepted too. "
        "Summaries: get_skills."
    )
    return "\n".join(lines)


def fetch_doc(page: str, max_chars: int) -> str:
    """Fetch one manual page and return its text."""
    url = page_url(page)
    request = urllib.request.Request(
        url, headers={"User-Agent": "YActivePRO-mcp/%s" % VERSION}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = clean_site_text(
                html_to_text(response.read().decode("utf-8", "replace"))
            )
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError("fetch failed for {}: {}".format(url, exc)) from exc
    if len(text) > max_chars:
        text = "%s\n[truncated at %d of %d characters; raise max_chars]" % (
            text[:max_chars],
            max_chars,
            len(text),
        )
    return "source: {}\n\n{}\n\nMore: get_skills for a summary, get_docs \
without arguments for the page list.".format(url, text)


def record_feedback(text: str) -> str:
    """Append one feedback entry to the feedback Markdown file."""
    path = CONF["feedback_file"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        if os.path.getsize(path) == 0:
            fh.write(
                "# YActivePRO MCP server feedback\n\n"
                "Entries appended by the feedback tool of connected "
                "LLM clients.\n"
            )
        fh.write(
            "\n## %s\n\n%s\n"
            % (time.strftime("%Y-%m-%d %H:%M:%S"), text.strip())
        )
    return "feedback recorded in %s" % path


# ------------------------------------------------- Active-Pro application

MODE_MAP_D = {"tristate": 0, "0v": 1, "3.3v": 2, "pwm": 3}
MODE_MAP_A0 = {
    "tristate": 0,
    "0v": 1,
    "1v": 2,
    "2v": 3,
    "3v": 4,
    "3.3v": 5,
    "dc": 6,
}
MODE_MAP_A1 = {
    **MODE_MAP_A0,
    "ramp": 7,
    "sine": 8,
    "square": 9,
    "triangle": 10,
}

MODE_TOOLS = {
    "set_d0_mode": (MODE_MAP_D, "SetD0Mode"),
    "set_d1_mode": (MODE_MAP_D, "SetD1Mode"),
    "set_a0_mode": (MODE_MAP_A0, "SetA0Mode"),
    "set_a1_mode": (MODE_MAP_A1, "SetA1Mode"),
}

TIME_TOOLS = {
    "set_cursor_current": "SetCursorCurrent",
    "set_cursor_x1": "SetCursorX1",
    "set_cursor_x2": "SetCursorX2",
    "set_trigger_cursor": "SetTriggerCursor",
}

PATH_TOOLS = {
    "open_capture": ".active",
    "save_capture": ".active",
    "save_between_cursors": ".active",
    "open_configuration": ".active",
    "save_configuration": ".active",
    "export_between_cursors": ".csv",
    "export_ai_snapshot": ".aft",
    "save_screenshot": ".png",
}

COMMANDS = {
    "hello": "Hello",
    "is_connected": "isConnected",
    "start_capture": "StartCapture",
    "stop_capture": "StopCapture",
    "is_capturing": "isCapturing",
    "get_capture_size": "GetCaptureSize",
    "get_capture_time": "GetCaptureTime",
    "get_logic": "GetLogic",
    "get_ch1": "GetCH1",
    "get_ch2": "GetCH2",
    "get_ch3": "GetCH3",
    "set_d0_pwm": "SetD0PWM {percent}",
    "set_d1_pwm": "SetD1PWM {percent}",
    "set_a0_dc_level": "SetA0DCLEVEL {volts}",
    "set_a1_dc_level": "SetA1DCLEVEL {volts}",
    "set_a1_minimum": "SetA1MINIMUM {volts}",
    "set_a1_maximum": "SetA1MAXIMUM {volts}",
    "set_a1_steps": "SetA1Steps {steps}",
    "clear_note": "ClearNote",
    "append_note": "AppendNote {text}",
    "get_note": "GetNote",
    "clear_analysis_context": "ClearAnalysisContext",
    "append_analysis_context": "AppendAnalysisContext {text}",
    "get_analysis_context": "GetAnalysisContext",
    "search": "Search {text}",
    "zoom_all": "ZoomAll",
    "show_inputs": "ShowInputs",
    "show_outputs": "ShowOutputs",
    "show_list": "ShowList",
    "show_settings": "ShowSettings",
    "show_notes": "ShowNotes",
    "show_triggers": "ShowTriggers",
    "show_code": "ShowCode",
    "show_liveui": "ShowLiveUI",
    "show_devices": "ShowDevices",
    "close_tabs": "CloseTabs",
    "new_capture": "NewCapture",
    "get_devices_attached": "GetDevicesAttached",
    "select_device": "SelectDevice {index}",
    "get_analog": "GetCH{channel}",
    # post-capture pipeline (ApplyChanges/ReprocessTriggers block until
    # done: they get TOOL_TIMEOUTS)
    "apply_changes": "ApplyChanges",
    "is_processing": "IsProcessing",
    "cancel_processing": "CancelProcessing",
    # trigger status and navigation
    "is_triggered": "IsTriggered",
    "get_trigger_count": "GetTriggerCount",
    "get_trigger_index": "GetTriggerIndex",
    "get_trigger_cursor": "GetTriggerCursor",
    "next_trigger": "NextTrigger",
    "prev_trigger": "PrevTrigger",
    "first_trigger": "FirstTrigger",
    "last_trigger": "LastTrigger",
    "goto_trigger": "GoToTrigger {index}",
    "center_trigger": "CenterTrigger",
    "reprocess_triggers": "ReprocessTriggers",
    # trigger configuration
    "set_trigger_mode": "SetTriggerMode {mode}",
    "get_trigger_mode": "GetTriggerMode",
    "set_trigger_source_type": "SetTriggerSourceType {source}",
    "get_trigger_source_type": "GetTriggerSourceType",
    "set_trigger_channel": "SetTriggerChannel {channel}",
    "get_trigger_channel": "GetTriggerChannel",
    "get_trigger_channel_list": "GetTriggerChannelList",
    "set_trigger_condition": "SetTriggerCondition {condition}",
    "get_trigger_condition": "GetTriggerCondition",
    "set_trigger_threshold": "SetTriggerThreshold {value}",
    "get_trigger_threshold": "GetTriggerThreshold",
    "set_trigger_pulse_width": "SetTriggerPulseWidth {value} {unit}",
    "get_trigger_pulse_width": "GetTriggerPulseWidth",
    "set_trigger_text": "SetTriggerText {text}",
    "get_trigger_text": "GetTriggerText",
    # buffer size and pre/post-trigger
    "set_buffer_size": "SetBufferSize {megabytes}",
    "get_buffer_size": "GetBufferSize",
    "set_pre_trigger_mode": "SetPreTriggerMode {mode}",
    "get_pre_trigger_mode": "GetPreTriggerMode",
    "set_pre_trigger_seconds": "SetPreTriggerSeconds {seconds}",
    "get_pre_trigger_seconds": "GetPreTriggerSeconds",
    "set_post_trigger_mode": "SetPostTriggerMode {mode}",
    "get_post_trigger_mode": "GetPostTriggerMode",
    "set_post_trigger_seconds": "SetPostTriggerSeconds {seconds}",
    "get_post_trigger_seconds": "GetPostTriggerSeconds",
    "set_post_trigger_triggers": "SetPostTriggerTriggers {count}",
    "get_post_trigger_triggers": "GetPostTriggerTriggers",
    # channel and device configuration
    "set_threshold_level": "ThresholdLevel {voltage}",
    "exit": "Exit",
    # path tools: the path is appended by run_api_tool
    "open_capture": "OpenCapture",
    "save_capture": "SaveCapture",
    "save_between_cursors": "SaveBetweenCursors",
    "open_configuration": "OpenConfiguration",
    "save_configuration": "SaveConfiguration",
    "export_between_cursors": "ExportBetweenCursors",
    "export_ai_snapshot": "ExportAISnapshotBetweenCursors",
    "save_screenshot": "SaveScreenshot",
}

# cursor readback and theme need a small argument -> command mapping
CURSOR_GET_COMMANDS = {
    "current": "GetCursorCurrent",
    "x1": "GetCursorX1",
    "x2": "GetCursorX2",
}
THEME_COMMANDS = {"dark": "SetDarkMode", "light": "SetLightMode"}

# channel on/off and device commands need the argument transformed
# (On/Off suffix, upper-case port letter) before formatting
ON_OFF_TOOLS = {
    "logic_channel_on_off": "LogicCH{channel}",
    "analog_channel_on_off": "AnalogCH{channel}",
}
DEVICE_TOOLS = {
    "set_device_mode": "Device{device}Mode {mode}",
    "set_device_setting": "Device{device}Setting {value}",
}

# blocking pipeline commands get a long socket timeout (server.py uses
# 600 s for the same commands)
TOOL_TIMEOUTS = {"apply_changes": 600, "reprocess_triggers": 600}
DEFAULT_TIMEOUT = 10


def _posix_absolute_path(path: str, default_extension: str = "") -> str:
    """Absolute local path, default extension added."""
    if default_extension and not os.path.splitext(path)[1]:
        path += default_extension
    return os.path.abspath(path)


def _app_path(absolute: str) -> str:
    """Convert a local absolute path for the Active-Pro application:
    Windows path under WSL/Cygwin (as in ActiveProApi.py)."""
    if os.name == "nt":
        return absolute
    helper = None
    if "CYGWIN" in os.environ:
        helper = ["cygpath", "-w", absolute]
    elif "WSL_DISTRO_NAME" in os.environ:
        helper = ["wslpath", "-w", absolute]
    if helper:
        result = subprocess.run(
            helper, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    return absolute


def get_absolute_path(path: str, default_extension: str = "") -> str:
    """Absolute path for the app, default extension added, Windows path
    under WSL/Cygwin."""
    return _app_path(_posix_absolute_path(path, default_extension))


# Tools that write a file (export/save): the write policy below applies.
# The open_* tools only make the application read a file.
WRITE_PATH_TOOLS = frozenset(
    {
        "save_capture",
        "save_between_cursors",
        "save_configuration",
        "export_between_cursors",
        "export_ai_snapshot",
        "save_screenshot",
    }
)

# Tools whose exported range is the X1/X2 cursors: on success the answer
# echoes the range actually exported (zoom_from changes the view only,
# it does not move the cursors).
CURSOR_RANGE_TOOLS = frozenset(
    {"export_between_cursors", "export_ai_snapshot", "save_between_cursors"}
)

# Export tools that take the decoded_only/device_filter row filters.
EXPORT_FILTER_TOOLS = frozenset(
    {"export_ai_snapshot", "export_between_cursors"}
)

# Extensions returned as text by the read_file tool; anything else is
# returned base64-encoded.
READ_TEXT_EXTENSIONS = frozenset(
    {".csv", ".txt", ".log", ".md", ".json", ".aft"}
)
READ_TEXT_MAX_CHARS = 200000
READ_BINARY_MAX_BYTES = 2 * 1024 * 1024
# Search answers are rounded to 0.1 ms; re-finds of the same decoded
# item (the application advances the cursor only ~0.1 ms past a match)
# within one quantum of the last reported hit are skipped, so one
# occurrence returns one hit.
SEARCH_DEDUP_QUANTUM = 0.0001


def _tmp_root() -> str:
    """The scratch root of this machine (realpath, symlink-safe)."""
    if os.name == "nt":
        return os.path.realpath(os.path.expandvars("%TEMP%"))
    return os.path.realpath("/tmp")


def _is_under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def check_write_path(
    path: str, default_extension: str = "", tmp_root: str = ""
) -> str:
    """Absolute local path after enforcing the write policy.

    A save/export may write under the scratch root (/tmp), where only
    files prefixed with yapd_ may be overwritten; anywhere else the
    file must not exist yet. Returns the realpath (traversal-safe).
    """
    absolute = os.path.realpath(_posix_absolute_path(path, default_extension))
    root = os.path.realpath(tmp_root) if tmp_root else _tmp_root()
    if _is_under(absolute, root):
        if os.path.exists(absolute) and not os.path.basename(
            absolute
        ).startswith("yapd_"):
            raise ValueError(
                "under %s only files prefixed with yapd_ may be "
                "overwritten: %s" % (root, absolute)
            )
    elif os.path.exists(absolute):
        raise ValueError(
            "refusing to overwrite an existing file outside %s: %s"
            % (root, absolute)
        )
    return absolute


def load_written_files() -> set:
    """Paths written through the save/export tools (persisted)."""
    try:
        with open(CONF["written_files_file"], encoding="utf-8") as fh:
            data = json.load(fh)
        return set(data) if isinstance(data, list) else set()
    except (ValueError, OSError):
        return set()


def record_written_file(path: str) -> None:
    """Remember a path written through a save/export tool, so the
    read_file tool can read it back (even outside /tmp)."""
    files = load_written_files()
    if path in files:
        return
    files.add(path)
    target = CONF["written_files_file"]
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(sorted(files), fh, ensure_ascii=False, indent=2)
    os.replace(tmp, target)


def check_read_path(path: str, tmp_root: str = "") -> str:
    """Absolute local path after enforcing the read policy: anything
    under the scratch root (/tmp), or a file written through a
    save/export tool. Returns the realpath."""
    absolute = os.path.realpath(os.path.abspath(path))
    root = os.path.realpath(tmp_root) if tmp_root else _tmp_root()
    if _is_under(absolute, root) or absolute in load_written_files():
        return absolute
    raise ValueError(
        "reading is limited to %s and to files written by the "
        "save/export tools: %s" % (root, absolute)
    )


def read_file(path: str, arguments: Dict[str, Any]) -> str:
    """Read back an exported/saved file for the MCP client: text files
    as text (from char offset, truncated at max_chars), other files as
    base64 (from byte offset)."""
    if not path:
        raise ValueError("path is required")
    absolute = check_read_path(path)
    if not os.path.isfile(absolute):
        raise ValueError("no such file: %s" % absolute)
    size = os.path.getsize(absolute)
    offset = max(0, int(arguments.get("offset") or 0))
    extension = os.path.splitext(absolute)[1].lower()
    if extension in READ_TEXT_EXTENSIONS:
        max_chars = int(arguments.get("max_chars") or DEFAULT_MAX_CHARS)
        max_chars = max(100, min(max_chars, READ_TEXT_MAX_CHARS))
        with open(absolute, encoding="utf-8", errors="replace") as fh:
            if offset:
                fh.read(offset)  # skip the first offset chars
            text = fh.read(max_chars + 1)
        truncated = len(text) > max_chars
        body = text[:max_chars]
        if offset or truncated:
            # trailing note only: a prefix wrapper line gets copied into
            # deliverables when an agent saves the answer as-is
            body += "\n[read_file: %s (%d bytes%s%s)]" % (
                absolute,
                size,
                ", from char %d" % offset if offset else "",
                ", truncated at %d chars" % max_chars if truncated else "",
            )
        return body
    if size - offset > READ_BINARY_MAX_BYTES:
        raise ValueError(
            "file too large to return as base64 from offset %d "
            "(%d bytes remain > %d): %s"
            % (offset, size - offset, READ_BINARY_MAX_BYTES, absolute)
        )
    with open(absolute, "rb") as fh:
        if offset:
            fh.seek(offset)
        data = fh.read(READ_BINARY_MAX_BYTES)
    encoded = base64.b64encode(data).decode()
    at = ", from byte %d" % offset if offset else ""
    return "%s (%d bytes%s, base64):\n%s" % (absolute, size, at, encoded)


# Source/device labels of the raw (non-decoded) rows in exports.
RAW_SOURCES_AFT = frozenset({"L", "AN"})
RAW_DEVICES_CSV = frozenset({"LOGIC", "ANALOG", "AN"})


def _filter_rows_aft(
    path: str, drop_raw: bool = True, keep: Optional[frozenset] = None
) -> int:
    """Rewrite an .aft export in place: drop data rows whose source is
    a raw L/AN row (drop_raw) or not listed in `keep` (when given).
    Header sections and the column header are kept. Returns the number
    of dropped rows."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    dropped = 0
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        in_data = False
        for line in lines:
            if line.strip() == "---DATA---":
                in_data = True
                fh.write(line)
                continue
            if in_data:
                parts = line.split(",", 3)
                if len(parts) >= 4:
                    source = parts[1].strip()
                    if (drop_raw and source in RAW_SOURCES_AFT) or (
                        keep is not None and source not in keep
                    ):
                        dropped += 1
                        continue
            fh.write(line)
    os.replace(tmp, path)
    return dropped


def _filter_rows_csv(
    path: str, drop_raw: bool = True, keep: Optional[frozenset] = None
) -> int:
    """Rewrite an exported .csv in place: drop rows whose Device column
    is LOGIC/ANALOG/AN (drop_raw) or not listed in `keep` (when given).
    Returns the number of dropped rows."""
    with open(path, newline="", encoding="utf-8", errors="replace") as src:
        rows = list(csv.reader(src))
    dropped = 0
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        for index, row in enumerate(rows):
            if index and len(row) >= 4:  # row 0 is the header, keep it
                device = row[2].strip()
                if (drop_raw and device in RAW_DEVICES_CSV) or (
                    keep is not None and device not in keep
                ):
                    dropped += 1
                    continue
            writer.writerow(row)
    os.replace(tmp, path)
    return dropped


# The raw .csv export encodes non-printable bytes as [HH] hex markers
# and packet ends as =EoP; the export tool corrects the written file in
# place (CLI: --no-correct-csv-export disables this).
_CSV_HEX_BYTE = re.compile(r"\[([0-9A-Fa-f]{1,2})\]")


def _decode_csv_export_text(text: str) -> str:
    """Decode the markers of a raw Active-Pro .csv export: [HH] hex
    byte markers become the printable character (a double quote is
    doubled, as CSV requires) or a \\r / \\n / \\xHH escape, and =EoP
    (end of packet) becomes \\n."""

    def repl(match):
        value = int(match.group(1), 16)
        if 0x20 <= value <= 0x7E:
            char = chr(value)
            return '""' if char == '"' else char
        if value == 0x0D:
            return "\\r"
        if value == 0x0A:
            return "\\n"
        return "\\x%02X" % value

    return _CSV_HEX_BYTE.sub(repl, text).replace("=EoP", "\\n")


def _correct_csv_export(local_path: str) -> int:
    """Correct an exported .csv in place (see _decode_csv_export_text).
    Returns the number of corrected lines (0 when the file carries no
    markers or does not exist)."""
    if not os.path.isfile(local_path):
        return 0
    with open(local_path, encoding="utf-8", errors="replace") as fh:
        content = fh.read()
    corrected = _decode_csv_export_text(content)
    if corrected == content:
        return 0
    changed = sum(
        1
        for line in content.splitlines()
        if _CSV_HEX_BYTE.search(line) or "=EoP" in line
    )
    tmp = local_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(corrected)
    os.replace(tmp, local_path)
    return changed


def _from_capture_end(value: float, capture_time: float) -> float:
    """Resolve a negative time against the capture duration."""
    return max(float(capture_time) + float(value), 0.0)


def _zoom_range(start: float, end: float) -> Tuple[float, float]:
    """Normalize a zoom range (ordered, never empty) as the CLI does."""
    start, end = (float(start), float(end))
    if end < start:
        start, end = (end, start)
    if start == end:
        if start == 0:
            end = 0.001
        else:
            start = max(end - 0.001, 0.0)
    return (start, end)


class ActiveProClient:
    """Client for the TCP API of the Active-Pro application."""

    PORT_BASE = 37800
    PORT_COUNT = 11

    def __init__(self, host: str = "localhost", port: int = 37800) -> None:
        """Remember the application host and port."""
        self.host = host
        self.port = port

    def send_command(
        self, command: str, timeout: float = DEFAULT_TIMEOUT
    ) -> str:
        """Send one command, return its one-line response."""
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=timeout
            ) as connection:
                connection.sendall((command + "\n").encode())
                response = connection.recv(65536)
        except OSError as exc:
            raise RuntimeError(
                "Active-Pro application not reachable on %s:%d (%s)"
                % (self.host, self.port, exc)
            ) from exc
        text = response.decode(errors="replace").strip()
        if text.upper().startswith("ERROR"):
            raise RuntimeError(text)
        return text

    def list_instances(self) -> str:
        """List the reachable Active-Pro instances (id: port)."""
        found = []
        for port in range(self.PORT_BASE, self.PORT_BASE + self.PORT_COUNT):
            try:
                with socket.create_connection((self.host, port), timeout=0.05):
                    pass
            except OSError:
                continue
            found.append((port - self.PORT_BASE + 1, port))
        if not found:
            return "no Active-Pro instance reachable on %s" % self.host
        return "\n".join(
            "id %d: port %d" % (identifier, port) for identifier, port in found
        )

    def autodetect(self) -> int:
        """Highest reachable instance port (CLI behavior), default
        port when nothing answers."""
        for port in reversed(
            range(self.PORT_BASE, self.PORT_BASE + self.PORT_COUNT)
        ):
            try:
                with socket.create_connection((self.host, port), timeout=0.05):
                    pass
                return port
            except OSError:
                continue
        return self.PORT_BASE

    def status(self) -> str:
        """Probe the application, refresh the port, status for clients."""
        port = self.autodetect()
        self.port = port
        if port != self.PORT_BASE or _reachable(self.host, port):
            return "Active-Pro application reachable on %s:%d" % (
                self.host,
                port,
            )
        return (
            "Active-Pro application NOT reachable on %s:%d: the API"
            " tools will fail. Start the application (or call"
            " list_instances); under WSL give --host/YAPD_MCP_HOST"
            " the Windows IP." % (self.host, port)
        )


# parameter tuples: (key, type, description, required, enum)
_P_TIME = (
    "time",
    "number",
    "time in seconds (negative: relative to the capture end)",
    True,
    None,
)
_P_VOLTS = (
    "volts",
    "number",
    "voltage level in volts",
    True,
    None,
)
_P_PATH = (
    "path",
    "string",
    "file path on the machine running the Active-Pro application",
    True,
    None,
)

_P_WRITE_PATH = (
    "path",
    "string",
    "file path on the machine running the Active-Pro application; a "
    "save/export may only write under /tmp (overwriting yapd_-prefixed "
    "files) or to a path outside /tmp that does not exist yet; set "
    "read_back=true to get the content in the same answer, otherwise "
    "read it back later with read_file",
    True,
    None,
)

_P_READ_BACK = (
    "read_back",
    "boolean",
    "also return the written file's content in this same answer (text "
    "for .csv/.txt/.log/.md/.json/.aft, base64 otherwise)",
    False,
    None,
)

_P_MAX_CHARS = (
    "max_chars",
    "integer",
    "truncate the returned text at this many characters "
    "(default 20000, max 200000)",
    False,
    None,
)


_P_DECODED_ONLY = (
    "decoded_only",
    "boolean",
    "drop the logic/analog rows from the export, keeping only the "
    "decoded device data (A-D); the written file and a read_back answer "
    "are both filtered",
    False,
    None,
)

_P_DEVICE_FILTER = (
    "device_filter",
    "string",
    "comma-separated labels to keep in the export, all other data rows "
    "are dropped: for .csv the Device column (e.g. 'UART_PACKETS' keeps "
    "only the packet transaction rows), for .aft the source letter "
    "(A-D); the written file and a read_back answer are both filtered",
    False,
    None,
)

_P_OFFSET = (
    "offset",
    "integer",
    "with read_back: skip this many characters (text files) or bytes "
    "(binary files) of the written file before returning it",
    False,
    None,
)


def _write_params() -> Tuple[Any, ...]:
    """Parameters of a save/export (write-path) tool."""
    return (_P_WRITE_PATH, _P_READ_BACK, _P_MAX_CHARS, _P_OFFSET)


def _export_params() -> Tuple[Any, ...]:
    """Parameters of an export tool (write path + filters)."""
    return (
        _P_WRITE_PATH,
        _P_READ_BACK,
        _P_MAX_CHARS,
        _P_OFFSET,
        _P_DECODED_ONLY,
        _P_DEVICE_FILTER,
    )


def _api_tool(name: str, description: str, params=()) -> Dict[str, Any]:
    """Build one Automation API tool entry."""
    properties = {}
    required = []
    for key, ptype, pdesc, preq, penum in params:
        prop = {"type": ptype, "description": pdesc}
        if penum:
            prop["enum"] = list(penum)
        properties[key] = prop
        if preq:
            required.append(key)
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return {
        "name": name,
        "description": description,
        "inputSchema": schema,
    }


def _mode_params(modes: Tuple[str, ...]) -> Tuple[Any, ...]:
    """Build the 'mode' parameter for a mode tool."""
    return (("mode", "string", "output mode", True, modes),)


API_TOOLS = [
    _api_tool("hello", "Hello: check the Active-Pro application answers."),
    _api_tool(
        "is_connected", "isConnected: is the target connected (YES/NO)."
    ),
    _api_tool("start_capture", "StartCapture: start capturing data."),
    _api_tool("stop_capture", "StopCapture: stop capturing data."),
    _api_tool("is_capturing", "isCapturing: is a capture running (YES/NO)."),
    _api_tool(
        "get_capture_size", "GetCaptureSize: number of samples captured."
    ),
    _api_tool(
        "get_capture_time", "GetCaptureTime: capture duration in seconds."
    ),
    _api_tool("get_logic", "GetLogic: read the logic input lines."),
    _api_tool("get_ch1", "GetCH1: read channel 1."),
    _api_tool("get_ch2", "GetCH2: read channel 2."),
    _api_tool("get_ch3", "GetCH3: read channel 3."),
    _api_tool(
        "get_analog",
        "GetCH{channel}: read an analog input channel (1-8, volts).",
        (("channel", "integer", "analog channel 1-8", True, None),),
    ),
    _api_tool(
        "get_devices_attached",
        "GetDevicesAttached: list the attached hardware devices "
        "(NONE when none).",
    ),
    _api_tool(
        "select_device",
        "SelectDevice: switch to the hardware device at this 1-based "
        "index from get_devices_attached (clears capture data and "
        "resets settings).",
        (("index", "integer", "1-based device index", True, None),),
    ),
    _api_tool(
        "set_d0_mode",
        "SetD0Mode: set the D0 output mode.",
        _mode_params(tuple(MODE_MAP_D)),
    ),
    _api_tool(
        "set_d0_pwm",
        "SetD0PWM: set the D0 PWM duty cycle (percent).",
        (("percent", "integer", "duty cycle in percent", True, None),),
    ),
    _api_tool(
        "set_d1_mode",
        "SetD1Mode: set the D1 output mode.",
        _mode_params(tuple(MODE_MAP_D)),
    ),
    _api_tool(
        "set_d1_pwm",
        "SetD1PWM: set the D1 PWM duty cycle (percent).",
        (("percent", "integer", "duty cycle in percent", True, None),),
    ),
    _api_tool(
        "set_a0_mode",
        "SetA0Mode: set the A0 output mode.",
        _mode_params(tuple(MODE_MAP_A0)),
    ),
    _api_tool(
        "set_a0_dc_level", "SetA0DCLEVEL: set the A0 DC level.", (_P_VOLTS,)
    ),
    _api_tool(
        "set_a1_mode",
        "SetA1Mode: set the A1 output mode.",
        _mode_params(tuple(MODE_MAP_A1)),
    ),
    _api_tool(
        "set_a1_dc_level", "SetA1DCLEVEL: set the A1 DC level.", (_P_VOLTS,)
    ),
    _api_tool(
        "set_a1_minimum", "SetA1MINIMUM: ramp/sweep minimum.", (_P_VOLTS,)
    ),
    _api_tool(
        "set_a1_maximum", "SetA1MAXIMUM: ramp/sweep maximum.", (_P_VOLTS,)
    ),
    _api_tool(
        "set_a1_steps",
        "SetA1Steps: number of steps of a ramp/sweep.",
        (("steps", "integer", "number of steps", True, None),),
    ),
    _api_tool("clear_note", "ClearNote: clear the capture note."),
    _api_tool(
        "append_note",
        "AppendNote: append a line to the capture note.",
        (("text", "string", "text to append", True, None),),
    ),
    _api_tool("get_note", "GetNote: read the capture note."),
    _api_tool(
        "clear_analysis_context",
        "ClearAnalysisContext: clear the Analysis Context briefing "
        "written into every exported .aft AI Snapshot.",
    ),
    _api_tool(
        "append_analysis_context",
        "AppendAnalysisContext: append a line to the Analysis Context "
        "(test name, firmware version, what to look for) carried by "
        "every exported .aft AI Snapshot.",
        (("text", "string", "text to append", True, None),),
    ),
    _api_tool(
        "get_analysis_context",
        "GetAnalysisContext: read the Analysis Context briefing.",
    ),
    _api_tool(
        "set_cursor_current",
        "SetCursorCurrent: move the current cursor.",
        (_P_TIME,),
    ),
    _api_tool("set_cursor_x1", "SetCursorX1: move the X1 cursor.", (_P_TIME,)),
    _api_tool("set_cursor_x2", "SetCursorX2: move the X2 cursor.", (_P_TIME,)),
    _api_tool(
        "get_cursor",
        "GetCursorCurrent/GetCursorX1/GetCursorX2: read a cursor "
        "position in seconds.",
        (
            (
                "cursor",
                "string",
                "which cursor to read",
                True,
                ("current", "x1", "x2"),
            ),
        ),
    ),
    _api_tool("zoom_all", "ZoomAll: show the whole capture."),
    _api_tool(
        "zoom_from",
        "ZoomFrom: zoom to a time range.",
        (
            (
                "start",
                "number",
                "range start in seconds (negative: "
                "relative to the capture end)",
                True,
                None,
            ),
            (
                "end",
                "number",
                "range end in seconds (negative: relative "
                "to the capture end)",
                True,
                None,
            ),
        ),
    ),
    _api_tool(
        "search",
        "Search: find a string in the decoded device data (packet "
        "presenter rows; strings that only appear in raw byte rows "
        "return NOTFOUND) forward from the current cursor; returns the "
        "match timestamp (seconds, rounded to 0.1 ms) or NOTFOUND. "
        "Consecutive calls enumerate all occurrences: the application "
        "advances past each match itself, and re-finds inside the same "
        "decoded item are skipped server-side, so one occurrence returns "
        "one hit. The returned timestamp is rounded, so when setting the "
        "cursor manually to a returned value, add 0.0001 s to skip that "
        "match. With 'from', the search starts at that timestamp and the "
        "cursor is restored afterwards, so repeated or parallel searches "
        "do not depend on the shared cursor.",
        (
            ("text", "string", "string to search for", True, None),
            (
                "from",
                "number",
                "optional start timestamp in seconds (negative: relative "
                "to the capture end); the current cursor is restored "
                "after the search",
                False,
                None,
            ),
        ),
    ),
    # --- post-capture pipeline ---
    _api_tool(
        "apply_changes",
        "ApplyChanges: reprocess the capture through the decoder/"
        "PacketPresenter/trigger pipeline; blocks until done (long "
        "timeout).",
    ),
    _api_tool(
        "is_processing",
        "IsProcessing: is the post-capture pipeline running (Yes/No); "
        "poll this instead of waiting on apply_changes.",
    ),
    _api_tool(
        "cancel_processing",
        "CancelProcessing: cancel the running pipeline (OK/NotRunning).",
    ),
    # --- trigger status and navigation ---
    _api_tool("is_triggered", "IsTriggered: did any trigger fire (YES/NO)."),
    _api_tool(
        "get_trigger_count", "GetTriggerCount: number of triggers found."
    ),
    _api_tool(
        "get_trigger_index",
        "GetTriggerIndex: 1-based index of the current trigger (0 if "
        "none).",
    ),
    _api_tool(
        "get_trigger_cursor",
        "GetTriggerCursor: position of the trigger cursor in seconds.",
    ),
    _api_tool(
        "set_trigger_cursor",
        "SetTriggerCursor: move the trigger cursor.",
        (_P_TIME,),
    ),
    _api_tool("next_trigger", "NextTrigger: advance to the next trigger."),
    _api_tool("prev_trigger", "PrevTrigger: step to the previous trigger."),
    _api_tool("first_trigger", "FirstTrigger: jump to the oldest trigger."),
    _api_tool("last_trigger", "LastTrigger: jump to the newest trigger."),
    _api_tool(
        "goto_trigger",
        "GoToTrigger: jump to a trigger by 1-based index.",
        (("index", "integer", "1-based trigger index", True, None),),
    ),
    _api_tool(
        "center_trigger",
        "CenterTrigger: re-center the current trigger in the view.",
    ),
    _api_tool(
        "reprocess_triggers",
        "ReprocessTriggers: re-scan the capture with the current trigger "
        "settings (blocks, long timeout).",
    ),
    # --- trigger configuration ---
    _api_tool(
        "set_trigger_mode",
        "SetTriggerMode: off = disabled, normal = fire on condition, "
        "auto = fire on timeout.",
        (("mode", "string", "trigger mode", True, ("off", "normal", "auto")),),
    ),
    _api_tool("get_trigger_mode", "GetTriggerMode: OFF, NORMAL or AUTO."),
    _api_tool(
        "set_trigger_source_type",
        "SetTriggerSourceType: source category; repopulates the channel "
        "and condition lists.",
        (
            (
                "source",
                "string",
                "source type",
                True,
                (
                    "none",
                    "analog",
                    "digital",
                    "atext",
                    "avalues",
                    "btext",
                    "bvalues",
                    "ctext",
                    "cvalues",
                    "dtext",
                    "dvalues",
                    "appgraph",
                    "bppgraph",
                    "cppgraph",
                    "dppgraph",
                ),
            ),
        ),
    ),
    _api_tool(
        "get_trigger_source_type",
        "GetTriggerSourceType: current source token (NONE, ANALOG, ...).",
    ),
    _api_tool(
        "set_trigger_channel",
        "SetTriggerChannel: 1-based channel index (see "
        "get_trigger_channel_list).",
        (("channel", "integer", "1-based channel index", True, None),),
    ),
    _api_tool(
        "get_trigger_channel", "GetTriggerChannel: selected channel text."
    ),
    _api_tool(
        "get_trigger_channel_list",
        "GetTriggerChannelList: available channels for the current "
        "source (newline-separated).",
    ),
    _api_tool(
        "set_trigger_condition",
        "SetTriggerCondition: valid tokens depend on the source type.",
        (
            (
                "condition",
                "string",
                "condition token",
                True,
                (
                    "rising",
                    "falling",
                    "pulsehighgreater",
                    "pulsehighless",
                    "pulselowgreater",
                    "pulselowless",
                    "contains",
                    "equals",
                ),
            ),
        ),
    ),
    _api_tool(
        "get_trigger_condition", "GetTriggerCondition: current condition."
    ),
    _api_tool(
        "set_trigger_threshold",
        "SetTriggerThreshold: threshold value (volts for analog, integer "
        "for device values).",
        (("value", "number", "threshold value", True, None),),
    ),
    _api_tool(
        "get_trigger_threshold", "GetTriggerThreshold: current threshold."
    ),
    _api_tool(
        "set_trigger_pulse_width",
        "SetTriggerPulseWidth: pulse-width value and unit for digital "
        "pulse conditions.",
        (
            ("value", "number", "pulse width value", True, None),
            ("unit", "string", "unit", True, ("ns", "us", "ms", "s")),
        ),
    ),
    _api_tool(
        "get_trigger_pulse_width",
        "GetTriggerPulseWidth: current pulse width as '<value> <unit>'.",
    ),
    _api_tool(
        "set_trigger_text",
        "SetTriggerText: text pattern for contains/equals conditions.",
        (("text", "string", "text pattern", True, None),),
    ),
    _api_tool("get_trigger_text", "GetTriggerText: current text pattern."),
    # --- buffer size and pre/post-trigger ---
    _api_tool(
        "set_buffer_size",
        "SetBufferSize: capture buffer in MB (smallest available entry "
        ">= requested).",
        (("megabytes", "integer", "buffer size in MB", True, None),),
    ),
    _api_tool("get_buffer_size", "GetBufferSize: current buffer size in MB."),
    _api_tool(
        "set_pre_trigger_mode",
        "SetPreTriggerMode: keepall = keep everything before the "
        "trigger, keeplast = keep the last N seconds.",
        (
            (
                "mode",
                "string",
                "pre-trigger mode",
                True,
                ("keepall", "keeplast"),
            ),
        ),
    ),
    _api_tool(
        "get_pre_trigger_mode",
        "GetPreTriggerMode: KEEPALL or KEEPLAST.",
    ),
    _api_tool(
        "set_pre_trigger_seconds",
        "SetPreTriggerSeconds: pre-trigger window depth in seconds "
        "(1-60, keeplast mode).",
        (("seconds", "integer", "seconds, 1-60", True, None),),
    ),
    _api_tool(
        "get_pre_trigger_seconds",
        "GetPreTriggerSeconds: current pre-trigger window depth.",
    ),
    _api_tool(
        "set_post_trigger_mode",
        "SetPostTriggerMode: untilfull = capture until the buffer fills, "
        "stopafterseconds = stop N seconds after the first trigger, "
        "stopaftertriggers = stop after N triggers.",
        (
            (
                "mode",
                "string",
                "post-trigger mode",
                True,
                ("untilfull", "stopafterseconds", "stopaftertriggers"),
            ),
        ),
    ),
    _api_tool(
        "get_post_trigger_mode",
        "GetPostTriggerMode: UNTILFULL, STOPAFTERSECONDS or "
        "STOPAFTERTRIGGERS.",
    ),
    _api_tool(
        "set_post_trigger_seconds",
        "SetPostTriggerSeconds: seconds to keep capturing after the "
        "first trigger (>= 1).",
        (("seconds", "integer", "seconds, >= 1", True, None),),
    ),
    _api_tool(
        "get_post_trigger_seconds",
        "GetPostTriggerSeconds: current post-trigger seconds.",
    ),
    _api_tool(
        "set_post_trigger_triggers",
        "SetPostTriggerTriggers: number of triggers to capture before "
        "stopping (>= 1).",
        (("count", "integer", "trigger count, >= 1", True, None),),
    ),
    _api_tool(
        "get_post_trigger_triggers",
        "GetPostTriggerTriggers: current post-trigger trigger count.",
    ),
    # --- channel and device configuration ---
    _api_tool(
        "logic_channel_on_off",
        "LogicCH{channel}On/Off: enable or disable a logic channel "
        "(D0-D7) for capture.",
        (
            ("channel", "integer", "logic channel 0-7", True, None),
            ("on", "boolean", "true to enable, false to disable", True, None),
        ),
    ),
    _api_tool(
        "analog_channel_on_off",
        "AnalogCH{channel}On/Off: enable or disable an analog channel "
        "(1-8) for capture.",
        (
            ("channel", "integer", "analog channel 1-8", True, None),
            ("on", "boolean", "true to enable, false to disable", True, None),
        ),
    ),
    _api_tool(
        "set_device_mode",
        "Device{device}Mode: decoder mode index for a device port (see "
        "the Device Mode Index Table in the Automation API chapter); "
        "resets the device label and setting to protocol defaults.",
        (
            ("device", "string", "device port", True, ("A", "B", "C", "D")),
            ("mode", "integer", "DECODER_MODES index", True, None),
        ),
    ),
    _api_tool(
        "set_device_setting",
        "Device{device}Setting: numeric setting (baud/bit rate) of a "
        "device port; use after set_device_mode.",
        (
            ("device", "string", "device port", True, ("A", "B", "C", "D")),
            ("value", "number", "setting value", True, None),
        ),
    ),
    _api_tool(
        "set_threshold_level",
        "ThresholdLevel: digital logic threshold voltage (1.0, 1.8, 2.5, "
        "3.3 or 5.0; other values snap to nearest).",
        (("voltage", "number", "threshold in volts", True, None),),
    ),
    _api_tool(
        "set_label",
        "Set a display label: target=logic (index 0-7), target=analog "
        "(index 1-8) or target=device (index A-D).",
        (
            (
                "target",
                "string",
                "what to label",
                True,
                ("logic", "analog", "device"),
            ),
            (
                "index",
                "string",
                "channel index, or port letter for device",
                True,
                None,
            ),
            ("text", "string", "label text", True, None),
        ),
    ),
    _api_tool(
        "set_device_visibility",
        "ShowDevice/HideDevice: show or hide a device's rows in the "
        "waveform view.",
        (
            (
                "device_label",
                "string",
                "device port",
                True,
                ("A", "B", "C", "D"),
            ),
            ("visible", "boolean", "true to show, false to hide", True, None),
        ),
    ),
    _api_tool("show_inputs", "ShowInputs: list the inputs."),
    _api_tool("show_outputs", "ShowOutputs: list the outputs."),
    _api_tool("show_list", "ShowList: list the signals."),
    _api_tool("show_settings", "ShowSettings: list the settings."),
    _api_tool("show_notes", "ShowNotes: show the capture notes."),
    _api_tool("show_triggers", "ShowTriggers: show the triggers tab."),
    _api_tool("show_code", "ShowCode: show the code tab."),
    _api_tool("show_liveui", "ShowLiveUI: show the LiveUI tab."),
    _api_tool("show_devices", "ShowDevices: show the devices tab."),
    _api_tool(
        "set_theme",
        "SetDarkMode/SetLightMode: switch the application theme.",
        (("theme", "string", "theme", True, ("dark", "light")),),
    ),
    _api_tool("close_tabs", "CloseTabs: close the open tabs."),
    _api_tool("new_capture", "NewCapture: start a new empty capture."),
    _api_tool(
        "open_capture",
        "OpenCapture: open a .active capture file (stops a running "
        "capture first).",
        (_P_PATH,),
    ),
    _api_tool(
        "save_capture",
        "SaveCapture: save the capture (.active).",
        _write_params(),
    ),
    _api_tool(
        "save_between_cursors",
        "SaveBetweenCursors: save the data between the X1/X2 cursors "
        "(.active).",
        _write_params(),
    ),
    _api_tool(
        "open_configuration",
        "OpenConfiguration: open a configuration file (.active).",
        (_P_PATH,),
    ),
    _api_tool(
        "save_configuration",
        "SaveConfiguration: save the configuration (.active).",
        _write_params(),
    ),
    _api_tool(
        "export_between_cursors",
        "ExportBetweenCursors: export the data between the X1/X2 "
        "cursors (.csv). The raw export's [HH] hex byte markers and "
        "=EoP packet end markers are decoded in the written file "
        "(disable with --no-correct-csv-export).",
        _export_params(),
    ),
    _api_tool(
        "export_ai_snapshot",
        "ExportAISnapshotBetweenCursors: export the AI Snapshot (.aft "
        "firmware trace) of the X1/X2 range - all decoded data plus the "
        "Analysis Context, ready for AI analysis. Set read_back=true to "
        "get the .aft content in the same answer, or read the file "
        "back later with read_file; decoded_only=true drops the "
        "logic/analog rows.",
        _export_params(),
    ),
    _api_tool(
        "save_screenshot",
        "SaveScreenshot: save a screenshot (.png).",
        _write_params(),
    ),
    _api_tool(
        "read_file",
        "ReadFile: read back a file on this server machine, e.g. the .csv "
        "written by export_between_cursors or the .png written by "
        "save_screenshot. Text files (.csv, .txt, .log, .md, .json, .aft) "
        "are returned as bare text - no wrapper line, so the answer can be "
        "saved as-is (from char offset, truncated at max_chars; a trailing "
        "'[read_file: ...]' note is appended only when offset or "
        "truncation applies). "
        "Other files come "
        "as a one-line header '<path> (<N> bytes, base64):' followed by "
        "standard base64 (RFC 4648: +, /, padding; strip the header "
        "line before piping to base64 -d). Allowed: any path under /tmp, "
        "or a path previously written by a save/export tool.",
        (
            (
                "path",
                "string",
                "file path (under /tmp, or a path written by a "
                "save/export tool)",
                True,
                None,
            ),
            (
                "max_chars",
                "integer",
                "truncate text files at this many characters "
                "(default 20000, max 200000)",
                False,
                None,
            ),
            (
                "offset",
                "integer",
                "skip this many characters (text files) or bytes "
                "(binary files) before reading; combine with "
                "max_chars for chunked reads of large exports",
                False,
                None,
            ),
        ),
    ),
    _api_tool("exit", "Exit: close the Active-Pro application."),
    _api_tool(
        "list_instances",
        "List the Active-Pro instances reachable on the host running "
        "this server, or report that none is.",
    ),
]

KNOWLEDGE_TOOLS = [
    {
        "name": "get_skills",
        "description": (
            "Active-Pro Debugger and YActivePRO knowledge. No arguments: "
            "overview and topic list. Then call with a topic, example: "
            '{"topic": "aft"}. Topics: aft (.aft firmware trace format), '
            "adp (ADP wire protocol, ACTIVEValue, ACTIVEText), automation "
            "(tool workflow, times, exports). Use when "
            "analyzing an .aft trace, an Active-Pro capture or firmware "
            "debug output."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": ["aft", "adp", "automation"],
                    "description": (
                        "topic to fetch (default: overview with the topic "
                        "list)"
                    ),
                },
            },
        },
    },
    {
        "name": "get_docs",
        "description": (
            "Fetch a page of the official Active-Pro user manual "
            "(activefirmwaretools.com) as plain text. No arguments: list "
            'the known pages. Example: {"page": "aft-format"}. \'page\' '
            "is a known page key or a full activefirmwaretools.com URL; "
            "'max_chars' truncates long pages (default 20000). Use for the "
            "full details behind get_skills topics."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page": {
                    "type": "string",
                    "description": (
                        "page key (e.g. aft-format, automation-api) or "
                        "full activefirmwaretools.com URL"
                    ),
                },
                "max_chars": {
                    "type": "integer",
                    "description": (
                        "truncate the page text at this many characters "
                        "(default 20000)"
                    ),
                },
            },
        },
    },
]

FEEDBACK_TOOLS = [
    {
        "name": "feedback",
        "description": (
            "Record feedback about this MCP server for its maintainer:"
            " missing or unclear documentation (a get_skills topic or a"
            " get_docs page), or a suggestion for an additional tool."
            " Use it whenever something is missing or would make the"
            " work easier. One call, one point. Example: "
            '{"feedback": "add a get_docs page about triggers"}.'
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "feedback": {
                    "type": "string",
                    "description": (
                        "the suggestion or problem, in a few sentences"
                    ),
                },
            },
            "required": ["feedback"],
        },
    },
]

TOOLS = KNOWLEDGE_TOOLS + FEEDBACK_TOOLS + API_TOOLS

TOOL_COMMANDS: Dict[str, Any] = dict(COMMANDS)
TOOL_COMMANDS.update(
    {
        "set_cursor_current": None,
        "set_cursor_x1": None,
        "set_cursor_x2": None,
        "set_trigger_cursor": None,
        "zoom_from": None,
        "list_instances": None,
        "read_file": None,
        "get_cursor": None,
        "set_theme": None,
    }
)
for _tool_name in ON_OFF_TOOLS:
    TOOL_COMMANDS[_tool_name] = None
for _tool_name in DEVICE_TOOLS:
    TOOL_COMMANDS[_tool_name] = None
TOOL_COMMANDS.update({"set_label": None, "set_device_visibility": None})
for _tool_name, (_map, _command) in MODE_TOOLS.items():
    TOOL_COMMANDS[_tool_name] = None


# ------------------------------------------------------------- dispatch


def run_api_tool(name: str, arguments: Dict[str, Any], api) -> str:
    """Run one Automation API tool call."""
    if name == "list_instances":
        return api.list_instances()
    if name in MODE_TOOLS:
        mode_map, command = MODE_TOOLS[name]
        mode = str(arguments["mode"]).lower()
        if mode not in mode_map:
            raise ValueError(
                "invalid mode for %s: %s (expected one of %s)"
                % (name, arguments["mode"], ", ".join(mode_map))
            )
        return api.send_command("%s %d" % (command, mode_map[mode]))
    if name in TIME_TOOLS:
        value = float(arguments["time"])
        if value < 0:
            value = _from_capture_end(
                value, float(api.send_command("GetCaptureTime"))
            )
        return api.send_command("{} {}".format(TIME_TOOLS[name], value))
    if name == "zoom_from":
        start = float(arguments["start"])
        end = float(arguments["end"])
        if start < 0 or end < 0:
            capture_time = float(api.send_command("GetCaptureTime"))
            start = _from_capture_end(start, capture_time)
            end = _from_capture_end(end, capture_time)
        start, end = _zoom_range(start, end)
        return api.send_command("ZoomFrom {} {}".format(start, end))
    if name == "search":
        text = str(arguments["text"])
        from_time = arguments.get("from")
        if from_time is not None:
            # stateless search: anchor at 'from', then restore the
            # shared cursor so parallel calls do not race on it
            value = float(from_time)
            if value < 0:
                value = _from_capture_end(
                    value, float(api.send_command("GetCaptureTime"))
                )
            saved = api.send_command(CURSOR_GET_COMMANDS["current"])
            api.send_command(
                "{} {}".format(TIME_TOOLS["set_cursor_current"], value)
            )
            try:
                return api.send_command("Search {}".format(text))
            finally:
                api.send_command(
                    "{} {}".format(TIME_TOOLS["set_cursor_current"], saved)
                )
        last = getattr(api, "last_search", None)
        seen = last[1] if last is not None and last[0] == text else None
        result = "NOTFOUND"
        # the application advances the cursor only ~0.1 ms past a
        # match, so it re-finds the same decoded item until the cursor
        # walks past the item; skip those re-finds (one quantum of
        # drift each) so one occurrence returns one hit
        for _ in range(100):
            result = api.send_command("Search {}".format(text))
            try:
                found = float(result)
            except ValueError:
                return result  # NOTFOUND or an error text
            if seen is not None and found <= seen + SEARCH_DEDUP_QUANTUM:
                seen = found
                continue
            api.last_search = (text, found)
            return result
        return result
    if name in PATH_TOOLS:
        if name in WRITE_PATH_TOOLS:
            # enforce the write policy on the local path, then convert
            # for the application host (Windows path under WSL)
            local_path = check_write_path(arguments["path"], PATH_TOOLS[name])
            path = _app_path(local_path)
        else:
            local_path = None
            path = get_absolute_path(arguments["path"], PATH_TOOLS[name])
        if name == "open_capture":
            if api.send_command("isCapturing").upper() == "YES":
                api.send_command("StopCapture")
        command = "{} {}".format(COMMANDS[name], path)
        response = api.send_command(command)
        if local_path is not None:
            # the app answers OK/YES on success, NO or ERROR... on failure
            answer = response.strip().upper()
            if answer and answer != "NO" and not answer.startswith("ERROR"):
                if (
                    name == "export_between_cursors"
                    and CONF["correct_csv_export"]
                ):
                    # correct the raw export markers in the .csv file
                    changed = _correct_csv_export(local_path)
                    if changed:
                        response = "%s (csv corrected: %d lines)" % (
                            response,
                            changed,
                        )
                if name in CURSOR_RANGE_TOOLS:
                    # echo the range actually exported (X1/X2 cursors)
                    x1 = api.send_command(CURSOR_GET_COMMANDS["x1"])
                    x2 = api.send_command(CURSOR_GET_COMMANDS["x2"])
                    try:
                        float(x1)
                        float(x2)
                    except ValueError:
                        pass
                    else:
                        response = "{} (exported range X1={}..X2={})".format(
                            response,
                            x1,
                            x2,
                        )
                record_written_file(local_path)
                device_filter = arguments.get("device_filter")
                if arguments.get("decoded_only") or device_filter:
                    keep = None
                    if device_filter:
                        keep = frozenset(
                            part.strip()
                            for part in str(device_filter).split(",")
                            if part.strip()
                        )
                    drop_raw = bool(arguments.get("decoded_only"))
                    if name == "export_ai_snapshot":
                        dropped = _filter_rows_aft(
                            local_path, drop_raw=drop_raw, keep=keep
                        )
                        kind = "L/AN source"
                    elif name == "export_between_cursors":
                        dropped = _filter_rows_csv(
                            local_path, drop_raw=drop_raw, keep=keep
                        )
                        kind = "LOGIC/ANALOG device"
                    else:
                        dropped = 0
                        kind = ""
                    if dropped:
                        note = "dropped %d rows" % dropped
                        if drop_raw:
                            note += " (%s)" % kind
                        if keep is not None:
                            note += " (kept %s)" % ",".join(sorted(keep))
                        response = "{} (export filtered: {})".format(
                            response,
                            note,
                        )
                if arguments.get("read_back"):
                    return "{}\n{}".format(
                        response, read_file(local_path, arguments)
                    )
        return response
    if name == "get_cursor":
        cursor = str(arguments["cursor"]).lower()
        if cursor not in CURSOR_GET_COMMANDS:
            raise ValueError(
                "invalid cursor: %s (expected one of %s)"
                % (arguments["cursor"], ", ".join(CURSOR_GET_COMMANDS))
            )
        return api.send_command(CURSOR_GET_COMMANDS[cursor])
    if name == "set_theme":
        theme = str(arguments["theme"]).lower()
        if theme not in THEME_COMMANDS:
            raise ValueError(
                "invalid theme: %s (expected one of %s)"
                % (arguments["theme"], ", ".join(THEME_COMMANDS))
            )
        return api.send_command(THEME_COMMANDS[theme])
    if name in ON_OFF_TOOLS:
        state = "On" if arguments.get("on") else "Off"
        return api.send_command(ON_OFF_TOOLS[name].format(**arguments) + state)
    if name in DEVICE_TOOLS:
        args = dict(arguments, device=str(arguments["device"]).upper())
        return api.send_command(DEVICE_TOOLS[name].format(**args))
    if name == "set_label":
        target = str(arguments["target"]).lower()
        index = str(arguments["index"])
        text = str(arguments["text"])
        if target == "device":
            command = "Device{}Label {}".format(index.upper(), text)
        elif target == "logic":
            command = "LogicCH{}Label {}".format(index, text)
        elif target == "analog":
            command = "AnalogCH{}Label {}".format(index, text)
        else:
            raise ValueError(
                "invalid target: %s (expected logic, analog or device)"
                % arguments["target"]
            )
        return api.send_command(command)
    if name == "set_device_visibility":
        action = "Show" if arguments.get("visible") else "Hide"
        label = str(arguments["device_label"]).upper()
        if label not in ("A", "B", "C", "D"):
            raise ValueError(
                "invalid device_label: %s (expected A, B, C or D)"
                % arguments["device_label"]
            )
        return api.send_command("{}Device{}".format(action, label))
    command = COMMANDS[name]
    if "{" in command:
        command = command.format(**arguments)
    return api.send_command(
        command, timeout=TOOL_TIMEOUTS.get(name, DEFAULT_TIMEOUT)
    )


def run_tool(name: str, arguments: Dict[str, Any], api=None) -> str:
    """Run one tool call and return its text result."""
    if name == "get_skills":
        topic = arguments.get("topic") or "overview"
        if topic not in SKILLS:
            raise ValueError(
                "unknown topic: %s (topics: %s)"
                % (topic, ", ".join(sorted(SKILLS)))
            )
        return SKILLS[topic]
    if name == "get_docs":
        page = arguments.get("page")
        if not page:
            return page_list()
        max_chars = int(arguments.get("max_chars") or DEFAULT_MAX_CHARS)
        return fetch_doc(page, max(1000, max_chars))
    if name == "feedback":
        text = str(arguments.get("feedback") or "").strip()
        if not text:
            raise ValueError("empty feedback: describe the suggestion")
        return record_feedback(text)
    if name == "read_file":
        return read_file(str(arguments.get("path") or ""), arguments)
    if name in TOOL_COMMANDS:
        if api is None:
            raise RuntimeError(
                "no Active-Pro client configured (stdio and HTTP modes "
                "both configure one)"
            )
        return run_api_tool(name, arguments, api)
    raise ValueError("unknown tool: %s" % name)


def handle(message: Dict[str, Any], api=None) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message; return None for notifications."""
    msg_id = message.get("id")
    if msg_id is None:
        return None
    method = message.get("method", "")
    if method == "initialize":
        requested = str(
            (message.get("params") or {}).get("protocolVersion") or ""
        )
        protocol_version = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else MCP_PROTOCOL_VERSION
        )
        result: Dict[str, Any] = {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": VERSION},
        }
        if api is not None:
            # every new MCP connection: probe and report the state of
            # the Active-Pro application to the client
            result["instructions"] = api.status()
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params", {})
        try:
            text = run_tool(
                params.get("name", ""), params.get("arguments", {}), api
            )
            result = {"content": [{"type": "text", "text": text}]}
        except (ValueError, RuntimeError) as exc:
            result = {
                "content": [{"type": "text", "text": "error: %s" % exc}],
                "isError": True,
            }
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": "method not found: %s" % method,
            },
        }
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


# --------------------------------------------------------- authentication

USERS: Dict[str, str] = {}


def hash_password(password: str, iters: int = 200000, salt: str = "") -> str:
    """PBKDF2 hash of a password: iterations$salt$hexdigest."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), iters
    )
    return "%d$%s$%s" % (iters, salt, digest.hex())


def verify_password(password: str, stored: str) -> bool:
    """Check a password against its PBKDF2 hash."""
    try:
        iters, salt, expected = stored.split("$", 2)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), int(iters)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, AttributeError):
        return False


def authenticate(username: str, password: str) -> bool:
    """Check the credentials of this run against USERS."""
    stored = USERS.get(username, "")
    if not stored or not verify_password(password, stored):
        return False
    return True


def issue_token(username: str, secret: str, ttl_h: float) -> str:
    """Signed session token: base64 payload + HMAC-SHA256."""
    payload = {
        "u": username,
        "exp": int(time.time() + ttl_h * 3600),
        "n": secrets.token_hex(8),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    signature = hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return body + "." + signature


def verify_token(token: str, secret: str) -> Optional[str]:
    """Return the username of a valid signed token, else None."""
    if not token or not secret:
        return None
    parts = token.split(".", 1)
    if len(parts) != 2:
        return None
    body, signature = parts
    expected = hmac.new(
        secret.encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return str(payload.get("u"))


# OAuth 2.1 authorization server for MCP clients (RFC 9728 protected
# resource metadata, RFC 8414 AS metadata, RFC 7636 PKCE S256, RFC 7591
# dynamic client registration). Access tokens are session tokens;
# refresh tokens are separate signed blobs.


def b64url(raw: bytes) -> str:
    """Base64 URL encoding without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def pkce_s256(verifier: str) -> str:
    """PKCE S256 challenge of a verifier (RFC 7636)."""
    return b64url(hashlib.sha256(verifier.encode()).digest())


def oauth_sign(payload: Dict[str, Any], ttl_s: float) -> str:
    """Sign an OAuth blob (refresh tokens) with the session secret."""
    payload = dict(payload, exp=int(time.time() + ttl_s))
    body = b64url(json.dumps(payload, ensure_ascii=False).encode())
    signature = hmac.new(
        CONF["session_secret"].encode(), body.encode(), hashlib.sha256
    ).hexdigest()
    return body + "." + signature


def oauth_verify(token: str) -> Optional[Dict[str, Any]]:
    """Verify an OAuth blob; return its payload or None."""
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(
            CONF["session_secret"].encode(), body.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        pad = "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(body + pad))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except (ValueError, TypeError, AttributeError):
        return None


def load_clients() -> Dict[str, Any]:
    """Load the OAuth client registry (persisted across restarts)."""
    try:
        with open(CONF["oauth_clients_file"], encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def save_clients(clients: Dict[str, Any]) -> None:
    """Save the OAuth client registry atomically."""
    path = CONF["oauth_clients_file"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(clients, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_credentials() -> Optional[Dict[str, Any]]:
    """The persisted consent-page credentials, None when absent."""
    try:
        with open(CONF["credentials_file"], encoding="utf-8") as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return None
    if (
        not isinstance(data, dict)
        or not data.get("username")
        or not data.get("password")
    ):
        return None
    return data


def save_credentials(username: str, password: str) -> None:
    """Save the consent-page credentials atomically (0600)."""
    path = CONF["credentials_file"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "username": username,
        "password": password,
        "created_at": int(time.time()),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def delete_credentials() -> bool:
    """Delete the persisted credentials; True when a file was removed."""
    try:
        os.remove(CONF["credentials_file"])
        return True
    except FileNotFoundError:
        return False


def load_session_secret() -> str:
    """The persisted session secret, empty when there is none."""
    try:
        with open(CONF["session_secret_file"], encoding="utf-8") as fh:
            secret = fh.read().strip()
    except OSError:
        return ""
    return secret if secret else ""


def save_session_secret(secret: str) -> None:
    """Persist the session secret atomically (0600)."""
    path = CONF["session_secret_file"]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(secret)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def register_client(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """RFC 7591 dynamic registration, public clients with PKCE."""
    uris = metadata.get("redirect_uris")
    if not isinstance(uris, list) or not uris:
        raise ValueError("redirect_uris is required (non-empty array)")
    for uri in uris:
        if not isinstance(uri, str) or not uri.startswith(
            ("http://", "https://")
        ):
            raise ValueError("invalid redirect_uri: %s" % uri)
    client_id = "mc-" + secrets.token_hex(16)
    clients = load_clients()
    clients[client_id] = {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "redirect_uris": uris,
        "client_name": str(metadata.get("client_name", ""))[:200],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    save_clients(clients)
    return clients[client_id]


OAUTH_CODES: Dict[str, Dict[str, Any]] = {}
OAUTH_LOCK = threading.Lock()


def oauth_code_issue(
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    username: str,
    scope: str = "",
) -> str:
    """Issue a single-use authorization code (10 min)."""
    code = secrets.token_urlsafe(32)
    with OAUTH_LOCK:
        now = time.time()
        for key in [
            key for key, value in OAUTH_CODES.items() if value["exp"] < now
        ]:
            del OAUTH_CODES[key]
        OAUTH_CODES[code] = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "username": username,
            "scope": scope,
            "exp": now + CONF["oauth_code_ttl_s"],
        }
    return code


def oauth_code_consume(
    code: str, client_id: str, redirect_uri: str, code_verifier: str
) -> Optional[Dict[str, Any]]:
    """Consume an authorization code; a wrong verifier burns it.

    An omitted redirect_uri (empty string) is accepted: the stored one
    was validated against the client registry when the code was
    issued; a provided redirect_uri must still match exactly.
    """
    with OAUTH_LOCK:
        params = OAUTH_CODES.pop(code, None)
    if (
        not params
        or params["client_id"] != client_id
        or (redirect_uri and params["redirect_uri"] != redirect_uri)
        or params["exp"] < time.time()
    ):
        return None
    if (
        not code_verifier
        or pkce_s256(code_verifier) != params["code_challenge"]
    ):
        return None
    return params


def validate_authorize(
    query: Dict[str, Any],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Common checks for GET/POST /authorize."""
    if (query.get("response_type") or ["code"])[0] != "code":
        return "unsupported_response_type", None
    client_id = (query.get("client_id") or [""])[0]
    redirect_uri = (query.get("redirect_uri") or [""])[0]
    client = load_clients().get(client_id)
    if not client:
        return "invalid_client", None
    if redirect_uri not in client["redirect_uris"]:
        return "invalid_redirect_uri", None
    method = (query.get("code_challenge_method") or ["S256"])[0]
    challenge = (query.get("code_challenge") or [""])[0]
    if method != "S256" or not challenge:
        return "invalid_request: PKCE S256 required", None
    return None, {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code_challenge": challenge,
        "client_name": client.get("client_name") or client_id,
        "state": (query.get("state") or [""])[0],
        "scope": (query.get("scope") or [""])[0],
    }


def consent_page(params: Dict[str, Any], error: str = "") -> str:
    """Login/consent HTML: username and password of this run."""
    hidden = "".join(
        '<input type="hidden" name="%s" value="%s">'
        % (key, html.escape(params.get(key, ""), quote=True))
        for key in (
            "client_id",
            "redirect_uri",
            "code_challenge",
            "state",
            "scope",
        )
    )
    body = [
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,'
        'initial-scale=1"><title>YActivePRO MCP</title></head>',
        '<body style="font-family:sans-serif;max-width:24em;'
        'margin:8em auto">',
        "<h2>YActivePRO MCP server</h2>",
        "<p>The client &laquo;%s&raquo; requests access to the MCP "
        "tools.</p>" % html.escape(params.get("client_name", "")),
        '<form method="post" action="/authorize">',
        '<input type="hidden" name="code_challenge_method" value="S256">',
        hidden,
        '<p><label>Username<br><input name="username" '
        'autocomplete="username"></label></p>',
        '<p><label>Password<br><input type="password" name="password" '
        'autocomplete="current-password"></label></p>',
        '<p><button type="submit">Authorize</button></p></form>',
    ]
    if error:
        body.insert(5, '<p style="color:#b00">%s</p>' % html.escape(error))
    body.append("</body></html>")
    return "".join(body)


def as_metadata(base: str) -> Dict[str, Any]:
    """Authorization-server metadata (RFC 8414)."""
    return {
        "issuer": base,
        "authorization_endpoint": base + "/authorize",
        "token_endpoint": base + "/token",
        "registration_endpoint": base + "/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp"],
    }


def rs_metadata(base: str) -> Dict[str, Any]:
    """Protected-resource metadata (RFC 9728)."""
    return {
        "resource": base + "/mcp",
        "authorization_servers": [base],
        "scopes_supported": ["mcp"],
        "resource_documentation": base + "/healthz",
        "bearer_methods_supported": ["header"],
    }


# ------------------------------------------------------------------ HTTP


# One event stream per username (the most recent GET /mcp wins):
# streamable HTTP clients get the JSON answer in the POST response,
# legacy HTTP+SSE clients read it from their open event stream.
SSE_STREAMS: Dict[str, "queue.Queue"] = {}
SSE_LOCK = threading.Lock()


def sse_frame(event: str, data: str) -> bytes:
    """One server-sent event frame."""
    return ("event: {}\ndata: {}\n\n".format(event, data)).encode()


def wants_sse(accept: str) -> bool:
    """Whether an Accept header asks for the legacy SSE transport."""
    return "text/event-stream" in accept and "application/json" not in accept


def _is_disconnect_error(exc: Optional[BaseException]) -> bool:
    """Whether an exception is a client dropping its connection."""
    return isinstance(
        exc, (ConnectionResetError, BrokenPipeError, TimeoutError)
    )


def token_body_params(content_type: str, body: bytes) -> Dict[str, Any]:
    """Parse a /token body: urlencoded form or a JSON object.

    MCP clients send both (LM Studio posts JSON); values are
    normalized to lists like parse_qs does, JSON values stringified.
    """
    if "application/json" in (content_type or ""):
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            key: [str(value)]
            for key, value in data.items()
            if value is not None
        }
    return urllib.parse.parse_qs(body.decode("utf-8"))


class McpHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying the Active-Pro client."""

    api = None
    remote = None

    def handle_error(self, request, client_address):
        """No traceback for clients that drop their connection."""
        # browsers preconnect and reset, clients drop keep-alive
        # sockets mid-request; socketserver would print a traceback
        exc = sys.exc_info()[1]
        if exc is not None and _is_disconnect_error(exc):
            return
        super().handle_error(request, client_address)


class Handler(BaseHTTPRequestHandler):
    """HTTP transport of the MCP server with OAuth 2.1 auth."""

    protocol_version = "HTTP/1.1"
    # request body of the current request, reset in handle_one_request
    _raw_body = None

    def log_message(self, fmt, *args):
        """Silence the default access log on stderr."""
        # pylint: disable=unused-argument,arguments-differ
        return

    def _cors_headers(self):
        """CORS headers on every response: browser-based MCP clients call
        /mcp, /token and the metadata endpoints cross-origin, and need to
        read WWW-Authenticate on 401s."""
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": (
                "Authorization, Content-Type, MCP-Protocol-Version, "
                "MCP-Session-Id, Last-Event-ID"
            ),
            "Access-Control-Expose-Headers": (
                "WWW-Authenticate, MCP-Session-Id"
            ),
            "Access-Control-Max-Age": "600",
        }

    def _send(self, status, obj, extra_headers=None):
        """Send a JSON response."""
        if obj is None:
            body = b""
        else:
            body = json.dumps(obj, ensure_ascii=False).encode()
        headers = self._cors_headers()
        headers.update(extra_headers or {})
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _send_html(self, status, html_body, extra_headers=None):
        """Send an HTML response."""
        body = html_body.encode()
        headers = self._cors_headers()
        headers.update(extra_headers or {})
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        """CORS preflight (browser clients)."""
        self._body()
        self.send_response(204)
        self.send_header("Content-Length", "0")
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.end_headers()

    def handle_one_request(self):
        """Reset the per-request body cache (one handler instance
        serves every request of a keep-alive connection)."""
        self._raw_body = None
        super().handle_one_request()

    def _body(self):
        """The request body, read exactly once per request.

        Every handler must call this before responding: an undrained
        body would stay in the socket and be parsed as the next
        request on a keep-alive connection (surfacing as random 501s
        through a reusing reverse proxy).
        """
        if self._raw_body is None:
            encoding = (self.headers.get("Transfer-Encoding") or "").lower()
            if "chunked" in encoding:
                chunks = []
                while True:
                    size = int(
                        self.rfile.readline(65536).split(b";", 1)[0].strip()
                        or b"0",
                        16,
                    )
                    if size == 0:
                        while self.rfile.readline(65536) not in (
                            b"\r\n",
                            b"\n",
                            b"",
                        ):
                            pass  # trailers
                        break
                    chunks.append(self.rfile.read(size))
                    self.rfile.read(2)  # CRLF after each chunk
                self._raw_body = b"".join(chunks)
            else:
                length = int(self.headers.get("Content-Length", "0") or 0)
                self._raw_body = self.rfile.read(length) if length else b""
        return self._raw_body

    def _form(self):
        """Read a urlencoded form body."""
        return urllib.parse.parse_qs(self._body().decode("utf-8"))

    def _json_body(self):
        """Read a JSON body."""
        return json.loads(self._body() or b"{}")

    def _base_url(self):
        """Public base URL: YAPD_MCP_OAUTH_ISSUER_URL wins, else the request
        headers (reverse proxy or tunnel)."""
        if CONF["oauth_issuer"]:
            return CONF["oauth_issuer"]
        scheme = self.headers.get("X-Forwarded-Proto") or "http"
        host = (
            self.headers.get("X-Forwarded-Host")
            or self.headers.get("Host")
            or "%s:%d" % (CONF["bind"], CONF["http_port"])
        )
        return "{}://{}".format(scheme, host)

    def _session_user(self):
        """Username of the Bearer token, None when invalid."""
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return None
        return verify_token(header[7:].strip(), CONF["session_secret"])

    def _challenge(self):
        """The WWW-Authenticate value of a 401 (RFC 9728/6750).

        resource_metadata points at the path-suffixed well-known URL of
        the /mcp resource; an invalid presented token adds
        error="invalid_token" so clients re-authenticate.
        """
        base = self._base_url()
        parts = [
            "Bearer",
            'resource_metadata="%s/.well-known/oauth-protected-resource/mcp"'
            % base,
        ]
        if self.headers.get("Authorization"):
            parts.append('error="invalid_token"')
        return ", ".join(parts)

    def do_GET(self):
        """GET endpoints: health, metadata, consent page."""
        self._body()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz":
            self._send(
                200,
                {
                    "status": "ok",
                    "server": SERVER_NAME,
                    "version": VERSION,
                },
            )
        elif (
            path == "/.well-known/oauth-protected-resource"
            or path.startswith("/.well-known/oauth-protected-resource/")
        ):
            # RFC 9728: clients may append the resource path to the
            # well-known URI (/.well-known/oauth-protected-resource/mcp)
            self._send(200, rs_metadata(self._base_url()))
        elif (
            path == "/.well-known/oauth-authorization-server"
            or path.startswith("/.well-known/oauth-authorization-server/")
            or path == "/.well-known/openid-configuration"
            or path.startswith("/.well-known/openid-configuration/")
        ):
            # RFC 8414 AS metadata; the OIDC well-known is an alias some
            # clients try first
            self._send(200, as_metadata(self._base_url()))
        elif path == "/authorize":
            self._handle_authorize_get()
        elif path == "/mcp":
            self._handle_mcp_get()
        else:
            self._send(404, {"error": "not found"})

    def do_DELETE(self):
        """DELETE /mcp terminates the session (streamable HTTP)."""
        self._body()
        path = urllib.parse.urlsplit(self.path).path
        if path != "/mcp":
            self._send(404, {"error": "not found"})
            return
        if not CONF["session_secret"]:
            self._send(500, {"error": "no session secret configured"})
            return
        username = self._session_user()
        if not username:
            self._send(
                401,
                {"error": "valid session token required"},
                {"WWW-Authenticate": self._challenge()},
            )
            return
        with SSE_LOCK:
            SSE_STREAMS.pop(username, None)
        self._send(200, {"ok": True})

    def do_POST(self):
        """POST endpoints: login, OAuth, MCP."""
        self._body()
        path = urllib.parse.urlsplit(self.path).path
        if path == "/login":
            self._handle_login()
        elif path == "/authorize":
            self._handle_authorize_post()
        elif path == "/token":
            self._handle_token()
        elif path == "/register":
            self._handle_register()
        elif path == "/mcp":
            self._handle_mcp()
        else:
            self._send(404, {"error": "not found"})

    def _handle_login(self):
        """POST /login: username/password -> session token."""
        try:
            credentials = self._json_body()
        except ValueError:
            self._send(400, {"error": "invalid JSON body"})
            return
        if not authenticate(
            credentials.get("username", ""),
            credentials.get("password", ""),
        ):
            self._send(401, {"error": "invalid credentials"})
            return
        token = issue_token(
            credentials["username"],
            CONF["session_secret"],
            CONF["session_ttl_h"],
        )
        self._send(
            200,
            {
                "token": token,
                "expires_at": int(time.time() + CONF["session_ttl_h"] * 3600),
                "ttl_hours": CONF["session_ttl_h"],
            },
        )

    def _handle_authorize_get(self):
        """GET /authorize: show the consent page."""
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        error, params = validate_authorize(query)
        if error or not params:
            self._send(400, {"error": error})
            return
        self._send_html(200, consent_page(params))

    def _handle_authorize_post(self):
        """POST /authorize: check credentials, redirect with a code."""
        form = self._form()
        error, params = validate_authorize(form)
        if error or not params:
            self._send(400, {"error": error})
            return
        if not authenticate(
            (form.get("username") or [""])[0],
            (form.get("password") or [""])[0],
        ):
            self._send_html(
                200,
                consent_page(params, error="Invalid username or password."),
            )
            return
        code = oauth_code_issue(
            params["client_id"],
            params["redirect_uri"],
            params["code_challenge"],
            (form.get("username") or [""])[0],
            params["scope"],
        )
        separator = "&" if "?" in params["redirect_uri"] else "?"
        location = "{}{}code={}".format(
            params["redirect_uri"],
            separator,
            urllib.parse.quote(code),
        )
        if params["state"]:
            location += "&state=" + urllib.parse.quote(params["state"])
        self._send_html(302, "", {"Location": location})

    def _handle_token(self):
        """POST /token: authorization_code+PKCE or refresh_token."""
        form = token_body_params(
            self.headers.get("Content-Type", ""), self._body()
        )
        grant = (form.get("grant_type") or [""])[0]
        client_id = (form.get("client_id") or [""])[0]
        if grant == "authorization_code":
            params = oauth_code_consume(
                code=(form.get("code") or [""])[0],
                client_id=client_id,
                redirect_uri=(form.get("redirect_uri") or [""])[0],
                code_verifier=(form.get("code_verifier") or [""])[0],
            )
            if not params:
                self._send(400, {"error": "invalid_grant"})
                return
            self._issue_token_response(
                params["username"], params.get("scope", ""), client_id
            )
        elif grant == "refresh_token":
            payload = oauth_verify((form.get("refresh_token") or [""])[0])
            if (
                not payload
                or payload.get("k") != "refresh"
                or payload.get("c") != client_id
            ):
                self._send(400, {"error": "invalid_grant"})
                return
            self._issue_token_response(
                str(payload.get("u", "")), str(payload.get("s", "")), client_id
            )
        else:
            self._send(400, {"error": "unsupported_grant_type"})

    def _issue_token_response(self, username, scope, client_id):
        """Send the OAuth token response (access + refresh)."""
        access = issue_token(
            username, CONF["session_secret"], CONF["session_ttl_h"]
        )
        refresh = oauth_sign(
            {"k": "refresh", "u": username, "c": client_id, "s": scope},
            CONF["oauth_refresh_ttl_h"] * 3600,
        )
        self._send(
            200,
            {
                "access_token": access,
                "token_type": "Bearer",
                "expires_in": int(CONF["session_ttl_h"] * 3600),
                "refresh_token": refresh,
                "scope": scope or "mcp",
            },
        )

    def _handle_register(self):
        """POST /register: RFC 7591 dynamic client registration."""
        try:
            metadata = self._json_body()
        except ValueError:
            self._send(400, {"error": "invalid JSON body"})
            return
        try:
            client = register_client(
                metadata if isinstance(metadata, dict) else {}
            )
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        self._send(201, client)

    def _handle_mcp_get(self):
        """GET /mcp: the event stream of the legacy SSE transport.

        A GET that does not ask for text/event-stream (a streamable
        HTTP client probing for server-initiated messages) gets 405.
        """
        if not CONF["session_secret"]:
            self._send(500, {"error": "no session secret configured"})
            return
        username = self._session_user()
        if not username:
            self._send(
                401,
                {"error": "valid session token required"},
                {"WWW-Authenticate": self._challenge()},
            )
            return
        if not wants_sse(self.headers.get("Accept", "")):
            self._send(
                405,
                {"error": "GET /mcp requires Accept: text/event-stream"},
                {"Allow": "POST"},
            )
            return
        messages: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with SSE_LOCK:
            SSE_STREAMS[username] = messages
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            self.wfile.write(sse_frame("endpoint", "/mcp"))
            self.wfile.flush()
            while True:
                try:
                    payload = messages.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(
                    sse_frame(
                        "message", json.dumps(payload, ensure_ascii=False)
                    )
                )
                self.wfile.flush()
        except OSError:
            pass  # the client closed the event stream
        finally:
            with SSE_LOCK:
                if SSE_STREAMS.get(username) is messages:
                    del SSE_STREAMS[username]

    def _handle_mcp(self):
        """POST /mcp: one JSON-RPC message per POST, Bearer required.

        Streamable HTTP clients get the JSON answer in the POST
        response; legacy HTTP+SSE clients read it from their open
        event stream (a 202 acknowledges the POST).
        """
        if not CONF["session_secret"]:
            self._send(500, {"error": "no session secret configured"})
            return
        username = self._session_user()
        if not username:
            self._send(
                401,
                {"error": "valid session token required"},
                {"WWW-Authenticate": self._challenge()},
            )
            return
        try:
            message = self._json_body()
        except ValueError:
            self._send(400, {"error": "invalid JSON body"})
            return
        if not isinstance(message, dict):
            self._send(400, {"error": "invalid JSON-RPC message"})
            return
        if message.get("id") is None:
            self._send(202, None)
            return
        try:
            response = handle(message, getattr(self.server, "api", None))
        except Exception:  # pylint: disable=broad-exception-caught
            # never leak a stack trace to clients
            self._send(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "error": {"code": -32603, "message": "internal error"},
                },
            )
            return
        if response is None:
            self._send(202, None)
            return
        if wants_sse(self.headers.get("Accept", "")):
            with SSE_LOCK:
                stream = SSE_STREAMS.get(username)
            if stream is not None:
                # legacy HTTP+SSE client: the answer goes to its
                # open event stream, the POST is acknowledged
                stream.put(response)
                self._send(202, None)
                return
        self._send(200, response)


def ssh_command(public_port: int, http_port: int, remote: str) -> str:
    """The suggested reverse tunnel command for --remote.

    No ExitOnForwardFailure: a ~/.ssh/config that adds unrelated
    RemoteForward entries (e.g. a catch-all "Host *" stanza) would
    otherwise abort the whole tunnel when one of those ports is taken
    on the remote, even though the MCP port bound fine. A failed
    forward is still reported by ssh on stderr ("Warning: remote port
    forwarding failed for listen port N").
    """
    return "ssh -N -R 0.0.0.0:%d:127.0.0.1:%d %s" % (
        public_port,
        http_port,
        remote,
    )


def start_tunnel(public_port: int, http_port: int, remote: str):
    """Start the reverse tunnel as a child process, or None on failure.

    The child inherits stdout/stderr, so ssh prompts and errors stay
    visible in this terminal.
    """
    argv = ssh_command(public_port, http_port, remote).split()
    try:
        child = subprocess.Popen(argv)  # pylint: disable=consider-using-with
    except OSError as exc:
        print("ssh tunnel not started: %s" % exc)
        return None
    time.sleep(1.0)
    if child.poll() is not None:
        print(
            "ssh tunnel exited with code %s (see its output above)"
            % child.returncode
        )
        return None
    print("ssh tunnel running (pid %d)" % child.pid)
    return child


def stop_tunnel(child) -> None:
    """Terminate the tunnel child process, waiting briefly."""
    if child is None or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
    print("ssh tunnel stopped")


def start_http(api, remote=None) -> None:
    """Load or create the run credentials, print the banner, serve HTTP."""
    if not CONF["session_secret"]:
        CONF["session_secret"] = load_session_secret()
    if not CONF["session_secret"]:
        CONF["session_secret"] = secrets.token_hex(32)
        save_session_secret(CONF["session_secret"])
    credentials = load_credentials()
    if credentials:
        username = str(credentials["username"])
        password = str(credentials["password"])
        created = time.strftime(
            "%Y-%m-%d %H:%M",
            time.localtime(credentials.get("created_at", 0) or 0),
        )
        cred_header = (
            "Consent page credentials (persisted in %s, created %s;"
            % (CONF["credentials_file"], created)
        )
    else:
        username = "mcp-" + secrets.token_hex(3)
        password = secrets.token_urlsafe(12)
        save_credentials(username, password)
        cred_header = (
            "Consent page credentials (new, persisted in %s;"
            % CONF["credentials_file"]
        )
    USERS[username] = hash_password(password)
    public_port = CONF["public_port"] or CONF["http_port"]
    print(
        "YActivePRO MCP server v%s (HTTP MCP on %s:%d%s)"
        % (
            VERSION,
            CONF["bind"],
            CONF["http_port"],
            ", default MCP port" if CONF["http_port"] == 37880 else "",
        )
    )
    print()
    print(cred_header)
    print("renew with --reset-credentials):")
    print("  username: %s" % username)
    print("  password: %s" % password)
    print()
    print("Active-Pro application: %s" % api.status())
    print()
    print("Local MCP endpoint (POST /login with the credentials for a token):")
    print("  http://%s:%d/mcp" % (CONF["bind"], CONF["http_port"]))
    if remote:
        print()
        print(
            "Reverse tunnel to '%s' starting now (~/.ssh/config"
            " holds its credentials):" % remote
        )
        print("  %s" % ssh_command(public_port, CONF["http_port"], remote))
        print()
        print("Public MCP endpoint once the tunnel is up:")
        print("  http://<public host of %s>:%d/mcp" % (remote, public_port))
        print()
        print("Notes:")
        print(
            "- a publicly bound -R port needs 'GatewayPorts "
            "clientspecified' (or 'yes') in sshd_config on %s;" % remote
        )
        print(
            "  without it the port stays bound to the loopback of %s." % remote
        )
        print(
            "- cloud MCP clients need https: put the usual TLS reverse "
            "proxy on %s" % remote
        )
        print(
            "  and set YAPD_MCP_OAUTH_ISSUER_URL, or rely on X-Forwarded-* "
            "headers."
        )
    else:
        print()
        print("Potential remote MCP endpoint (restart with --remote NAME):")
        print("  http://<public host of NAME>:%d/mcp" % public_port)
    if CONF["bind"] not in ("127.0.0.1", "localhost", "::1"):
        print()
        print(
            "Warning: listening on %s exposes the MCP endpoint to"
            % CONF["bind"]
        )
        print("the network; the credentials above are the protection.")
    print()
    print("Ctrl+C to stop.")
    sys.stdout.flush()
    tunnel = None
    if remote:
        tunnel = start_tunnel(public_port, CONF["http_port"], remote)
    server = McpHTTPServer((CONF["bind"], CONF["http_port"]), Handler)
    server.api = api
    server.remote = remote

    def _stop_request(signum, frame):
        # pylint: disable=unused-argument
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, _stop_request)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_tunnel(tunnel)


def serve_stdio(api) -> None:
    """Serve MCP over stdio, one JSON message per line."""
    print(
        "YActivePRO MCP server v%s (MCP over stdio, no HTTP endpoint)"
        % VERSION,
        file=sys.stderr,
    )
    print(
        "HTTP MCP endpoint when started with --http or --remote NAME"
        " (default MCP port 37880, YAPD_MCP_HTTP_PORT/--port override):",
        file=sys.stderr,
    )
    print(
        "  http://%s:%d/mcp" % (CONF["bind"], CONF["http_port"]),
        file=sys.stderr,
    )
    print(
        "Remote MCP endpoint once --remote NAME and its ssh tunnel are up:",
        file=sys.stderr,
    )
    print(
        "  http://<public host of NAME>:%d/mcp"
        % (CONF["public_port"] or CONF["http_port"]),
        file=sys.stderr,
    )
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = handle(message if isinstance(message, dict) else {}, api)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


# --------------------------------------------------------------- selftest


def selftest() -> None:
    """Run the built-in checks, no network access needed."""
    # skills: topics known, each carries its markers
    assert set(SKILLS) == {"overview", "aft", "adp", "automation"}
    assert "---DATA---" in SKILLS["aft"]
    assert "timestamp, source, channel, data" in SKILLS["aft"]
    assert '"err=I2C_NACK, retry=1"' in SKILLS["aft"]
    assert _AFT_FIXED_LINE.strip() in SKILLS["aft"]
    assert "0x7F" in SKILLS["adp"]
    assert "export_between_cursors" in SKILLS["automation"]
    assert "get_skills" in SKILLS["overview"]
    # tools: every API tool has a dispatch entry and vice versa
    names = [tool["name"] for tool in TOOLS]
    assert len(names) == len(set(names))
    assert set(names) == set(TOOL_COMMANDS) | {
        "get_skills",
        "get_docs",
        "feedback",
    }
    for tool in TOOLS:
        assert tool["inputSchema"]["type"] == "object"
        assert isinstance(tool["inputSchema"]["properties"], dict)
        assert isinstance(tool["inputSchema"].get("required", []), list)
        for param in tool["inputSchema"]["properties"].values():
            assert param["type"] and param["description"]
    # mode maps match the ActiveProApi.py CLI values
    assert MODE_MAP_D["pwm"] == 3 and MODE_MAP_D["tristate"] == 0
    assert MODE_MAP_A0["dc"] == 6
    assert MODE_MAP_A1["ramp"] == 7 and MODE_MAP_A1["triangle"] == 10
    # zoom range normalization (CLI behavior)
    assert _zoom_range(1, 2) == (1.0, 2.0)
    assert _zoom_range(2, 1) == (1.0, 2.0)
    assert _zoom_range(0, 0) == (0.0, 0.001)
    assert _zoom_range(5, 5) == (4.999, 5.0)
    # negative times resolved against the capture duration
    assert _from_capture_end(-600, 900) == 300.0
    assert _from_capture_end(-600, 100) == 0.0
    # default path extension
    assert get_absolute_path("x", ".csv").endswith(".csv")
    assert os.path.isabs(get_absolute_path("x", ".csv"))
    assert os.path.splitext(get_absolute_path("x.csv", ".csv"))[1] == ".csv"
    assert _posix_absolute_path("x", ".csv").endswith(".csv")
    # write policy: /tmp allows yapd_ overwrites only, elsewhere the
    # file must not exist; realpath defeats /tmp/../ traversal
    selftest_tmp = os.path.join(
        _tmp_root(), "yactivepro-selftest-%d" % os.getpid()
    )
    os.makedirs(selftest_tmp, exist_ok=True)
    yapd_csv = os.path.join(selftest_tmp, "yapd_data.csv")
    assert check_write_path(
        yapd_csv, ".csv", tmp_root=selftest_tmp
    ) == os.path.realpath(yapd_csv)
    with open(yapd_csv, "w", encoding="utf-8") as fh:
        fh.write("a,b\n1,2\n")
    assert check_write_path(
        yapd_csv, ".csv", tmp_root=selftest_tmp
    ) == os.path.realpath(
        yapd_csv
    )  # yapd_ overwrite allowed
    other_csv = os.path.join(selftest_tmp, "other.csv")
    with open(other_csv, "w", encoding="utf-8") as fh:
        fh.write("x")
    try:
        check_write_path(other_csv, ".csv", tmp_root=selftest_tmp)
        raise AssertionError("expected ValueError for %s" % other_csv)
    except ValueError:
        pass
    new_csv = os.path.join(selftest_tmp, "new.csv")
    assert check_write_path(
        new_csv, ".csv", tmp_root=selftest_tmp
    ) == os.path.realpath(
        new_csv
    )  # does not exist yet: ok
    outside_dir = selftest_tmp + "-outside"
    os.makedirs(outside_dir, exist_ok=True)
    existing_out = os.path.join(outside_dir, "exists.csv")
    with open(existing_out, "w", encoding="utf-8") as fh:
        fh.write("x")
    try:
        check_write_path(existing_out, ".csv", tmp_root=selftest_tmp)
        raise AssertionError("expected ValueError for existing outside")
    except ValueError:
        pass
    missing_out = os.path.join(outside_dir, "missing.csv")
    assert check_write_path(
        missing_out, ".csv", tmp_root=selftest_tmp
    ) == os.path.realpath(missing_out)
    # traversal through the scratch root lands outside it (existing
    # file there -> refused)
    try:
        check_write_path(
            os.path.join(
                selftest_tmp,
                "..",
                os.path.basename(outside_dir),
                "exists.csv",
            ),
            ".csv",
            tmp_root=selftest_tmp,
        )
        raise AssertionError("expected ValueError for traversal")
    except ValueError:
        pass
    # read policy: anything under the scratch root, or a recorded write
    assert check_read_path(
        yapd_csv, tmp_root=selftest_tmp
    ) == os.path.realpath(yapd_csv)
    try:
        check_read_path(existing_out, tmp_root=selftest_tmp)
        raise AssertionError("expected ValueError for unrecorded outside")
    except ValueError:
        pass
    # application host is configurable (WSL: the Windows host IP)
    assert ActiveProClient(host="10.1.2.3").host == "10.1.2.3"
    assert ActiveProClient().host == "localhost"
    assert CONF["app_host"]
    # knowledge tool descriptions carry an example call
    for tool in KNOWLEDGE_TOOLS:
        assert (
            '"topic"' in tool["description"] or '"page"' in tool["description"]
        )
    for tool in FEEDBACK_TOOLS:
        assert '"feedback"' in tool["description"]
    # pages: unique keys, slugs non-empty, resolution works
    assert len(PAGES) == len(set(PAGES))
    for key, (slug, title) in PAGES.items():
        assert slug and title and " " not in slug
        assert page_url(key) == DOCS_BASE + SLUG_FIXUPS.get(slug, slug)
    assert PAGES["license-agreement"][0] == "license-agreement"
    assert page_url("license-agreement").endswith("/liscence-agreement")
    url = "https://www.activefirmwaretools.com/usersmanualold/aft-format"
    assert page_url(url) == url
    for bad in ("https://example.com/x", "no-such-page", ""):
        try:
            page_url(bad)
            raise AssertionError("expected ValueError for %r" % bad)
        except ValueError:
            pass
    # html extraction: visible text kept, script dropped
    sample = "<p>Hello <b>world</b></p><script>alert(1)</script><p>x</p>"
    text = html_to_text(sample)
    assert "Hello world" in text and "alert" not in text
    assert "By using this website" not in html_to_text(
        "By using this website, cookies. Read more in our privacy policy."
        "<h1>Title</h1>"
    )
    assert "\u00ad" not in html_to_text("<p>x\u00ady</p><p>\u00ad</p>")
    cleaned = clean_site_text(
        "Skip to Content\nDownload\nBuy Now\n"
        "Active-Pro Ultra pre-orders ship Nov 16.\n\n# Real content"
    )
    assert "Buy Now" not in cleaned and "# Real content" in cleaned
    assert clean_site_text("a\n\n\n\nb") == "a\n\nb"
    # passwords
    stored = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", stored)
    assert not verify_password("wrong", stored)
    # session tokens
    token = issue_token("alice", "secret-hmac", 1)
    assert verify_token(token, "secret-hmac") == "alice"
    assert verify_token(token, "other-key") is None
    assert verify_token(issue_token("bob", "secret-hmac", -1), "s") is None
    # PKCE S256 (RFC 7636 appendix B test vector)
    assert (
        pkce_s256("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )
    # OAuth blobs (refresh tokens): round trip, tamper, expiry
    old_secret = CONF["session_secret"]
    old_clients = CONF["oauth_clients_file"]
    old_credentials = CONF["credentials_file"]
    old_secret_file = CONF["session_secret_file"]
    old_feedback = CONF["feedback_file"]
    old_written = CONF["written_files_file"]
    CONF["session_secret"] = "selftest-secret"
    tmp = os.path.join(_tmp_root(), "yactivepro-selftest-%d" % os.getpid())
    os.makedirs(tmp, exist_ok=True)
    CONF["oauth_clients_file"] = os.path.join(tmp, "oauth_clients.json")
    CONF["credentials_file"] = os.path.join(tmp, "credentials.json")
    CONF["session_secret_file"] = os.path.join(tmp, "session_secret")
    CONF["feedback_file"] = os.path.join(tmp, "feedback.md")
    CONF["written_files_file"] = os.path.join(tmp, "written_files.json")
    try:
        # credentials persistence: create, load, delete
        assert load_credentials() is None
        assert delete_credentials() is False
        save_credentials("mcp-abc123", "pw-one")
        creds = load_credentials()
        assert creds is not None
        assert creds["username"] == "mcp-abc123"
        assert creds["password"] == "pw-one"
        assert int(creds["created_at"]) > 0
        assert delete_credentials() is True
        assert load_credentials() is None
        with open(CONF["credentials_file"], "w", encoding="utf-8") as fh:
            fh.write("{not json")
        assert load_credentials() is None
        # session secret persistence: round trip
        assert load_session_secret() == ""
        save_session_secret("hex-one")
        assert load_session_secret() == "hex-one"
        # feedback file: header once, one section per entry
        record_feedback("add a page about triggers")
        record_feedback("the zoom tool should accept ms too")
        with open(CONF["feedback_file"], encoding="utf-8") as fh:
            feedback_text = fh.read()
        assert feedback_text.count("# YActivePRO MCP server feedback") == 1
        assert feedback_text.count("\n## 20") == 2
        assert "add a page about triggers" in feedback_text
        assert "feedback recorded" in run_tool(
            "feedback", {"feedback": "a dispatch check"}
        )
        try:
            run_tool("feedback", {"feedback": "   "})
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        # written-files tracking: a save outside the scratch root
        # becomes readable only once recorded
        assert load_written_files() == set()
        rec = os.path.realpath(
            os.path.abspath(".yapd-selftest-rec-%d.csv" % os.getpid())
        )
        with open(rec, "w", encoding="utf-8") as fh:
            fh.write("saved\n")
        try:
            check_read_path(rec, tmp_root=tmp)
            raise AssertionError("expected ValueError before recording")
        except ValueError:
            pass
        try:
            run_tool("read_file", {"path": rec})
            raise AssertionError("expected ValueError before recording")
        except ValueError:
            pass
        record_written_file(rec)
        assert rec in load_written_files()
        assert check_read_path(rec, tmp_root=tmp) == rec
        record_written_file(rec)  # idempotent
        assert len(load_written_files()) == 1
        assert "saved" in run_tool("read_file", {"path": rec})

        # a successful save/export through run_api_tool records the path
        class _OkApi:
            def send_command(self, _command):
                """Pretend the application accepted the command."""
                return "OK"

            def list_instances(self):
                """Pretend no instance listing is available."""
                return ""

        out = run_api_tool("save_capture", {"path": missing_out}, _OkApi())
        assert out == "OK"
        assert os.path.realpath(missing_out) in load_written_files()

        # a failed save does not record
        class _FailApi(_OkApi):
            def send_command(self, _command):
                """Pretend the application refused the command."""
                return "ERROR disk full"

        run_api_tool("save_capture", {"path": new_csv}, _FailApi())
        assert os.path.realpath(new_csv) not in load_written_files()
        # read_back: a successful save also returns the file content
        rb_csv = os.path.join(tmp, "yapd_rb.csv")
        with open(rb_csv, "w", encoding="utf-8") as fh:
            fh.write("a,b\n1,2\n")
        out = run_api_tool(
            "export_between_cursors",
            {"path": rb_csv, "read_back": True},
            _OkApi(),
        )
        assert out.startswith("OK") and "1,2" in out
        out = run_api_tool(
            "export_between_cursors", {"path": rb_csv}, _OkApi()
        )
        assert out == "OK"  # without read_back: just the app answer
        for tool in TOOLS:
            if tool["name"] in WRITE_PATH_TOOLS:
                props = tool["inputSchema"]["properties"]
                assert "read_back" in props and "max_chars" in props
                if tool["name"] in EXPORT_FILTER_TOOLS:
                    assert "decoded_only" in props
        # decoded_only drops the logic/analog rows from the export
        mini_aft = os.path.join(tmp, "yapd_mini.aft")
        with open(mini_aft, "w", encoding="utf-8") as fh:
            fh.write(
                "Active-Pro Firmware Trace (.aft)\n\n---DATA---\n"
                "timestamp, source, channel, data\n"
                "1.000000000, L, 2, 0\n"
                "1.000001000, B, 2, 0x0D\n"
                "1.000002000, AN, 1, 3.3V\n"
            )
        out = run_api_tool(
            "export_ai_snapshot",
            {"path": mini_aft, "decoded_only": True},
            _OkApi(),
        )
        with open(mini_aft, encoding="utf-8") as fh:
            kept = fh.read()
        assert "dropped 2" in out
        assert ", L, " not in kept and ", AN, " not in kept
        assert "0x0D" in kept
        mini_csv = os.path.join(tmp, "yapd_mini.csv")
        with open(mini_csv, "w", encoding="utf-8") as fh:
            fh.write(
                "Seconds, Output, Device, Channel\n"
                '1.0,"85","LOGIC","7to0"\n'
                '1.1,"0x0D","MyUART B","2"\n'
            )
        out = run_api_tool(
            "export_between_cursors",
            {"path": mini_csv, "decoded_only": True},
            _OkApi(),
        )
        with open(mini_csv, encoding="utf-8") as fh:
            kept = fh.read()
        assert "dropped 1" in out and "7to0" not in kept
        assert "0x0D" in kept
        # .aft export endpoint + the new command mappings
        assert PATH_TOOLS["export_ai_snapshot"] == ".aft"
        assert "export_ai_snapshot" in WRITE_PATH_TOOLS
        # export tools also take device_filter; search takes from
        for tool in TOOLS:
            if tool["name"] in EXPORT_FILTER_TOOLS:
                assert "device_filter" in tool["inputSchema"]["properties"]
            if tool["name"] == "search":
                assert "from" in tool["inputSchema"]["properties"]
        # device_filter keeps only the listed rows (.csv: Device column)
        filt_csv = os.path.join(tmp, "yapd_filt.csv")
        with open(filt_csv, "w", encoding="utf-8") as fh:
            fh.write(
                "Seconds, Output, Device, Channel\n"
                '1.0,"TX=AT+CRESET[D]=EoP","UART_PACKETS","0"\n'
                '1.1,"0x0D","MyUART B","2"\n'
                '1.2,"85","LOGIC","7to0"\n'
            )
        out = run_api_tool(
            "export_between_cursors",
            {"path": filt_csv, "device_filter": "UART_PACKETS"},
            _OkApi(),
        )
        with open(filt_csv, encoding="utf-8") as fh:
            kept = fh.read()
        assert "dropped 2" in out and "kept UART_PACKETS" in out
        assert "UART_PACKETS" in kept and "MyUART B" not in kept
        assert "LOGIC" not in kept
        # .aft: device_filter works on the source letter
        filt_aft = os.path.join(tmp, "yapd_filt.aft")
        with open(filt_aft, "w", encoding="utf-8") as fh:
            fh.write(
                "Active-Pro Firmware Trace (.aft)\n\n---DATA---\n"
                "timestamp, source, channel, data\n"
                "1.000000000, B, 2, 0x0D\n"
                "1.000001000, L, 2, 0\n"
            )
        out = run_api_tool(
            "export_ai_snapshot",
            {"path": filt_aft, "device_filter": "B"},
            _OkApi(),
        )
        with open(filt_aft, encoding="utf-8") as fh:
            kept = fh.read()
        assert "0x0D" in kept and ", L, " not in kept
        assert "kept B" in out

        # the export answer echoes the X1/X2 range actually exported
        class _RangeApi(_OkApi):
            def send_command(self, command, _timeout=10):
                """Answer fixed cursor positions."""
                if command == "GetCursorX1":
                    return "328.5"
                if command == "GetCursorX2":
                    return "330.5"
                return "OK"

        range_csv = os.path.join(tmp, "yapd_range.csv")
        with open(range_csv, "w", encoding="utf-8") as fh:
            fh.write("a\n")
        out = run_api_tool(
            "export_between_cursors", {"path": range_csv}, _RangeApi()
        )
        assert "exported range X1=328.5..X2=330.5" in out
        # csv export correction: the [HH] hex byte and =EoP markers of
        # the raw export are decoded in the written file (flag off:
        # the raw markers stay)
        fix_csv = os.path.join(tmp, "yapd_fix.csv")
        with open(fix_csv, "w", encoding="utf-8") as fh:
            fh.write(
                "Seconds, Output, Device, Channel\n"
                '1.0,"TX=AT+CRESET[D]=EoP","UART_PACKETS","0"\n'
                '1.1,"[41][42][0A]","MyUART B","2"\n'
            )
        old_fix = CONF["correct_csv_export"]
        assert isinstance(old_fix, bool)
        try:
            CONF["correct_csv_export"] = True
            out = run_api_tool(
                "export_between_cursors", {"path": fix_csv}, _OkApi()
            )
            with open(fix_csv, encoding="utf-8") as fh:
                fixed = fh.read()
            assert "csv corrected: 2 lines" in out
            assert "TX=AT+CRESET\\r\\n" in fixed and "[D]" not in fixed
            assert '"AB\\n"' in fixed
            with open(fix_csv, "w", encoding="utf-8") as fh:
                fh.write('1.0,"[0D]","X","0"\n')
            CONF["correct_csv_export"] = False
            out = run_api_tool(
                "export_between_cursors", {"path": fix_csv}, _OkApi()
            )
            with open(fix_csv, encoding="utf-8") as fh:
                assert fh.read() == '1.0,"[0D]","X","0"\n'
            assert "corrected" not in out
        finally:
            CONF["correct_csv_export"] = old_fix
        # no markers: no rewrite, plain answer
        plain_csv = os.path.join(tmp, "yapd_plain.csv")
        with open(plain_csv, "w", encoding="utf-8") as fh:
            fh.write("a,b\n1,2\n")
        out = run_api_tool(
            "export_between_cursors", {"path": plain_csv}, _OkApi()
        )
        assert out == "OK"
        # unit: the decoder itself
        assert _decode_csv_export_text("[41][0D][0A][07][22]=EoP") == (
            'A\\r\\n\\x07""\\n'
        )
        assert _correct_csv_export(os.path.join(tmp, "yapd_missing.csv")) == 0
        # read_file returns text bare (no wrapper line); a trailing
        # note appears only when offset/truncation applies
        out = run_tool("read_file", {"path": rb_csv})
        assert out == "a,b\n1,2\n"
        out = run_tool(
            "read_file", {"path": rb_csv, "offset": 2, "max_chars": 100}
        )
        assert out.startswith("b\n1,2\n") and "[read_file:" in out

        class _RecApi:
            def __init__(self):
                """Start with an empty command recording."""
                self.sent = []
                self.timeouts = []

            def send_command(self, command, timeout=10):
                """Record the command and its timeout, answer OK."""
                self.sent.append(command)
                self.timeouts.append(timeout)
                return "OK"

            def list_instances(self):
                """Pretend no instance listing is available."""
                return ""

        api_rec = _RecApi()

        class _SearchApi(_RecApi):
            def send_command(self, command, timeout=10):
                """Answer a fixed timestamp for Search commands."""
                if command.startswith("Search "):
                    self.sent.append(command)
                    return "12.5"
                return super().send_command(command, timeout)

        # search passes through untouched: the application advances
        # past each match itself (full internal precision), so the
        # tool must not move the cursor (the displayed cursor is
        # quantized to 0.1 ms and would land back on the match)
        # search passes through untouched: the application advances
        # past each match itself at full internal precision, so the
        # tool must not move the cursor (the displayed cursor is
        # quantized to 0.1 ms and would land back on the match)
        srec = _SearchApi()
        out = run_api_tool("search", {"text": "NACK"}, srec)
        assert out == "12.5"
        assert srec.sent == ["Search NACK"]
        rec2 = _RecApi()
        out = run_api_tool("search", {"text": "x"}, rec2)
        assert out == "OK"
        assert rec2.sent == ["Search x"]

        # search dedup: re-finds inside the same decoded item (within
        # one 0.1 ms quantum of the last hit) are skipped, so one
        # occurrence returns one hit
        class _SeqApi(_RecApi):
            def __init__(self, answers):
                super().__init__()
                self.answers = list(answers)

            def send_command(self, command, timeout=10):
                """Answer from a scripted sequence of search results."""
                if command.startswith("Search "):
                    self.sent.append(command)
                    return self.answers.pop(0) if self.answers else "NOTFOUND"
                return super().send_command(command, timeout)

        seq = _SeqApi(["82.4644", "82.4645", "9175.6", "9175.6", "NOTFOUND"])
        assert run_api_tool("search", {"text": "RDY"}, seq) == "82.4644"
        assert run_api_tool("search", {"text": "RDY"}, seq) == "9175.6"
        assert run_api_tool("search", {"text": "RDY"}, seq) == "NOTFOUND"

        # search with from=: anchored at the given timestamp, and the
        # shared cursor is restored afterwards (stateless, parallel-safe)
        class _FromApi(_RecApi):
            def send_command(self, command, timeout=10):
                """Answer a fixed current cursor and search hit."""
                if command == "GetCursorCurrent":
                    self.sent.append(command)
                    return "42.0"
                if command.startswith("Search "):
                    self.sent.append(command)
                    return "100.25"
                return super().send_command(command, timeout)

        fapi = _FromApi()
        out = run_api_tool("search", {"text": "RDY", "from": 100}, fapi)
        assert out == "100.25"
        assert fapi.sent == [
            "GetCursorCurrent",
            "SetCursorCurrent 100.0",
            "Search RDY",
            "SetCursorCurrent 42.0",
        ]
        aft = os.path.join(tmp, "yapd_snap.aft")
        run_api_tool("export_ai_snapshot", {"path": aft}, api_rec)
        assert any(
            c.startswith("ExportAISnapshotBetweenCursors ")
            for c in api_rec.sent
        )
        # the range echo queried the cursors after the export
        assert api_rec.sent[-2:] == ["GetCursorX1", "GetCursorX2"]
        assert os.path.realpath(aft) in load_written_files()
        run_api_tool("get_cursor", {"cursor": "x1"}, api_rec)
        assert api_rec.sent[-1] == "GetCursorX1"
        run_api_tool("set_theme", {"theme": "dark"}, api_rec)
        assert api_rec.sent[-1] == "SetDarkMode"
        run_api_tool("get_analog", {"channel": 5}, api_rec)
        assert api_rec.sent[-1] == "GetCH5"
        run_api_tool("append_analysis_context", {"text": "rev D"}, api_rec)
        assert api_rec.sent[-1] == "AppendAnalysisContext rev D"
        run_api_tool("get_analysis_context", {}, api_rec)
        assert api_rec.sent[-1] == "GetAnalysisContext"
        run_api_tool("select_device", {"index": 2}, api_rec)
        assert api_rec.sent[-1] == "SelectDevice 2"
        try:
            run_api_tool("get_cursor", {"cursor": "bogus"}, api_rec)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        # trigger suite / pipeline / buffer / channel-config mappings
        for name, args, expected in (
            ("apply_changes", {}, "ApplyChanges"),
            ("is_processing", {}, "IsProcessing"),
            ("is_triggered", {}, "IsTriggered"),
            ("goto_trigger", {"index": 3}, "GoToTrigger 3"),
            ("set_trigger_mode", {"mode": "auto"}, "SetTriggerMode auto"),
            (
                "set_trigger_source_type",
                {"source": "atext"},
                "SetTriggerSourceType atext",
            ),
            (
                "set_trigger_condition",
                {"condition": "pulsehighgreater"},
                "SetTriggerCondition pulsehighgreater",
            ),
            (
                "set_trigger_pulse_width",
                {"value": 100, "unit": "us"},
                "SetTriggerPulseWidth 100 us",
            ),
            ("set_buffer_size", {"megabytes": 100}, "SetBufferSize 100"),
            (
                "set_pre_trigger_mode",
                {"mode": "keeplast"},
                "SetPreTriggerMode keeplast",
            ),
            (
                "set_post_trigger_mode",
                {"mode": "stopafterseconds"},
                "SetPostTriggerMode stopafterseconds",
            ),
            (
                "set_post_trigger_triggers",
                {"count": 4},
                "SetPostTriggerTriggers 4",
            ),
            (
                "logic_channel_on_off",
                {"channel": 3, "on": True},
                "LogicCH3On",
            ),
            (
                "analog_channel_on_off",
                {"channel": 2, "on": False},
                "AnalogCH2Off",
            ),
            (
                "set_device_mode",
                {"device": "b", "mode": 2},
                "DeviceBMode 2",
            ),
            (
                "set_device_setting",
                {"device": "A", "value": 115200},
                "DeviceASetting 115200",
            ),
            ("set_threshold_level", {"voltage": 1.8}, "ThresholdLevel 1.8"),
            (
                "set_label",
                {"target": "device", "index": "c", "text": "I2C bus"},
                "DeviceCLabel I2C bus",
            ),
            (
                "set_label",
                {"target": "logic", "index": "0", "text": "MOTOR_EN"},
                "LogicCH0Label MOTOR_EN",
            ),
            (
                "set_device_visibility",
                {"device_label": "d", "visible": False},
                "HideDeviceD",
            ),
        ):
            run_api_tool(name, args, api_rec)
            assert api_rec.sent[-1] == expected, (name, api_rec.sent[-1])
        # blocking pipeline commands use the long timeout
        run_api_tool("apply_changes", {}, api_rec)
        assert api_rec.timeouts[-1] == 600
        run_api_tool("reprocess_triggers", {}, api_rec)
        assert api_rec.timeouts[-1] == 600
        run_api_tool("is_triggered", {}, api_rec)
        assert api_rec.timeouts[-1] == 10
        # set_trigger_cursor resolves like the other time tools
        run_api_tool("set_trigger_cursor", {"time": 1.5}, api_rec)
        assert api_rec.sent[-1] == "SetTriggerCursor 1.5"
        try:
            run_api_tool(
                "set_label",
                {"target": "bogus", "index": "1", "text": "x"},
                api_rec,
            )
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        try:
            run_api_tool(
                "set_device_visibility",
                {"device_label": "E", "visible": True},
                api_rec,
            )
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        # read_file: text round trip, base64 round trip, policy refusal
        text_out = run_tool("read_file", {"path": yapd_csv})
        assert "a,b" in text_out and "1,2" in text_out
        png = os.path.join(tmp, "yapd_shot.png")
        payload = b"\x89PNG\r\n\x1a\n" + b"0" * 100
        with open(png, "wb") as bfh:
            bfh.write(payload)
        bin_out = run_tool("read_file", {"path": png})
        assert "base64" in bin_out
        assert (
            base64.b64decode(bin_out.split(":\n", 1)[1], validate=True)
            == payload
        )
        # offset pages into large text/binary files (chars resp. bytes)
        big = os.path.join(tmp, "yapd_big.txt")
        with open(big, "w", encoding="utf-8") as fh:
            fh.write("0123456789" * 50)  # 500 chars
        out = run_tool(
            "read_file", {"path": big, "offset": 490, "max_chars": 100}
        )
        # text comes back bare, with a trailing note for the offset
        assert out.startswith("0123456789")
        assert "from char 490" in out and "[read_file:" in out
        out = run_tool("read_file", {"path": png, "offset": 8})
        assert "from byte 8" in out
        assert (
            base64.b64decode(out.split(":\n", 1)[1], validate=True)
            == payload[8:]
        )
        # an existing file outside the scratch root, not written by a
        # save/export tool, is refused
        try:
            run_tool("read_file", {"path": os.path.abspath(__file__)})
            raise AssertionError("expected ValueError for unrecorded path")
        except ValueError:
            pass
        try:
            run_tool("read_file", {"path": ""})
            raise AssertionError("expected ValueError for empty path")
        except ValueError:
            pass
        try:
            run_tool("read_file", {"path": os.path.join(tmp, "missing.csv")})
            raise AssertionError("expected ValueError for missing file")
        except ValueError:
            pass
        blob = oauth_sign({"k": "refresh", "u": "alice"}, 3600)
        verified = oauth_verify(blob)
        assert verified is not None and verified["u"] == "alice"
        assert oauth_verify(blob[:-2] + "zz") is None
        assert oauth_verify(oauth_sign({"k": "refresh"}, -1)) is None
        # client registry: register + exact redirect_uri matching
        client = register_client(
            {"redirect_uris": ["http://127.0.0.1/cb"], "client_name": "test"}
        )
        assert load_clients()[client["client_id"]]["redirect_uris"] == [
            "http://127.0.0.1/cb"
        ]
        try:
            register_client({"redirect_uris": []})
            raise AssertionError("expected ValueError")
        except ValueError:
            pass
        query = {
            "client_id": [client["client_id"]],
            "redirect_uri": ["http://127.0.0.1/cb"],
            "code_challenge": [pkce_s256("verifier-1")],
            "state": ["xyz"],
        }
        error, params = validate_authorize(query)
        assert error is None and params is not None
        assert params["state"] == "xyz"
        assert (
            validate_authorize(dict(query, client_id=["unknown"]))[0]
            == "invalid_client"
        )
        assert (
            validate_authorize(dict(query, redirect_uri=["http://evil/cb"]))[0]
            == "invalid_redirect_uri"
        )
        # authorization codes: single use, PKCE-bound
        code = oauth_code_issue(
            client["client_id"],
            "http://127.0.0.1/cb",
            pkce_s256("verifier-1"),
            "alice",
            "mcp",
        )
        assert (
            oauth_code_consume(
                code, client["client_id"], "http://127.0.0.1/cb", "wrong"
            )
            is None
        )
        assert (
            oauth_code_consume(
                code, client["client_id"], "http://127.0.0.1/cb", "wrong"
            )
            is None
        )
        assert (
            oauth_code_consume(
                code, client["client_id"], "http://127.0.0.1/cb", "verifier-1"
            )
            is None
        )  # a failed attempt burns the code
        code = oauth_code_issue(
            client["client_id"],
            "http://127.0.0.1/cb",
            pkce_s256("verifier-1"),
            "alice",
            "mcp",
        )
        params = oauth_code_consume(
            code, client["client_id"], "http://127.0.0.1/cb", "verifier-1"
        )
        assert params is not None and params["username"] == "alice"
        # an omitted redirect_uri is accepted, a wrong one is not
        code = oauth_code_issue(
            client["client_id"],
            "http://127.0.0.1/cb",
            pkce_s256("verifier-1"),
            "alice",
            "mcp",
        )
        params = oauth_code_consume(
            code, client["client_id"], "", "verifier-1"
        )
        assert params is not None and params["username"] == "alice"
        code = oauth_code_issue(
            client["client_id"],
            "http://127.0.0.1/cb",
            pkce_s256("verifier-1"),
            "alice",
            "mcp",
        )
        assert (
            oauth_code_consume(
                code, client["client_id"], "http://other/cb", "verifier-1"
            )
            is None
        )
        assert (
            oauth_code_consume(
                code, client["client_id"], "http://127.0.0.1/cb", "verifier-1"
            )
            is None
        )
        # metadata + consent page
        metadata = as_metadata("https://mcp.example")
        assert metadata["issuer"] == "https://mcp.example"
        assert metadata["code_challenge_methods_supported"] == ["S256"]
        assert rs_metadata("https://mcp.example")["authorization_servers"] == [
            "https://mcp.example"
        ]
        assert 'name="username"' in consent_page(params or {})
        # ssh tunnel suggestion
        assert ssh_command(1, 2, "srv").endswith("srv")
        assert "ExitOnForwardFailure" not in ssh_command(1, 2, "srv")
        # the tunnel child runs the printed command as an argv list
        argv = ssh_command(37880, 37880, "srv").split()
        assert argv[0] == "ssh" and argv[-1] == "srv" and "-N" in argv
    finally:
        CONF["session_secret"] = old_secret
        CONF["oauth_clients_file"] = old_clients
        CONF["credentials_file"] = old_credentials
        CONF["session_secret_file"] = old_secret_file
        CONF["feedback_file"] = old_feedback
        CONF["written_files_file"] = old_written

        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(selftest_tmp + "-outside", ignore_errors=True)
        try:
            os.remove(
                os.path.realpath(
                    os.path.abspath(".yapd-selftest-rec-%d.csv" % os.getpid())
                )
            )
        except OSError:
            pass
    # HTTP integration: discovery variants, CORS, 401 challenge, DELETE,
    # the full OAuth code flow and an MCP initialize over HTTP
    CONF["session_secret"] = "selftest-secret"
    USERS["alice"] = hash_password("pw-one")
    server = McpHTTPServer(("127.0.0.1", 0), Handler)
    server.api = None
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:

        def req(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=body, headers=headers or {})
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return resp, data

        resp, data = req("GET", "/healthz")
        assert resp.status == 200 and json.loads(data)["status"] == "ok"
        for path in (
            "/.well-known/oauth-protected-resource",
            "/.well-known/oauth-protected-resource/mcp",
        ):
            resp, data = req("GET", path)
            assert resp.status == 200
            assert json.loads(data)["authorization_servers"]
        for path in (
            "/.well-known/oauth-authorization-server",
            "/.well-known/openid-configuration",
        ):
            resp, data = req("GET", path)
            assert resp.status == 200
            assert json.loads(data)["token_endpoint"].endswith("/token")
        # CORS preflight and headers on errors too
        resp, _ = req(
            "OPTIONS",
            "/mcp",
            headers={
                "Origin": "https://client.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert resp.status == 204
        assert resp.getheader("Access-Control-Allow-Origin") == "*"
        resp, _ = req(
            "POST",
            "/mcp",
            body=b"{}",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 401
        assert resp.getheader("Access-Control-Allow-Origin") == "*"
        challenge = resp.getheader("WWW-Authenticate")
        assert "resource_metadata=" in challenge
        assert "/oauth-protected-resource/mcp" in challenge
        assert "invalid_token" not in challenge
        resp, _ = req(
            "POST",
            "/mcp",
            body=b"{}",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer bogus",
            },
        )
        assert resp.status == 401
        assert 'error="invalid_token"' in resp.getheader("WWW-Authenticate")
        # login -> token -> DELETE + non-SSE GET + full OAuth flow
        resp, data = req(
            "POST",
            "/login",
            body=json.dumps(
                {"username": "alice", "password": "pw-one"}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        token = json.loads(data)["token"]
        auth = {"Authorization": "Bearer " + token}
        # an answered-but-undrained request body must not corrupt the
        # next request on the same keep-alive connection (random 501s
        # through a connection-reusing reverse proxy)
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST",
            "/mcp",
            body=b'{"jsonrpc":"2.0","id":9,' b'"method":"ping"}',
            headers={"Content-Type": "application/json"},
        )
        r1 = conn.getresponse()
        r1.read()
        assert r1.status == 401
        conn.request(
            "POST",
            "/mcp",
            body=b'{"jsonrpc":"2.0","id":10,' b'"method":"ping"}',
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + token,
            },
        )
        r2 = conn.getresponse()
        d2 = r2.read()
        conn.close()
        assert r2.status == 200 and json.loads(d2)["result"] == {}
        resp, _ = req("DELETE", "/mcp", headers=auth)
        assert resp.status == 200
        resp, _ = req(
            "GET",
            "/mcp",
            headers=dict(auth, Accept="application/json, text/event-stream"),
        )
        assert resp.status == 405
        resp, data = req(
            "POST",
            "/register",
            body=json.dumps(
                {"redirect_uris": ["http://127.0.0.1/cb"], "client_name": "it"}
            ).encode(),
            headers={"Content-Type": "application/json"},
        )
        client_id = json.loads(data)["client_id"]
        verifier = "it-verifier-0123456789-0123456789"
        challenge_q = pkce_s256(verifier)
        resp, _ = req(
            "GET",
            "/authorize?response_type=code"
            "&client_id=%s&redirect_uri=http://127.0.0.1/cb"
            "&code_challenge=%s&code_challenge_method=S256"
            % (client_id, challenge_q),
        )
        assert resp.status == 200
        form = urllib.parse.urlencode(
            {
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/cb",
                "code_challenge": challenge_q,
                "code_challenge_method": "S256",
                "state": "s1",
                "username": "alice",
                "password": "pw-one",
            }
        ).encode()
        resp, _ = req(
            "POST",
            "/authorize",
            body=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status == 302
        code = urllib.parse.parse_qs(
            urllib.parse.urlsplit(resp.getheader("Location")).query
        )["code"][0]
        form = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1/cb",
                "code_verifier": verifier,
            }
        ).encode()
        resp, data = req(
            "POST",
            "/token",
            body=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        access = json.loads(data)["access_token"]
        resp, data = req(
            "POST",
            "/mcp",
            body=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "it", "version": "0"},
                    },
                }
            ).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer " + access,
            },
        )
        assert resp.status == 200
        assert json.loads(data)["result"]["serverInfo"]["name"] == (
            SERVER_NAME
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        CONF["session_secret"] = old_secret
        USERS.pop("alice", None)

    # handle(): requests, notifications, dispatch errors
    def call_rpc(message, api=None):
        """handle() requiring a reply (notifications return None)."""
        reply = handle(message, api)
        assert reply is not None
        return reply

    reply = call_rpc({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert reply == {"jsonrpc": "2.0", "id": 1, "result": {}}
    assert handle({"jsonrpc": "2.0", "method": "initialized"}) is None
    reply = call_rpc({"jsonrpc": "2.0", "id": 2, "method": "bogus"})
    assert reply["error"]["code"] == -32601
    reply = call_rpc({"jsonrpc": "2.0", "id": 3, "method": "initialize"})
    assert (
        reply["result"]["serverInfo"]["name"] == SERVER_NAME
        and reply["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    )
    assert "instructions" not in reply["result"]

    class _StubApi:
        """Minimal api to check the initialize status report."""

        def status(self):
            """Return a fixed status line."""
            return "stub status line"

    reply = call_rpc(
        {"jsonrpc": "2.0", "id": 30, "method": "initialize"}, _StubApi()
    )
    assert reply["result"]["instructions"] == "stub status line"
    # initialize answers a supported requested protocol version
    reply = call_rpc(
        {
            "jsonrpc": "2.0",
            "id": 31,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"},
        }
    )
    assert reply["result"]["protocolVersion"] == "2024-11-05"
    reply = call_rpc(
        {
            "jsonrpc": "2.0",
            "id": 33,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25"},
        }
    )
    assert reply["result"]["protocolVersion"] == "2025-11-25"
    reply = call_rpc(
        {
            "jsonrpc": "2.0",
            "id": 32,
            "method": "initialize",
            "params": {"protocolVersion": "bogus"},
        }
    )
    assert reply["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    # SSE frames and the legacy-client detection
    sse_expected = b"event: endpoint\ndata: /mcp\n\n"
    assert sse_frame("endpoint", "/mcp") == sse_expected
    assert sse_frame("message", "{}") == b"event: message\ndata: {}\n\n"
    assert wants_sse("text/event-stream")
    assert not wants_sse("application/json, text/event-stream")
    assert not wants_sse("application/json")
    assert not wants_sse("")
    # /token accepts urlencoded and JSON bodies (LM Studio posts JSON)
    urlenc_body = token_body_params(
        "application/x-www-form-urlencoded",
        b"grant_type=authorization_code&code=42",
    )
    assert urlenc_body["grant_type"] == ["authorization_code"]
    assert urlenc_body["code"] == ["42"]
    json_body = token_body_params(
        "application/json",
        json.dumps({"grant_type": "authorization_code", "code": 42}).encode(),
    )
    assert json_body["grant_type"] == ["authorization_code"]
    assert json_body["code"] == ["42"]  # JSON values are stringified
    assert token_body_params("application/json", b"{not json") == {}
    assert token_body_params("application/json", b"[1]") == {}
    assert token_body_params("", b"a=1") == {"a": ["1"]}
    # dropped connections are silenced, not a server error
    assert _is_disconnect_error(ConnectionResetError())
    assert _is_disconnect_error(BrokenPipeError())
    assert not _is_disconnect_error(ValueError("x"))
    reply = call_rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
    assert len(reply["result"]["tools"]) == len(TOOLS)
    request = {"jsonrpc": "2.0", "id": 5, "method": "tools/call"}
    reply = call_rpc(
        dict(request, params={"name": "get_skills", "arguments": {}})
    )
    assert "get_skills" in reply["result"]["content"][0]["text"]
    reply = call_rpc(
        dict(request, params={"name": "no_such_tool", "arguments": {}})
    )
    assert reply["result"]["isError"] is True


def _reachable(host: str, port: int) -> bool:
    """Whether a TCP connect to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=0.05):
            pass
        return True
    except OSError:
        return False


def main() -> None:
    """Parse the command line and start the requested mode."""
    parser = argparse.ArgumentParser(
        prog=SERVER_NAME,
        description="MCP server for the Active-Pro application.",
        epilog=(
            "environment variables:\n"
            "  YAPD_MCP_HOST (Active-Pro host), YAPD_MCP_BIND,\n"
            "  YAPD_MCP_HTTP_PORT, YAPD_MCP_PUBLIC_PORT\n"
            "  YAPD_MCP_SESSION_SECRET, YAPD_MCP_SESSION_TTL_HOURS\n"
            "  YAPD_MCP_STATE_DIR, YAPD_MCP_OAUTH_ISSUER_URL,\n"
            "  YAPD_MCP_OAUTH_REFRESH_TTL_HOURS, YAPD_MCP_CORRECT_CSV_EXPORT"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the built-in checks and exit",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="serve HTTP on YAPD_MCP_BIND (default port 37880)",
    )
    parser.add_argument(
        "--port",
        type=int,
        metavar="N",
        help="HTTP port (default: YAPD_MCP_HTTP_PORT or 37880)",
    )
    parser.add_argument(
        "--bind",
        metavar="ADDRESS",
        help=(
            "HTTP bind address (default: YAPD_MCP_BIND or 127.0.0.1);"
            " 0.0.0.0 listens on every interface"
        ),
    )
    parser.add_argument(
        "--host",
        metavar="ADDRESS",
        help=(
            "Active-Pro application host (default: YAPD_MCP_HOST or"
            " localhost; under WSL, use the Windows host IP)"
        ),
    )
    parser.add_argument(
        "--correct-csv-export",
        dest="correct_csv_export",
        action="store_true",
        default=True,
        help=(
            "correct the exported .csv in place: decode the [HH] hex "
            "byte and =EoP markers (default; YAPD_MCP_CORRECT_CSV_EXPORT"
            "=0 also disables it)"
        ),
    )
    parser.add_argument(
        "--no-correct-csv-export",
        dest="correct_csv_export",
        action="store_false",
        help="disable the CSV export content correction",
    )
    parser.add_argument(
        "--remote",
        metavar="NAME",
        help=(
            "serve HTTP and start the ssh reverse tunnel to NAME "
            "(the command line is printed; Ctrl+C stops both)"
        ),
    )
    parser.add_argument(
        "--reset-credentials",
        action="store_true",
        help=(
            "delete the persisted consent-page credentials and the "
            "session secret; a --http/--remote start creates new ones"
        ),
    )
    try:
        import argcomplete  # pylint: disable=import-outside-toplevel

        argcomplete.autocomplete(parser)
    except ImportError:
        pass
    args = parser.parse_args()
    if args.selftest:
        selftest()
        print("yactivepro_mcp: all selftests passed")
        return
    if args.reset_credentials:
        if delete_credentials():
            print(
                "persisted credentials deleted: %s" % CONF["credentials_file"]
            )
        else:
            print("no persisted credentials at %s" % CONF["credentials_file"])
        try:
            os.remove(CONF["session_secret_file"])
            print("session secret deleted: %s" % CONF["session_secret_file"])
        except FileNotFoundError:
            pass
        if not (args.http or args.remote):
            print("new ones are created on the next --http or --remote start")
            return
    if args.port:
        CONF["http_port"] = args.port
    if args.bind:
        CONF["bind"] = args.bind
    if args.host:
        CONF["app_host"] = args.host
    CONF["correct_csv_export"] = args.correct_csv_export
    api = ActiveProClient(host=CONF["app_host"])
    port = api.autodetect()
    found = port != api.PORT_BASE or _reachable(api.host, port)
    if found:
        api.port = port
        if api.port == api.PORT_BASE:
            note = " (default Active-Pro Debugger port)"
        else:
            note = ""
        message = "Active-Pro application port: %s:%d%s" % (
            api.host,
            api.port,
            note,
        )
    else:
        message = (
            "no Active-Pro application found on %s; using the "
            "default Active-Pro Debugger port %d" % (api.host, api.port)
        )
    print(message, file=sys.stderr)
    if (
        not found
        and api.host == "localhost"
        and os.environ.get("WSL_DISTRO_NAME")
    ):
        print(
            "WSL: the Windows host is not localhost; restart with"
            " --host WINDOWS_IP or set YAPD_MCP_HOST (the IP is often"
            " the default gateway, see 'ip route show default')",
            file=sys.stderr,
        )
    if args.http or args.remote:
        start_http(api, args.remote)
    else:
        serve_stdio(api)


if __name__ == "__main__":
    main()
