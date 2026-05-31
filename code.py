# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

from adafruit_matrixportal.matrix import Matrix
from messageboard import MessageBoard
from messageboard.fontpool import FontPool
from messageboard.message import Message

import os
import time

import json
import ssl
import socketpool

import wifi

import adafruit_requests

import triple_scroll

print("booting...")

matrix = Matrix(width=64, height=32, bit_depth=5, rotation=0)
messageboard = MessageBoard(matrix)
triple_scroll.fit_messageboard_to_panel(messageboard)
# messageboard.set_background("images/background.bmp")
fontpool = FontPool()
fontpool.add_font("arial", "fonts/Arial-10.pcf")
fontpool.add_font("dejavu", "fonts/DejaVuSans-10.pcf")

status_color_ok = 0x3ABF24
status_color_err = 0xFF4040

color_wares = 0xFF7F50
color_accounts = 0x0000FF
color_messages = 0x00CC00
color_trend_up = 0x00CC00
color_trend_down = 0xFF0000

BAND_HEIGHT = 10
BAND_GAP = 1
# MessageBoard y_offset is relative to an ~11px cursor baseline, not display row.
# For 10+1+10+1+10 layout: wares rows 0-9, messages 11-20, accounts 22-31.
Y_WARES = -(BAND_HEIGHT + BAND_GAP)  # -11
Y_MESSAGES = 0
Y_ACCOUNTS = BAND_HEIGHT

messageWares = Message(fontpool.find_font("dejavu"))
messageWares.add_text("_", color=color_wares, y_offset=Y_WARES)

messageMessages = Message(fontpool.find_font("dejavu"))
messageMessages.add_text("_", color=color_messages, y_offset=Y_MESSAGES)

messageAccounts = Message(fontpool.find_font("dejavu"))
messageAccounts.add_text("_", color=color_accounts, y_offset=Y_ACCOUNTS)

ssid = os.getenv("CIRCUITPY_WIFI_SSID")
password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
backend_host = os.getenv("BACKEND_HOST")

bootStatus = Message(fontpool.find_font("dejavu"))


def show_two_line_status(top: str, bottom: str, color: int) -> None:
    bootStatus.clear()
    bootStatus.add_text(f" {top} ", color=color, y_offset=7)
    bootStatus._cursor[0] = 0
    bootStatus.add_text(f" {bottom} ", color=color, y_offset=-11)
    messageboard.animate(bootStatus, "Static", "show")


def show_boot_status(status: str, color: int) -> None:
    show_two_line_status(status, "WiFi", color)


def parse_backend_host(spec):
    spec = (spec or "").strip()
    if not spec:
        return None, None
    if ":" not in spec:
        return spec, 80
    host, port_s = spec.rsplit(":", 1)
    host = host.strip()
    if host and port_s.isdigit():
        return host, int(port_s)
    return None, None


def tcp_reachable(pool, host, port, timeout_s=5):
    sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
    sock.settimeout(timeout_s)
    try:
        sock.connect((host, port))
    finally:
        sock.close()


def apply_joined_line(message, items, color, y_offset, sep="   "):
    """Build a single-colour tickertape line from string items."""
    if not isinstance(items, list) or not items:
        return False

    parts = []
    for entry in items:
        text = str(entry).strip() if entry is not None else ""
        if text:
            parts.append(text)
    if not parts:
        return False

    message.clear()
    message.add_text(sep.join(parts) + " ", color=color, y_offset=y_offset)
    return True


def apply_wares_line(message, wares, y_offset):
    """Build top tickertape from wares list (name + trend-coloured price)."""
    if not isinstance(wares, list) or not wares:
        return False

    sep = "   "
    segments = []
    for item in wares:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        price = str(item.get("price") or "").strip()
        trend = item.get("trend")
        if not name and not price:
            continue
        if segments:
            segments.append((sep, color_wares))
        if name:
            segments.append((name + " ", color_wares))
        if trend == "up" and price:
            segments.append(("\u25b2" + price, color_trend_up))
        elif trend == "down" and price:
            segments.append(("\u25bc" + price, color_trend_down))
        elif price:
            segments.append((price, color_wares))

    if not segments:
        return False

    message.clear()
    for text, color in segments:
        message.add_text(text, color=color, y_offset=y_offset)
    message.add_text(" ", color=color_wares, y_offset=y_offset)
    return True


def apply_accounts_line(message, accounts, y_offset):
    return apply_joined_line(message, accounts, color_accounts, y_offset)


def apply_messages_line(message, messages, y_offset):
    return apply_joined_line(message, messages, color_messages, y_offset)


def fetch_and_apply_tickertape(
    requests_session, backend_host_spec, message_wares, message_messages, message_accounts
):
    """
    GET /api/tickertape and refresh wares, messages, and accounts lines.
    Returns True if at least one line was updated. Logs and returns False otherwise.
    """
    url = f"http://{backend_host_spec}/api/tickertape"
    resp = requests_session.get(url, timeout=5)
    try:
        code = getattr(resp, "status_code", None)
        if code is not None and code != 200:
            print(f"tickertape poll: HTTP {code} from {url}")
            return False
        try:
            payload = resp.json()
        except Exception:
            payload = json.loads(resp.text)
        if not isinstance(payload, dict):
            print("tickertape poll: expected JSON object")
            return False

        wares_ok = apply_wares_line(message_wares, payload.get("wares"), Y_WARES)
        messages_ok = apply_messages_line(
            message_messages, payload.get("messages"), Y_MESSAGES
        )
        accounts_ok = apply_accounts_line(
            message_accounts, payload.get("accounts"), Y_ACCOUNTS
        )
        if wares_ok or messages_ok or accounts_ok:
            print("Tickertape updated.")
            return True
        print("tickertape poll: no usable wares, messages, or accounts")
        return False
    finally:
        resp.close()


def show_backend_misconfig(msg_print, line1, line2):
    print(msg_print)
    show_two_line_status(line1, line2, status_color_err)
    time.sleep(5)


connected = False
last_error = None

if not ssid:
    last_error = "missing CIRCUITPY_WIFI_SSID"
elif password is None:
    last_error = "missing CIRCUITPY_WIFI_PASSWORD"
else:
    for _ in range(3):
        try:
            if wifi.radio.connected:
                connected = True
                break
            print(f"Connecting to {ssid}")
            show_boot_status("connecting", status_color_ok)
            wifi.radio.connect(ssid, password)
            if wifi.radio.connected:
                connected = True
                break
            last_error = "not connected"
        except Exception as exc:  # CircuitPython raises RuntimeError / OSError variants
            last_error = exc
            time.sleep(1)

if not connected:
    print(f"WiFi error: {last_error}")
    show_boot_status("fail", status_color_err)
    while True:
        time.sleep(1)

ip = getattr(wifi.radio, "ipv4_address", None)
print(f"WiFi connected: {ip}")
show_boot_status(f"ok {ip}", status_color_ok)
time.sleep(3)

ticker_poll_interval_s = None
ticker_poll_callback = None

# Fetch tickertape JSON and set wares, messages, and accounts lines
if backend_host:
    print(f"Backend host (from settings): {backend_host}")
    host, port = parse_backend_host(backend_host)
    pool = socketpool.SocketPool(wifi.radio)

    if host is None:
        show_backend_misconfig(
            "BACKEND_HOST is invalid (use host:port, e.g. 192.168.0.78:8080).",
            "bad host",
            "settings",
        )
    else:
        try:
            tcp_reachable(pool, host, port)
        except Exception as exc:
            show_backend_misconfig(
                f"Backend not reachable at {host}:{port} (wrong IP, server down, "
                f"or not listening on 0.0.0.0). {exc}",
                "backend",
                "unreachable",
            )
        else:
            try:
                show_boot_status("ticker", status_color_ok)
                requests = adafruit_requests.Session(pool, ssl.create_default_context())
                print(f"GET http://{backend_host}/api/tickertape")
                try:
                    ok = fetch_and_apply_tickertape(
                        requests,
                        backend_host,
                        messageWares,
                        messageMessages,
                        messageAccounts,
                    )
                except Exception as exc:
                    show_backend_misconfig(
                        f"Tickertape request failed for {backend_host}: {exc}",
                        "ticker",
                        "fetch fail",
                    )
                else:
                    if not ok:
                        show_backend_misconfig(
                            f"Tickertape JSON at http://{backend_host}/api/tickertape "
                            "has no usable wares, messages, or accounts.",
                            "ticker",
                            "bad json",
                        )
                    else:
                        ticker_poll_interval_s = 20

                        def _ticker_poll():
                            fetch_and_apply_tickertape(
                                requests,
                                backend_host,
                                messageWares,
                                messageMessages,
                                messageAccounts,
                            )

                        ticker_poll_callback = _ticker_poll
            except Exception as exc:
                show_backend_misconfig(
                    f"Tickertape request failed for {backend_host}: {exc}",
                    "ticker",
                    "fetch fail",
                )
else:
    print("Missing BACKEND_HOST; skipping tickertape fetch.")

TICKERTAPE_STREAMS = [
    {"message": messageWares, "px_per_sec": 30},
    {"message": messageMessages, "px_per_sec": 20},
    {"message": messageAccounts, "px_per_sec": 10},
]

triple_scroll.run_forever(
    messageboard,
    TICKERTAPE_STREAMS,
    poll_interval_s=ticker_poll_interval_s,
    poll_callback=ticker_poll_callback,
)
