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
    "Ragnarök: the Goblin Stock Market ", color=0xFF7F50, y_offset=7
)
# stock prices to go here

messageBottom = Message(fontpool.find_font("dejavu"))
messageBottom.add_text(
    " Ragnarök: the Goblin Stock Market", color=0x3ABF24, y_offset=-11
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
                url = f"http://{backend_host}/api/public/ticker"
                print(f"GET {url}")
                resp = requests.get(url, timeout=5)
                try:
                    code = getattr(resp, "status_code", None)
                    if code is not None and code != 200:
                        show_backend_misconfig(
                            f"Backend HTTP error at {url}: status {code}",
                            "http",
                            f"err {code}",
                        )
                    else:
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
                            messageTop.clear()
                            messageTop.add_text(
                                ticker_message, color=0xFF7F50, y_offset=7
                            )
                            print("Ticker message loaded.")
                        else:
                            show_backend_misconfig(
                                f"Ticker JSON at {url} has no usable 'message' key.",
                                "ticker",
                                "bad json",
                            )
                finally:
                    resp.close()
            except Exception as exc:
                show_backend_misconfig(
                    f"Ticker request failed for {backend_host}: {exc}",
                    "ticker",
                    "fetch fail",
                )
else:
    print("Missing BACKEND_HOST; skipping ticker fetch.")

dual_scroll.run_forever(messageboard, messageBottom, messageTop, y=0, px_per_sec=20)
