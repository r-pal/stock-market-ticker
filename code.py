# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

from adafruit_matrixportal.matrix import Matrix
from messageboard import MessageBoard
from messageboard.fontpool import FontPool
from messageboard.message import Message

import dual_scroll

matrix = Matrix(width=128, height=32, bit_depth=5, rotation=0)
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

dual_scroll.run_forever(messageboard, messageBottom, messageTop, y=0, px_per_sec=20)
