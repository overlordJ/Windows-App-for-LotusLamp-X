"""
ble_controller.py
-----------------
Low-level BLE communication layer for ELK-BLEDOM / LotusLamp X compatible
RGB LED strip controllers.

Protocol reference (reverse-engineered, 9-byte frames):
  Header  : 0x7E
  Footer  : 0xEF
  Service : 0000fff0-0000-1000-8000-00805f9b34fb
  Write   : 0000fff3-0000-1000-8000-00805f9b34fb  (Write Without Response)
  Notify  : 0000fff4-0000-1000-8000-00805f9b34fb

Fallback UUIDs (some firmware variants):
  Service : 0000ffe0-0000-1000-8000-00805f9b34fb
  Write   : 0000ffe1-0000-1000-8000-00805f9b34fb
"""

from __future__ import annotations
import asyncio
import logging
from typing import Optional, Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

logger = logging.getLogger(__name__)

# --- UUIDs (try fff0/fff3 first, then ffe0/ffe1 as fallback) ---
SERVICE_UUIDS = [
    "0000fff0-0000-1000-8000-00805f9b34fb",
    "0000ffe0-0000-1000-8000-00805f9b34fb",
]
WRITE_UUIDS = [
    "0000fff3-0000-1000-8000-00805f9b34fb",
    "0000ffe1-0000-1000-8000-00805f9b34fb",
]

# --- Named built-in effects ---
EFFECTS: dict[str, int] = {
    "RGB Jump":          0x87,
    "7-Color Jump":      0x88,
    "Red Fade":          0x89,
    "Green Fade":        0x8A,
    "Blue Fade":         0x8B,
    "Yellow Fade":       0x8C,
    "Cyan Fade":         0x8D,
    "Purple Fade":       0x8E,
    "White Fade":        0x8F,
    "Red/Green Fade":    0x90,
    "Red/Blue Fade":     0x91,
    "Green/Blue Fade":   0x92,
    "7-Color Fade":      0x93,
    "Red Blink":         0x94,
    "7-Color Blink":     0x95,
    "Red/Green Blink":   0x96,
    "Red/Blue Blink":    0x97,
    "Green/Blue Blink":  0x98,
    "Yellow/White Blink":0x99,
    "Gradient Strobe":   0x9A,
    "Rainbow Breath":    0x9B,
    "Color Wipe":        0x9C,
}


def _cmd(*bytes_: int) -> bytearray:
    """Build a 9-byte command frame padded with 0x00."""
    frame = bytearray(9)
    for i, b in enumerate(bytes_):
        frame[i] = b
    frame[-1] = 0xEF
    return frame


class LotusLampController:
    """Async BLE controller for a single LotusLamp X / ELK-BLEDOM device."""

    def __init__(self) -> None:
        self._client: Optional[BleakClient] = None
        self._write_char: Optional[str] = None
        self._device: Optional[BLEDevice] = None
        self._connected = False

    # ------------------------------------------------------------------ #
    # Scan                                                                 #
    # ------------------------------------------------------------------ #
    @staticmethod
    async def scan(timeout: float = 8.0) -> list[BLEDevice]:
        """Return all visible BLE devices (filtered to likely LED controllers)."""
        devices = await BleakScanner.discover(timeout=timeout, return_adv=False)
        # Prefer known prefixes but return all so user can pick
        known = []
        others = []
        prefixes = ("ELK", "LEDBLE", "BLE", "LED", "LOTUS", "LAMP", "STRIP", "RGB")
        for d in devices:
            name = (d.name or "").upper()
            if any(name.startswith(p) for p in prefixes):
                known.append(d)
            else:
                others.append(d)
        return known + others

    # ------------------------------------------------------------------ #
    # Connect / Disconnect                                                 #
    # ------------------------------------------------------------------ #
    async def connect(self, device: BLEDevice,
                      disconnected_cb: Optional[Callable] = None) -> None:
        """Connect to *device* and discover the write characteristic."""
        def _on_disconnect(client: BleakClient) -> None:
            self._connected = False
            logger.info("Disconnected from %s", client.address)
            if disconnected_cb:
                disconnected_cb()

        self._client = BleakClient(device, disconnected_callback=_on_disconnect)
        await self._client.connect()
        self._connected = True
        self._device = device
        self._write_char = await self._find_write_char()
        logger.info("Connected to %s, write char: %s",
                    device.address, self._write_char)

    async def _find_write_char(self) -> str:
        """Walk the GATT table and return the best write characteristic UUID."""
        if not self._client:
            raise RuntimeError("Not connected")
        svcs = self._client.services
        # Try known write UUIDs first
        for wu in WRITE_UUIDS:
            char = svcs.get_characteristic(wu)
            if char is not None:
                return wu
        # Fall back: first writable characteristic in known service UUIDs
        for svc_uuid in SERVICE_UUIDS:
            svc = svcs.get_service(svc_uuid)
            if svc:
                for c in svc.characteristics:
                    if "write" in c.properties or "write-without-response" in c.properties:
                        return c.uuid
        # Last resort: first writable char anywhere
        for svc in svcs:
            for c in svc.characteristics:
                if "write" in c.properties or "write-without-response" in c.properties:
                    logger.warning("Using fallback write char: %s", c.uuid)
                    return c.uuid
        raise RuntimeError("No writable characteristic found — unsupported device?")

    async def disconnect(self) -> None:
        if self._client and self._connected:
            await self._client.disconnect()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    # ------------------------------------------------------------------ #
    # Internal send                                                        #
    # ------------------------------------------------------------------ #
    async def _send(self, data: bytearray) -> None:
        if not self.is_connected or not self._write_char:
            raise RuntimeError("Not connected to a device")
        try:
            await self._client.write_gatt_char(
                self._write_char, data, response=False
            )
        except Exception as exc:
            # Some controllers require response=True
            logger.warning("write_without_response failed (%s), retrying with response", exc)
            await self._client.write_gatt_char(
                self._write_char, data, response=True
            )

    # ------------------------------------------------------------------ #
    # Power                                                                #
    # ------------------------------------------------------------------ #
    async def power_on(self) -> None:
        await self._send(_cmd(0x7E, 0x04, 0x04, 0xF0, 0x00, 0x01, 0xFF, 0x00))

    async def power_off(self) -> None:
        await self._send(_cmd(0x7E, 0x04, 0x04, 0x00, 0x00, 0x00, 0xFF, 0x00))

    # ------------------------------------------------------------------ #
    # Color                                                                #
    # ------------------------------------------------------------------ #
    async def set_color(self, r: int, g: int, b: int) -> None:
        """Set a static RGB color (0–255 each channel)."""
        await self._send(_cmd(0x7E, 0x07, 0x05, 0x03, r & 0xFF, g & 0xFF, b & 0xFF, 0x10))

    # ------------------------------------------------------------------ #
    # Brightness                                                           #
    # ------------------------------------------------------------------ #
    async def set_brightness(self, pct: int) -> None:
        """Set brightness 0–100 %."""
        val = max(0, min(100, pct))
        await self._send(_cmd(0x7E, 0x00, 0x01, val, 0x00, 0x00, 0x00, 0x00))

    # ------------------------------------------------------------------ #
    # Effects / Animations                                                 #
    # ------------------------------------------------------------------ #
    async def set_effect(self, effect_id: int) -> None:
        """Trigger a built-in hardware animation by its ID byte."""
        await self._send(_cmd(0x7E, 0x00, 0x03, effect_id, 0x03, 0x00, 0x00, 0x00))

    async def set_effect_speed(self, pct: int) -> None:
        """Set effect animation speed 0–100 %."""
        val = max(0, min(100, pct))
        await self._send(_cmd(0x7E, 0x00, 0x02, val, 0x00, 0x00, 0x00, 0x00))
