"""Sounddevice-based audio I/O layer for the EQ app."""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover - makes diagnostics clearer
    raise RuntimeError("sounddevice is required for real-time audio") from exc

from equaliser.dsp import EQBand, EQEngine, MeterSnapshot


@dataclass
class DeviceMetadata:
    index: int
    name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float


class AudioBackend:
    """Owns the sounddevice stream and bridges GUI events to the DSP engine."""

    def __init__(self) -> None:
        self.sample_rate: float = 48000.0
        self.block_size: int = 256
        self.channels: int = 2
        self.input_device: Optional[int] = None
        self.output_device: Optional[int] = None
        self._stream: Optional[sd.Stream] = None
        self._engine: Optional[EQEngine] = None
        self._lock = threading.Lock()
        self._status = queue.Queue(maxsize=32)
        self._bands: List[EQBand] = []
        self._bypass: bool = False
        self._output_gain_db: float = -3.0

    # Device helpers -----------------------------------------------------
    @staticmethod
    def list_devices() -> List[DeviceMetadata]:
        devices = []
        for idx, raw in enumerate(sd.query_devices()):
            devices.append(
                DeviceMetadata(
                    index=idx,
                    name=raw["name"],
                    max_input_channels=int(raw["max_input_channels"]),
                    max_output_channels=int(raw["max_output_channels"]),
                    default_samplerate=float(raw["default_samplerate"]),
                )
            )
        return devices

    # Configuration ------------------------------------------------------
    def configure(
        self,
        sample_rate: float,
        block_size: int,
        input_device: int,
        output_device: int,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.input_device = input_device
        self.output_device = output_device
        self._create_engine()

    def _create_engine(self) -> None:
        self._engine = EQEngine(
            sample_rate=self.sample_rate,
            channels=self.channels,
            output_gain_db=self._output_gain_db,
        )
        self._engine.bypass = self._bypass
        if self._bands:
            self._engine.set_bands(self._bands)

    def set_bands(self, bands: List[EQBand]) -> None:
        copies = [EQBand(b.frequency, b.gain_db, b.q, b.enabled) for b in bands]
        with self._lock:
            self._bands = copies
            if self._engine:
                self._engine.set_bands(self._bands)

    def set_bypass(self, bypass: bool) -> None:
        self._bypass = bypass
        with self._lock:
            if self._engine:
                self._engine.bypass = bypass

    def set_output_gain(self, gain_db: float) -> None:
        self._output_gain_db = gain_db
        with self._lock:
            if self._engine:
                self._engine.set_output_gain(gain_db)

    def get_meter(self) -> MeterSnapshot:
        with self._lock:
            if self._engine:
                return self._engine.meter
        return MeterSnapshot()

    # Stream lifecycle ---------------------------------------------------
    def start(self) -> None:
        if self._stream is not None:
            return
        if None in (self.input_device, self.output_device):
            raise RuntimeError("Input/output devices must be configured before starting audio")
        if self._engine is None:
            self._create_engine()
        self._stream = sd.Stream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            device=(self.input_device, self.output_device),
            dtype="float32",
            channels=self.channels,
            callback=self._callback,
            finished_callback=self._on_stream_finished,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream is None:
            return
        self._stream.stop()
        self._stream.close()
        self._stream = None

    def close(self) -> None:
        self.stop()

    def _callback(self, indata, outdata, frames, time, status):  # type: ignore[override]
        if status:
            self._put_status(f"Audio callback status: {status}")
        block = np.array(indata, copy=True)
        with self._lock:
            engine = self._engine
        if engine is None:
            outdata.fill(0)
            return
        try:
            processed = engine.process_block(block)
        except Exception as exc:  # pragma: no cover - safety net for GUI build
            outdata.fill(0)
            self._put_status(f"Processing error: {exc}")
            return
        outdata[:] = processed

    def _on_stream_finished(self) -> None:  # pragma: no cover - callback hook
        self._put_status("Audio stream finished")

    def _put_status(self, message: str) -> None:
        try:
            self._status.put_nowait(message)
        except queue.Full:
            try:
                _ = self._status.get_nowait()
            except queue.Empty:
                pass
            try:
                self._status.put_nowait(message)
            except queue.Full:
                pass

    def poll_status(self) -> List[str]:
        messages = []
        while True:
            try:
                messages.append(self._status.get_nowait())
            except queue.Empty:
                break
        return messages
