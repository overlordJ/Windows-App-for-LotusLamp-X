"""
app.py — LotusLamp X Windows Controller
========================================
A modern Windows desktop app for controlling ELK-BLEDOM / LotusLamp X
Bluetooth RGB LED strips directly from your PC.

Features:
  • BLE device scan & connect
  • Power on / off toggle
  • RGB color picker with live hex input
  • Quick-colour palette (10 preset swatches)
  • Brightness slider (0–100 %)
  • Built-in effects selector with speed control
  • Colour-wheel canvas for intuitive hue/saturation selection
  • Status bar with connection info
"""

from __future__ import annotations

import asyncio
import colorsys
import logging
import math
import threading
from typing import Optional

import customtkinter as ctk
from tkinter import colorchooser
import tkinter as tk

from ble_controller import LotusLampController, EFFECTS

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# ── Theme ─────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Colour constants ──────────────────────────────────────────────────────────
ACCENT       = "#2196F3"
ACCENT_HOVER = "#1976D2"
DANGER       = "#F44336"
SUCCESS      = "#4CAF50"
SURFACE      = "#1E1E2E"
CARD         = "#252538"
BORDER       = "#353550"

QUICK_COLORS = [
    ("#FF0000", "Red"),
    ("#FF8C00", "Orange"),
    ("#FFD700", "Yellow"),
    ("#00FF00", "Green"),
    ("#00FFFF", "Cyan"),
    ("#0000FF", "Blue"),
    ("#8B00FF", "Violet"),
    ("#FF1493", "Pink"),
    ("#FFFFFF", "White"),
    ("#FF6347", "Warm"),
]

WHEEL_RADIUS = 110   # px, colour-wheel canvas


# ═════════════════════════════════════════════════════════════════════════════
# Async bridge — run a single asyncio event-loop in a background thread so
# the tkinter main-loop never blocks.
# ═════════════════════════════════════════════════════════════════════════════
class AsyncBridge:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro) -> asyncio.Future:
        """Schedule *coro* on the background loop and return its Future."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)


# ═════════════════════════════════════════════════════════════════════════════
# Colour-wheel canvas widget
# ═════════════════════════════════════════════════════════════════════════════
class ColorWheelCanvas(tk.Canvas):
    """Interactive HSV colour wheel drawn with PIL-free pure-tkinter arcs."""

    def __init__(self, master, size: int, on_pick, **kw) -> None:
        super().__init__(master, width=size, height=size,
                         bg=CARD, highlightthickness=0, **kw)
        self._size = size
        self._cx = self._cy = size // 2
        self._r = size // 2 - 6
        self._on_pick = on_pick
        self._cursor_id: Optional[int] = None
        self._draw_wheel()
        self.bind("<Button-1>", self._clicked)
        self.bind("<B1-Motion>", self._clicked)

    def _draw_wheel(self) -> None:
        """Draw 360 coloured arcs to simulate an HSV wheel."""
        cx, cy, r = self._cx, self._cy, self._r
        step = 2  # degrees per arc — balance quality vs speed
        for hue_deg in range(0, 360, step):
            h = hue_deg / 360.0
            # outer ring (s=1) → inner ring blends toward white (s=0) done by
            # layering thin arcs from outer to inner
            for s_pct in range(100, 0, -5):
                s = s_pct / 100.0
                ri = r * s_pct / 100
                ro = r * (s_pct + 5) / 100
                r_v, g_v, b_v = colorsys.hsv_to_rgb(h, s, 1.0)
                color = f"#{int(r_v*255):02x}{int(g_v*255):02x}{int(b_v*255):02x}"
                # arc bounding box
                x0, y0 = cx - ro, cy - ro
                x1, y1 = cx + ro, cy + ro
                self.create_arc(x0, y0, x1, y1,
                                start=hue_deg, extent=step + 1,
                                fill=color, outline="", style=tk.PIESLICE)
        # White centre dot
        self.create_oval(cx - 4, cy - 4, cx + 4, cy + 4,
                         fill="white", outline="")

    def _clicked(self, event: tk.Event) -> None:
        dx = event.x - self._cx
        dy = event.y - self._cy
        dist = math.hypot(dx, dy)
        if dist > self._r:
            return
        hue_deg = math.degrees(math.atan2(-dy, dx)) % 360
        sat = dist / self._r
        h, s, v = hue_deg / 360.0, sat, 1.0
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        rgb = (int(r * 255), int(g * 255), int(b * 255))
        # Draw cursor ring
        if self._cursor_id:
            self.delete(self._cursor_id)
        self._cursor_id = self.create_oval(
            event.x - 7, event.y - 7, event.x + 7, event.y + 7,
            outline="white", width=2
        )
        self._on_pick(rgb)

    def set_cursor(self, h: float, s: float) -> None:
        """Move the cursor to the given HSV (h 0-1, s 0-1)."""
        angle = math.radians(h * 360)
        dist  = s * self._r
        x = self._cx + dist * math.cos(angle)
        y = self._cy - dist * math.sin(angle)
        if self._cursor_id:
            self.delete(self._cursor_id)
        self._cursor_id = self.create_oval(
            x - 7, y - 7, x + 7, y + 7,
            outline="white", width=2
        )


# ═════════════════════════════════════════════════════════════════════════════
# Main Application Window
# ═════════════════════════════════════════════════════════════════════════════
class LotusLampApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        self.title("🌸 LotusLamp X — RGB Controller")
        self.geometry("860x760")
        self.minsize(820, 720)
        self.configure(fg_color=SURFACE)

        self._bridge   = AsyncBridge()
        self._ctrl     = LotusLampController()
        self._devices: list = []
        self._power_on = True
        self._current_rgb = (255, 255, 255)

        self._build_ui()
        self._set_connected(False)

    # ------------------------------------------------------------------ #
    # UI construction                                                       #
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._build_status_bar()

    # ── Header ────────────────────────────────────────────────────────────
    def _build_header(self) -> None:
        hdr = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=68)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(hdr, text="🌸  LotusLamp X",
                     font=ctk.CTkFont(size=22, weight="bold"),
                     text_color="white").grid(row=0, column=0, padx=20, pady=18)

        ctk.CTkLabel(hdr, text="Windows Bluetooth Controller",
                     font=ctk.CTkFont(size=13),
                     text_color="#888888").grid(row=0, column=1, sticky="w", padx=0)

        # Connection indicator dot
        self._conn_dot = ctk.CTkLabel(hdr, text="●", font=ctk.CTkFont(size=18),
                                      text_color="#555555")
        self._conn_dot.grid(row=0, column=2, padx=(0, 6))
        self._conn_label = ctk.CTkLabel(hdr, text="Disconnected",
                                        font=ctk.CTkFont(size=12),
                                        text_color="#888888")
        self._conn_label.grid(row=0, column=3, padx=(0, 20))

    # ── Body ──────────────────────────────────────────────────────────────
    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color=SURFACE)
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(0, weight=0, minsize=270)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    # ── Left panel: device list + power ───────────────────────────────────
    def _build_left_panel(self, parent) -> None:
        lp = ctk.CTkFrame(parent, fg_color=CARD, width=270, corner_radius=12)
        lp.grid(row=0, column=0, sticky="ns", padx=(12, 6), pady=12)
        lp.grid_propagate(False)
        lp.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(lp, text="DEVICE", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#888888").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))

        # Scan button
        self._scan_btn = ctk.CTkButton(
            lp, text="🔍  Scan for Devices", height=36,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._do_scan)
        self._scan_btn.grid(row=1, column=0, padx=12, pady=(0, 6), sticky="ew")

        # Device listbox (scrollable)
        self._device_list = ctk.CTkScrollableFrame(
            lp, height=140, fg_color="#1A1A2E", corner_radius=8)
        self._device_list.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="ew")
        self._device_btns: list[ctk.CTkButton] = []

        self._scanning_lbl = ctk.CTkLabel(self._device_list, text="Press Scan to find devices",
                                          text_color="#555", font=ctk.CTkFont(size=12))
        self._scanning_lbl.pack(pady=20)

        # Connect / Disconnect
        self._connect_btn = ctk.CTkButton(
            lp, text="Connect", height=36,
            fg_color=SUCCESS, hover_color="#388E3C",
            command=self._do_connect, state="disabled")
        self._connect_btn.grid(row=3, column=0, padx=12, pady=(0, 4), sticky="ew")

        self._disconnect_btn = ctk.CTkButton(
            lp, text="Disconnect", height=36,
            fg_color=DANGER, hover_color="#C62828",
            command=self._do_disconnect, state="disabled")
        self._disconnect_btn.grid(row=4, column=0, padx=12, pady=(0, 10), sticky="ew")

        # Divider
        ctk.CTkFrame(lp, height=1, fg_color=BORDER).grid(
            row=5, column=0, sticky="ew", padx=12, pady=4)

        # Power toggle
        ctk.CTkLabel(lp, text="POWER", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#888888").grid(row=6, column=0, sticky="w", padx=14, pady=(10, 4))

        self._power_btn = ctk.CTkButton(
            lp, text="⏻  Turn Off", height=48,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="#2E2E4E", hover_color="#3E3E6E",
            command=self._toggle_power, state="disabled")
        self._power_btn.grid(row=7, column=0, padx=12, pady=(0, 10), sticky="ew")

        # Divider
        ctk.CTkFrame(lp, height=1, fg_color=BORDER).grid(
            row=8, column=0, sticky="ew", padx=12, pady=4)

        # Brightness
        ctk.CTkLabel(lp, text="BRIGHTNESS", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#888888").grid(row=9, column=0, sticky="w", padx=14, pady=(10, 2))

        self._brightness_lbl = ctk.CTkLabel(lp, text="100 %",
                                            font=ctk.CTkFont(size=13),
                                            text_color="white")
        self._brightness_lbl.grid(row=9, column=0, sticky="e", padx=14)

        self._brightness_slider = ctk.CTkSlider(
            lp, from_=0, to=100, number_of_steps=100,
            command=self._on_brightness_change,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT)
        self._brightness_slider.set(100)
        self._brightness_slider.grid(row=10, column=0, padx=12, pady=(0, 14), sticky="ew")
        self._brightness_slider.configure(state="disabled")

    # ── Right panel: colour + effects ─────────────────────────────────────
    def _build_right_panel(self, parent) -> None:
        rp = ctk.CTkScrollableFrame(parent, fg_color=SURFACE)
        rp.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        rp.grid_columnconfigure(0, weight=1)

        # ── Colour section ─────────────────────────────────────────────────
        col_card = self._card(rp, "🎨  Colour")
        col_card.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        col_card.grid_columnconfigure((0, 1), weight=1)

        # Colour wheel
        wheel_frame = ctk.CTkFrame(col_card, fg_color=CARD, corner_radius=8)
        wheel_frame.grid(row=1, column=0, padx=10, pady=10, sticky="n")
        self._wheel = ColorWheelCanvas(
            wheel_frame, size=WHEEL_RADIUS * 2 + 10,
            on_pick=self._on_wheel_pick)
        self._wheel.pack(padx=5, pady=5)

        # Right side: hex entry + preview + quick palette
        ctrl_frame = ctk.CTkFrame(col_card, fg_color="transparent")
        ctrl_frame.grid(row=1, column=1, padx=10, pady=10, sticky="new")
        ctrl_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(ctrl_frame, text="Hex Colour",
                     font=ctk.CTkFont(size=12), text_color="#888").grid(
            row=0, column=0, sticky="w")

        hex_row = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        hex_row.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        hex_row.grid_columnconfigure(0, weight=1)

        self._hex_entry = ctk.CTkEntry(hex_row, placeholder_text="#FFFFFF",
                                       font=ctk.CTkFont(size=14, family="Consolas"),
                                       height=36)
        self._hex_entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self._hex_entry.bind("<Return>", self._on_hex_enter)

        ctk.CTkButton(hex_row, text="Set", width=50, height=36,
                      fg_color=ACCENT, hover_color=ACCENT_HOVER,
                      command=self._on_hex_enter).grid(row=0, column=1)

        # Colour preview swatch
        self._preview_canvas = tk.Canvas(ctrl_frame, width=160, height=50,
                                         bg="#FFFFFF", highlightthickness=1,
                                         highlightbackground=BORDER)
        self._preview_canvas.grid(row=2, column=0, sticky="ew", pady=(0, 10))

        # Open system colour picker
        ctk.CTkButton(ctrl_frame, text="🖌  Open Colour Picker", height=32,
                      fg_color="#2E2E4E", hover_color="#3E3E6E",
                      command=self._open_color_picker).grid(
            row=3, column=0, sticky="ew", pady=(0, 12))

        # Quick palette
        ctk.CTkLabel(ctrl_frame, text="Quick Colours",
                     font=ctk.CTkFont(size=12), text_color="#888").grid(
            row=4, column=0, sticky="w")
        palette = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        palette.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        for i, (hex_c, name) in enumerate(QUICK_COLORS):
            btn = tk.Button(
                palette, bg=hex_c, width=3, height=1,
                relief="flat", cursor="hand2",
                command=lambda h=hex_c: self._on_quick_color(h))
            btn.grid(row=i // 5, column=i % 5, padx=2, pady=2)

        # ── RGB sliders ────────────────────────────────────────────────────
        rgb_card = self._card(rp, "🔵  RGB Fine-Tune")
        rgb_card.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        rgb_card.grid_columnconfigure(1, weight=1)

        self._r_slider = self._rgb_row(rgb_card, "R", "#FF4444", 1,
                                       self._on_rgb_slider)
        self._g_slider = self._rgb_row(rgb_card, "G", "#44FF44", 2,
                                       self._on_rgb_slider)
        self._b_slider = self._rgb_row(rgb_card, "B", "#4488FF", 3,
                                       self._on_rgb_slider)
        self._r_slider.set(255); self._g_slider.set(255); self._b_slider.set(255)

        # ── Effects section ────────────────────────────────────────────────
        fx_card = self._card(rp, "✨  Built-in Effects")
        fx_card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        fx_card.grid_columnconfigure(0, weight=1)

        self._effect_var = ctk.StringVar(value=list(EFFECTS.keys())[0])
        effect_menu = ctk.CTkOptionMenu(
            fx_card, values=list(EFFECTS.keys()),
            variable=self._effect_var,
            fg_color="#2E2E4E", button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            command=self._on_effect_select)
        effect_menu.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        # Speed
        speed_row = ctk.CTkFrame(fx_card, fg_color="transparent")
        speed_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))
        speed_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(speed_row, text="Speed",
                     font=ctk.CTkFont(size=12), text_color="#888").grid(
            row=0, column=0, padx=(0, 10))
        self._speed_lbl = ctk.CTkLabel(speed_row, text="50 %",
                                       font=ctk.CTkFont(size=12), text_color="white")
        self._speed_lbl.grid(row=0, column=2, padx=(10, 0))

        self._speed_slider = ctk.CTkSlider(
            speed_row, from_=0, to=100, number_of_steps=100,
            command=self._on_speed_change,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color="#9C27B0")
        self._speed_slider.set(50)
        self._speed_slider.grid(row=0, column=1, sticky="ew")
        self._speed_slider.configure(state="disabled")

        # Keep refs to disable/enable on connect
        self._effect_menu = effect_menu
        self._effect_menu.configure(state="disabled")

    # ── Status bar ────────────────────────────────────────────────────────
    def _build_status_bar(self) -> None:
        sb = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=28)
        sb.grid(row=2, column=0, sticky="ew")
        sb.grid_propagate(False)
        self._status_lbl = ctk.CTkLabel(
            sb, text="Ready — scan for a device to get started.",
            font=ctk.CTkFont(size=11), text_color="#888888")
        self._status_lbl.pack(side="left", padx=12)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _card(self, parent, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color="white").grid(
            row=0, column=0, sticky="w", padx=14, pady=(12, 6))
        return frame

    def _rgb_row(self, parent, label, color, row, cmd) -> ctk.CTkSlider:
        ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=color, width=20).grid(
            row=row, column=0, padx=(14, 4), pady=4, sticky="w")
        s = ctk.CTkSlider(parent, from_=0, to=255, number_of_steps=255,
                          command=cmd,
                          button_color=color, button_hover_color=color,
                          progress_color=color)
        s.grid(row=row, column=1, padx=(0, 12), pady=4, sticky="ew")
        s.configure(state="disabled")
        return s

    # ------------------------------------------------------------------ #
    # Scan                                                                 #
    # ------------------------------------------------------------------ #
    def _do_scan(self) -> None:
        self._scan_btn.configure(text="⏳  Scanning…", state="disabled")
        self._status("Scanning for BLE devices (8 s)…")
        self._clear_device_list()
        self._scanning_lbl.configure(text="Scanning…")

        def _done(fut) -> None:
            try:
                self._devices = fut.result()
            except Exception as exc:
                self.after(0, self._status, f"Scan error: {exc}")
                self._devices = []
            self.after(0, self._populate_device_list)

        self._bridge.run(self._ctrl.scan(timeout=8.0)).add_done_callback(_done)

    def _clear_device_list(self) -> None:
        for w in self._device_btns:
            w.destroy()
        self._device_btns.clear()
        if self._scanning_lbl.winfo_exists():
            self._scanning_lbl.pack_forget()

    def _populate_device_list(self) -> None:
        self._scan_btn.configure(text="🔍  Scan for Devices", state="normal")
        if not self._devices:
            self._scanning_lbl.configure(text="No devices found")
            self._scanning_lbl.pack(pady=20)
            self._status("No BLE devices found — ensure the strip is powered on.")
            return

        self._selected_device_index: Optional[int] = None
        for i, dev in enumerate(self._devices):
            name = dev.name or "Unknown"
            addr = dev.address
            btn = ctk.CTkButton(
                self._device_list,
                text=f"{name}\n{addr}",
                height=44, anchor="w",
                font=ctk.CTkFont(size=11),
                fg_color="#1E1E3E", hover_color="#2E2E5E",
                command=lambda idx=i: self._select_device(idx))
            btn.pack(fill="x", pady=2, padx=4)
            self._device_btns.append(btn)

        self._status(f"Found {len(self._devices)} device(s). Select one to connect.")

    def _select_device(self, idx: int) -> None:
        self._selected_device_index = idx
        for i, btn in enumerate(self._device_btns):
            btn.configure(fg_color=ACCENT if i == idx else "#1E1E3E")
        self._connect_btn.configure(state="normal")
        dev = self._devices[idx]
        self._status(f"Selected: {dev.name or 'Unknown'}  ({dev.address})")

    # ------------------------------------------------------------------ #
    # Connect / Disconnect                                                  #
    # ------------------------------------------------------------------ #
    def _do_connect(self) -> None:
        idx = getattr(self, "_selected_device_index", None)
        if idx is None:
            return
        dev = self._devices[idx]
        self._connect_btn.configure(state="disabled", text="Connecting…")
        self._status(f"Connecting to {dev.name or dev.address}…")

        def _done(fut) -> None:
            try:
                fut.result()
                self.after(0, self._on_connected, dev)
            except Exception as exc:
                self.after(0, self._status, f"Connection failed: {exc}")
                self.after(0, self._connect_btn.configure,
                           {"state": "normal", "text": "Connect"})

        self._bridge.run(
            self._ctrl.connect(dev, disconnected_cb=self._on_disconnected_cb)
        ).add_done_callback(_done)

    def _on_connected(self, dev) -> None:
        self._connect_btn.configure(text="Connect", state="disabled")
        self._set_connected(True)
        self._status(f"Connected ✓  {dev.name or dev.address}  ({dev.address})")
        self._conn_label.configure(text=dev.name or dev.address)

    def _on_disconnected_cb(self) -> None:
        self.after(0, self._set_connected, False)
        self.after(0, self._status, "Device disconnected.")

    def _do_disconnect(self) -> None:
        self._bridge.run(self._ctrl.disconnect())
        self._set_connected(False)
        self._status("Disconnected.")

    def _set_connected(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        self._conn_dot.configure(text_color=SUCCESS if connected else "#555555")
        self._conn_label.configure(
            text="Connected" if connected else "Disconnected",
            text_color=SUCCESS if connected else "#888888")
        self._disconnect_btn.configure(state=state)
        self._power_btn.configure(state=state)
        self._brightness_slider.configure(state=state)
        self._r_slider.configure(state=state)
        self._g_slider.configure(state=state)
        self._b_slider.configure(state=state)
        self._speed_slider.configure(state=state)
        self._effect_menu.configure(state=state)
        if not connected:
            self._connect_btn.configure(state="normal" if self._devices else "disabled")

    # ------------------------------------------------------------------ #
    # Power                                                                #
    # ------------------------------------------------------------------ #
    def _toggle_power(self) -> None:
        self._power_on = not self._power_on
        if self._power_on:
            self._power_btn.configure(text="⏻  Turn Off")
            self._bridge.run(self._ctrl.power_on())
            self._status("Power ON")
        else:
            self._power_btn.configure(text="⏻  Turn On")
            self._bridge.run(self._ctrl.power_off())
            self._status("Power OFF")

    # ------------------------------------------------------------------ #
    # Colour                                                               #
    # ------------------------------------------------------------------ #
    def _send_color(self, r: int, g: int, b: int) -> None:
        self._current_rgb = (r, g, b)
        hex_str = f"#{r:02X}{g:02X}{b:02X}"
        # Update preview
        self._preview_canvas.configure(bg=hex_str)
        # Update hex entry
        self._hex_entry.delete(0, "end")
        self._hex_entry.insert(0, hex_str)
        # Update RGB sliders (suppress callback loop via flag)
        self._updating_sliders = True
        self._r_slider.set(r); self._g_slider.set(g); self._b_slider.set(b)
        self._updating_sliders = False
        # Update wheel cursor
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self._wheel.set_cursor(h, s)
        # Send BLE command
        if self._ctrl.is_connected:
            self._bridge.run(self._ctrl.set_color(r, g, b))

    def _on_wheel_pick(self, rgb: tuple[int, int, int]) -> None:
        self._send_color(*rgb)

    def _on_hex_enter(self, event=None) -> None:
        raw = self._hex_entry.get().strip().lstrip("#")
        if len(raw) == 6:
            try:
                r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
                self._send_color(r, g, b)
            except ValueError:
                self._status("Invalid hex colour code")

    def _open_color_picker(self) -> None:
        r, g, b = self._current_rgb
        init = f"#{r:02x}{g:02x}{b:02x}"
        result = colorchooser.askcolor(color=init, title="Choose Colour")
        if result and result[0]:
            r, g, b = (int(x) for x in result[0])
            self._send_color(r, g, b)

    def _on_quick_color(self, hex_c: str) -> None:
        raw = hex_c.lstrip("#")
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        self._send_color(r, g, b)

    def _on_rgb_slider(self, _=None) -> None:
        if getattr(self, "_updating_sliders", False):
            return
        r = int(self._r_slider.get())
        g = int(self._g_slider.get())
        b = int(self._b_slider.get())
        self._send_color(r, g, b)

    # ------------------------------------------------------------------ #
    # Brightness                                                           #
    # ------------------------------------------------------------------ #
    def _on_brightness_change(self, value) -> None:
        pct = int(value)
        self._brightness_lbl.configure(text=f"{pct} %")
        if self._ctrl.is_connected:
            self._bridge.run(self._ctrl.set_brightness(pct))

    # ------------------------------------------------------------------ #
    # Effects                                                              #
    # ------------------------------------------------------------------ #
    def _on_effect_select(self, name: str) -> None:
        if self._ctrl.is_connected:
            effect_id = EFFECTS[name]
            self._bridge.run(self._ctrl.set_effect(effect_id))
            self._status(f"Effect: {name}")

    def _on_speed_change(self, value) -> None:
        pct = int(value)
        self._speed_lbl.configure(text=f"{pct} %")
        if self._ctrl.is_connected:
            self._bridge.run(self._ctrl.set_effect_speed(pct))

    # ------------------------------------------------------------------ #
    # Status bar                                                           #
    # ------------------------------------------------------------------ #
    def _status(self, msg: str) -> None:
        self._status_lbl.configure(text=msg)


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = LotusLampApp()
    app.mainloop()
