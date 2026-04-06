# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

import time
from adafruit_matrixportal.matrix import Matrix
from messageboard import MessageBoard
from messageboard.fontpool import FontPool
from messageboard.message import Message

matrix = Matrix(width=128, height=32, bit_depth=5, rotation=180)
messageboard = MessageBoard(matrix)
# messageboard.set_background("images/background.bmp")
fontpool = FontPool()
fontpool.add_font("arial", "fonts/Arial-10.pcf")

# Create the message ahead of time
message = Message(fontpool.find_font("arial"), mask_color=0x7C9930, opacity=0.8)
# message.add_image("images/maskedstar.bmp")
message.add_text("Ragnarök: the Goblin Stock Market", color=0x3ABF24
# , x_offset=2, y_offset=20x7C9930
)

while True:
    # Animate the message
    messageboard.animate(message, "Loop", "bounce_in")
    # time.sleep(1)
    # messageboard.animate(message, "Scroll", "out_to_left")
