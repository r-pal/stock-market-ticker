# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Two-stream scrolling: two Messages both move left, composited each frame."""

import time
import bitmaptools
import displayio


def _composite_message(dest_buf, board, message, x, y, foreground):
    """
    Same compositing idea as MessageBoard._draw (foreground + alphablend).

    ``foreground`` must be a scratch RGB565 bitmap of board buffer size, reused
    every call — allocating it each frame triggers GC and makes scroll slow down
    over time on Matrix / ESP32-S3.
    """
    image = message.buffer
    w, h = image.width, image.height
    disp = board.display

    while w + x < 0:
        x += disp.width
    while h + y < 0:
        y += disp.height

    buffer_x_offset = board._buffer_width - disp.width
    buffer_y_offset = board._buffer_height - disp.height
    dx = x + buffer_x_offset
    dy = y + buffer_y_offset

    fg_w = foreground.width
    fg_h = foreground.height
    src_x1 = max(0, -dx)
    src_y1 = max(0, -dy)
    dst_x = max(0, dx)
    dst_y = max(0, dy)
    avail_w = fg_w - dst_x
    avail_h = fg_h - dst_y
    src_x2 = min(w, src_x1 + avail_w)
    src_y2 = min(h, src_y1 + avail_h)
    if src_x2 <= src_x1 or src_y2 <= src_y1:
        return

    mask_color = message.mask_color
    if mask_color > 65535:
        mask_color = displayio.ColorConverter().convert(mask_color)

    foreground.fill(mask_color)
    bitmaptools.blit(
        foreground,
        image,
        dst_x,
        dst_y,
        x1=src_x1,
        y1=src_y1,
        x2=src_x2,
        y2=src_y2,
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


def run_forever(
    board,
    message_left,
    message_right,
    y=0,
    px_per_sec_bottom=20,
    px_per_sec_top=20,
    px_per_sec=None,
    frame_hz=60.0,
):
    """
    Scroll message_left and message_right both to the left, forever.

    ``message_left`` / ``message_right`` are usually the bottom and top ticker
    (e.g. ``messageBottom``, ``messageTop``).

    Each stream moves at most **one pixel per loop**; average rates are
    ``px_per_sec_bottom`` and ``px_per_sec_top``. If ``px_per_sec`` is set, it
    applies to both streams (handy for a single speed). ``frame_hz`` is unused
    and kept for callers that still pass it.

    Uses the same double-buffer and compositing as MessageBoard._draw.
    Second stream starts half a display width ahead so both can share the same y.
    """
    _ = frame_hz  # unused; kept so existing callers can pass frame_hz=

    if px_per_sec is not None:
        px_per_sec_bottom = px_per_sec
        px_per_sec_top = px_per_sec

    display = board.display
    buffer_x_offset = board._buffer_width - display.width
    buffer_y_offset = board._buffer_height - display.height

    x1 = 0
    x2 = display.width // 2
    pace = max(px_per_sec_bottom, px_per_sec_top, 0.001)
    loop_dt = 1.0 / pace
    foreground = displayio.Bitmap(
        board._buffer_width, board._buffer_height, 65535
    )

    last_t = time.monotonic()
    accum_bottom = 0.0
    accum_top = 0.0

    while True:
        t_loop = time.monotonic()
        dt = t_loop - last_t
        last_t = t_loop

        accum_bottom += px_per_sec_bottom * dt
        accum_top += px_per_sec_top * dt
        if accum_bottom >= 1.0:
            accum_bottom -= 1.0
            x1 -= 1
            if x1 < -message_left.buffer.width:
                x1 = display.width
        if accum_top >= 1.0:
            accum_top -= 1.0
            x2 -= 1
            if x2 < -message_right.buffer.width:
                x2 = display.width

        buf = board._dbl_buf.active_buffer

        bitmaptools.blit(
            buf,
            board._background,
            buffer_x_offset,
            buffer_y_offset,
        )

        _composite_message(buf, board, message_left, x1, y, foreground)
        _composite_message(buf, board, message_right, x2, y, foreground)

        board._dbl_buf.show()
        elapsed = time.monotonic() - t_loop
        time.sleep(max(0, loop_dt - elapsed))
