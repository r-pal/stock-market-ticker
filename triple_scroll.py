# SPDX-FileCopyrightText: 2023 Melissa LeBlanc-Williams for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""Multi-stream horizontal tickertape scrolling on the visible panel (64x32 etc.)."""

import time
import bitmaptools
import displayio


def fit_messageboard_to_panel(board):
    """
    MessageBoard defaults to 2x panel size for animations. Tickertape scroll uses
    a 1:1 buffer so pixel positions match the physical matrix (e.g. 64x32).
    """
    try:
        from messageboard.doublebuffer import DoubleBuffer
    except ImportError:
        return False

    disp = board.display
    panel_w = disp.width
    panel_h = disp.height
    if board._buffer_width == panel_w and board._buffer_height == panel_h:
        return True

    board._buffer_width = panel_w
    board._buffer_height = panel_h
    board._dbl_buf = DoubleBuffer(disp, panel_w, panel_h)
    board.set_background(0x000000)
    return True


def _composite_message(
    dest_buf, board, message, x, y, foreground, panel_w, panel_h, band_height=None
):
    """
    Composite one message into the panel-sized foreground, then alphablend onto
    the active buffer. Coordinates are in panel space (0 .. panel_w-1).
    """
    image = message.buffer
    w, h = image.width, image.height

    while w + x < 0:
        x += panel_w
    while h + y < 0:
        y += panel_h

    buffer_x_offset = board._buffer_width - panel_w
    buffer_y_offset = board._buffer_height - panel_h
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

    if band_height is not None:
        band_top = dy
        band_bottom = band_top + band_height
        if dst_y < band_top:
            skip = band_top - dst_y
            src_y1 += skip
            dst_y = band_top
        if src_y2 <= src_y1:
            return
        max_h = band_bottom - dst_y
        if max_h <= 0:
            return
        if src_y2 - src_y1 > max_h:
            src_y2 = src_y1 + max_h

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
    streams,
    poll_interval_s=None,
    poll_callback=None,
    frame_hz=60.0,
):
    """
    Scroll tickertape streams left, one panel pixel at a time per stream.

    Each stream dict: ``message``, ``px_per_sec``, optional ``x`` (initial offset).

    Scroll timing uses a fixed frame interval (``frame_hz``) so movement is not
    tied to variable draw time. Place text rows via Message ``y_offset``; keep
    compositing ``y`` at 0.
    """
    fit_messageboard_to_panel(board)

    display = board.display
    panel_w = display.width
    panel_h = display.height
    buffer_x_offset = board._buffer_width - panel_w
    buffer_y_offset = board._buffer_height - panel_h
    frame_dt = 1.0 / frame_hz

    n = len(streams)
    state = []
    for index, spec in enumerate(streams):
        default_x = (index * panel_w) // n if n else 0
        state.append(
            {
                "message": spec["message"],
                "y": spec.get("y", 0),
                "band_height": spec.get("band_height"),
                "px_per_sec": spec["px_per_sec"],
                "x": spec.get("x", default_x),
                "accum": 0.0,
            }
        )

    foreground = displayio.Bitmap(panel_w, panel_h, 65535)

    next_poll_at = None
    if poll_interval_s is not None and poll_callback is not None:
        next_poll_at = time.monotonic() + float(poll_interval_s)

    while True:
        t_loop = time.monotonic()

        for st in state:
            st["accum"] += st["px_per_sec"] * frame_dt
            if st["accum"] >= 1.0:
                st["accum"] -= 1.0
                st["x"] -= 1
                msg = st["message"]
                if st["x"] < -msg.buffer.width:
                    st["x"] = panel_w

        buf = board._dbl_buf.active_buffer

        bitmaptools.blit(
            buf,
            board._background,
            buffer_x_offset,
            buffer_y_offset,
        )

        for st in state:
            _composite_message(
                buf,
                board,
                st["message"],
                st["x"],
                st["y"],
                foreground,
                panel_w,
                panel_h,
                band_height=st.get("band_height"),
            )

        board._dbl_buf.show()

        if next_poll_at is not None:
            now = time.monotonic()
            if now >= next_poll_at:
                try:
                    poll_callback()
                except Exception as exc:
                    print("poll_callback:", exc)
                next_poll_at = time.monotonic() + float(poll_interval_s)

        elapsed = time.monotonic() - t_loop
        time.sleep(max(0, frame_dt - elapsed))
