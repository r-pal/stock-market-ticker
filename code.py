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

import dual_scroll

print("booting...")

matrix = Matrix(width=64, height=32, bit_depth=5, rotation=0)
messageboard = MessageBoard(matrix)
# messageboard.set_background("images/background.bmp")
fontpool = FontPool()
fontpool.add_font("arial", "fonts/Arial-10.pcf")
fontpool.add_font("dejavu", "fonts/DejaVuSans-10.pcf")

messageTop = Message(fontpool.find_font("dejavu"))
messageTop.add_text(
    "_", color=0xFF7F50, y_offset=7
)
    # Ragnarök: the Goblin Stock Market 
# stock prices to go here

messageBottom = Message(fontpool.find_font("dejavu"))
messageBottom.add_text(
    "Ragnarök: the Goblin Stock Market ", color=0x3ABF24, y_offset=-11
)
# personalised messages to go here

ssid = os.getenv("CIRCUITPY_WIFI_SSID")
password = os.getenv("CIRCUITPY_WIFI_PASSWORD")
backend_host = os.getenv("BACKEND_HOST")


status_color_ok = 0x3ABF24
status_color_err = 0xFF4040

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


def fetch_and_apply_public_ticker(requests_session, backend_host_spec, message_top):
    """
    GET /api/public/ticker and replace message_top text on success.
    Returns True if the message was updated. Logs and returns False otherwise.
    """
    url = f"http://{backend_host_spec}/api/public/ticker"
    resp = requests_session.get(url, timeout=5)
    try:
        code = getattr(resp, "status_code", None)
        if code is not None and code != 200:
            print(f"ticker poll: HTTP {code} from {url}")
            return False
        try:
            payload = resp.json()
        except Exception:
            payload = json.loads(resp.text)
        ticker_message = (
            payload.get("message")
            if isinstance(payload, dict)
            else None
        )
        if isinstance(ticker_message, str) and ticker_message.strip():
            message_top.clear()
            message_top.add_text(ticker_message, color=0xFF7F50, y_offset=7)
            print("Ticker message updated.")
            return True
        print("ticker poll: no usable 'message' in JSON")
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

# Fetch ticker JSON and set it as the top message
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
                print(f"GET http://{backend_host}/api/public/ticker")
                try:
                    ok = fetch_and_apply_public_ticker(
                        requests, backend_host, messageTop
                    )
                except Exception as exc:
                    show_backend_misconfig(
                        f"Ticker request failed for {backend_host}: {exc}",
                        "ticker",
                        "fetch fail",
                    )
                else:
                    if not ok:
                        show_backend_misconfig(
                            f"Ticker JSON at http://{backend_host}/api/public/ticker "
                            "has no usable 'message' or non-200 response.",
                            "ticker",
                            "bad json",
                        )
                    else:
                        ticker_poll_interval_s = 20

                        def _ticker_poll():
                            fetch_and_apply_public_ticker(
                                requests, backend_host, messageTop
                            )

                        ticker_poll_callback = _ticker_poll
            except Exception as exc:
                show_backend_misconfig(
                    f"Ticker request failed for {backend_host}: {exc}",
                    "ticker",
                    "fetch fail",
                )
else:
    print("Missing BACKEND_HOST; skipping ticker fetch.")

dual_scroll.run_forever(
    messageboard,
    messageBottom,
    messageTop,
    y=0,
    px_per_sec_bottom=10,
    px_per_sec_top=30,
    poll_interval_s=ticker_poll_interval_s,
    poll_callback=ticker_poll_callback,
)
