# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

from adafruit_matrixportal.matrix import Matrix
from messageboard import MessageBoard
from messageboard.fontpool import FontPool
from messageboard.message import Message

import os
import time

import wifi

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

status_color_ok = 0x3ABF24
status_color_err = 0xFF4040

bootStatus = Message(fontpool.find_font("dejavu"))

def show_boot_status(status: str, color: int) -> None:
    bootStatus.clear()
    # Top line: status. Bottom line: WiFi (common).
    # Message.add_text() advances an internal x cursor, so reset it for line 2.
    bootStatus.add_text(f" {status} ", color=color, y_offset=7)
    bootStatus._cursor[0] = 0  # revert cursor to 0
    bootStatus.add_text(" WiFi ", color=color, y_offset=-11)
    messageboard.animate(bootStatus, "Static", "show")


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
dual_scroll.run_forever(messageboard, messageBottom, messageTop, y=0, px_per_sec=20)
