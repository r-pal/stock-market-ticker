# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Two-row scrolling: one Message moves left, one right, composited each frame."""

import time
import bitmaptools
import displayio


def _crop_image_for_position(image, x, y, buffer_x_offset, buffer_y_offset, disp):
    """Match MessageBoard._draw: keep blit destinations valid; crop when off-screen left/top."""
    while image.width + x < 0:
        x += disp.width
    while image.height + y < 0:
        y += disp.height
    while x + buffer_x_offset < 0:
        new_image = displayio.Bitmap(
            image.width - disp.width, image.height, 65535
        )
        bitmaptools.blit(
            new_image,
            image,
            0,
            0,
            x1=disp.width,
            y1=0,
            x2=image.width,
            y2=image.height,
        )
        x += disp.width
        image = new_image
    while y + buffer_y_offset < 0:
        new_image = displayio.Bitmap(
            image.width, image.height - disp.height, 65535
        )
        bitmaptools.blit(
            new_image,
            image,
            0,
            0,
            x1=0,
            y1=disp.height,
            x2=image.width,
            y2=image.height,
        )
        y += disp.height
        image = new_image
    return image, x, y


def _composite_message(dest_buf, board, message, x, y):
    """Same compositing as MessageBoard._draw (foreground + alphablend)."""
    image = message.buffer
    mask_color = message.mask_color
    if mask_color > 65535:
        mask_color = displayio.ColorConverter().convert(mask_color)

    buffer_x_offset = board._buffer_width - board.display.width
    buffer_y_offset = board._buffer_height - board.display.height

    image, x, y = _crop_image_for_position(
        image, x, y, buffer_x_offset, buffer_y_offset, board.display
    )

    foreground = displayio.Bitmap(board._buffer_width, board._buffer_height, 65535)
    foreground.fill(mask_color)
    bitmaptools.blit(
        foreground,
        image,
        x + buffer_x_offset,
        y + buffer_y_offset,
    )
    bitmaptools.alphablend(
        dest_buf,
        dest_buf,
        foreground,
        displayio.Colorspace.RGB565,
        1.0,
        message.opacity,
        blendmode=message.blendmode,
        skip_source2_index=mask_color,
    )


def run_forever(board, message_left, message_right, y=0, px_per_sec=20, frame_hz=60.0):
    """
    Scroll message_left to the left and message_right to the right, forever.

    Uses the same double-buffer and compositing as MessageBoard._draw.
    """
    display = board.display
    buffer_x_offset = board._buffer_width - display.width
    buffer_y_offset = board._buffer_height - display.height

    x1 = 0
    x2 = -message_right.buffer.width
    frame_dt = 1.0 / frame_hz
    last_t = time.monotonic()

    while True:
        now = time.monotonic()
        dt = now - last_t
        last_t = now

        step = max(1, int(px_per_sec * dt))

        x1 -= step
        if x1 < -message_left.buffer.width:
            x1 = display.width

        x2 += step
        if x2 > display.width:
            x2 = -message_right.buffer.width

        buf = board._dbl_buf.active_buffer

        bitmaptools.blit(
            buf,
            board._background,
            buffer_x_offset,
            buffer_y_offset,
        )

        _composite_message(buf, board, message_left, x1, y)
        _composite_message(buf, board, message_right, x2, y)

        board._dbl_buf.show()
        time.sleep(frame_dt)
