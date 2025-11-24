"""PyQt6 main window for the system-wide EQ."""
from __future__ import annotations

from typing import List, Optional

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from equaliser.audio.stream import AudioBackend, DeviceMetadata
from equaliser.dsp import EQBand
from .plotting import frequency_response


INSTRUCTIONS = """System Audio Routing
=====================
1. Install the BlackHole 2ch virtual driver (brew install blackhole-2ch).
2. Open Audio MIDI Setup ➝ click + ➝ Create Multi-Output Device.
3. Check BlackHole and your real output (e.g., MacBook Speakers). Set the real output as the master clock.
4. In macOS System Settings ➝ Sound ➝ Output, choose the Multi-Output device so the OS routes audio into BlackHole.
5. In Equaliser, select BlackHole as the input device and your real output as the output device.
6. Optionally, create an Aggregate Device if you want DAW recording: include BlackHole + Built-in Mic and select it as needed.
7. Keep sample rates matched (typically 48 kHz) across every device to avoid pitch shifts.
"""


class EQCurveCanvas(FigureCanvasQTAgg):
    def __init__(self) -> None:
        fig = Figure(figsize=(5, 3), tight_layout=True)
        super().__init__(fig)
        self.ax = fig.add_subplot(111)
        self.ax.set_xscale("log")
        self.ax.set_xlim(20, 20000)
        self.ax.set_ylim(-18, 18)
        self.ax.set_xlabel("Frequency (Hz)")
        self.ax.set_ylabel("Gain (dB)")
        self.line, = self.ax.plot([], [], color="orange")
        self.ax.grid(True, which="both", ls=":", lw=0.5)

    def update_curve(self, bands: List[EQBand], sample_rate: float) -> None:
        if not bands:
            self.line.set_data([], [])
            self.draw_idle()
            return
        freqs, magnitude = frequency_response(bands, sample_rate)
        self.line.set_data(freqs, np.clip(magnitude, -24, 24))
        self.draw_idle()


class EqualiserWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("macOS System EQ (BlackHole)")
        self.resize(1100, 720)
        self.audio = AudioBackend()
        self.bands: List[EQBand] = []
        self._updating_table = False

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        layout.addWidget(self._build_device_group())
        layout.addWidget(self._build_band_group())

        lower_split = QtWidgets.QHBoxLayout()
        self.curve_canvas = EQCurveCanvas()
        lower_split.addWidget(self.curve_canvas, 2)
        lower_split.addWidget(self._build_meter_panel(), 1)
        layout.addLayout(lower_split)

        layout.addWidget(self._build_instructions_box())

        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)

        self.device_refresh()

        self.meter_timer = QtCore.QTimer(self)
        self.meter_timer.timeout.connect(self._poll_meters)
        self.meter_timer.start(100)

        self.status_timer = QtCore.QTimer(self)
        self.status_timer.timeout.connect(self._poll_backend_status)
        self.status_timer.start(500)

    # UI builders -------------------------------------------------------
    def _build_device_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Audio Devices")
        layout = QtWidgets.QGridLayout(group)

        self.input_combo = QtWidgets.QComboBox()
        self.output_combo = QtWidgets.QComboBox()
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.device_refresh)

        layout.addWidget(QtWidgets.QLabel("Input (BlackHole)"), 0, 0)
        layout.addWidget(self.input_combo, 0, 1)
        layout.addWidget(QtWidgets.QLabel("Output (Speakers)"), 1, 0)
        layout.addWidget(self.output_combo, 1, 1)
        layout.addWidget(self.refresh_button, 0, 2, 2, 1)

        self.sample_rate_spin = QtWidgets.QSpinBox()
        self.sample_rate_spin.setRange(44100, 192000)
        self.sample_rate_spin.setSingleStep(100)
        self.sample_rate_spin.setValue(int(self.audio.sample_rate))
        layout.addWidget(QtWidgets.QLabel("Sample Rate (Hz)"), 2, 0)
        layout.addWidget(self.sample_rate_spin, 2, 1)

        self.block_size_spin = QtWidgets.QSpinBox()
        self.block_size_spin.setRange(64, 2048)
        self.block_size_spin.setSingleStep(64)
        self.block_size_spin.setValue(self.audio.block_size)
        layout.addWidget(QtWidgets.QLabel("Buffer Size (frames)"), 3, 0)
        layout.addWidget(self.block_size_spin, 3, 1)

        self.start_button = QtWidgets.QPushButton("Start Audio")
        self.start_button.clicked.connect(self.start_audio)
        self.stop_button = QtWidgets.QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_audio)
        layout.addWidget(self.start_button, 4, 0)
        layout.addWidget(self.stop_button, 4, 1)

        return group

    def _build_band_group(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Parametric EQ Bands")
        layout = QtWidgets.QVBoxLayout(group)

        self.band_table = QtWidgets.QTableWidget(0, 3)
        self.band_table.setHorizontalHeaderLabels(["Frequency (Hz)", "Gain (dB)", "Q"])
        self.band_table.horizontalHeader().setStretchLastSection(True)
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.itemChanged.connect(self._on_band_item_changed)
        layout.addWidget(self.band_table)

        self.preamp_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.preamp_slider.setRange(-240, 120)
        self.preamp_slider.setSingleStep(1)
        self.preamp_slider.setPageStep(5)
        self.preamp_slider.valueChanged.connect(self._on_preamp_changed)
        self.preamp_value = QtWidgets.QLabel("0.0 dB")
        preamp_row = QtWidgets.QHBoxLayout()
        preamp_row.addWidget(QtWidgets.QLabel("Global Gain / Preamp"))
        preamp_row.addWidget(self.preamp_slider, 1)
        preamp_row.addWidget(self.preamp_value)
        layout.addLayout(preamp_row)

        button_row = QtWidgets.QHBoxLayout()
        self.add_band_button = QtWidgets.QPushButton("Add Band")
        self.add_band_button.clicked.connect(self.add_band)
        self.remove_band_button = QtWidgets.QPushButton("Remove Selected")
        self.remove_band_button.clicked.connect(self.remove_selected_band)
        self.bypass_button = QtWidgets.QPushButton("EQ Bypass (A/B)")
        self.bypass_button.setCheckable(True)
        self.bypass_button.clicked.connect(self._toggle_bypass)
        button_row.addWidget(self.add_band_button)
        button_row.addWidget(self.remove_band_button)
        button_row.addStretch(1)
        button_row.addWidget(self.bypass_button)
        layout.addLayout(button_row)

        self.preamp_slider.setValue(-30)  # default -3.0 dB headroom

        return group

    def _build_meter_panel(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Meters")
        layout = QtWidgets.QVBoxLayout(group)

        self.input_meter = self._make_meter("Input")
        self.output_meter = self._make_meter("Output")
        layout.addWidget(self.input_meter)
        layout.addWidget(self.output_meter)

        self.latency_label = QtWidgets.QLabel("Buffer ~0 ms")
        layout.addWidget(self.latency_label)

        self.status_log = QtWidgets.QPlainTextEdit()
        self.status_log.setReadOnly(True)
        self.status_log.setMaximumBlockCount(200)
        layout.addWidget(self.status_log)

        return group

    def _build_instructions_box(self) -> QtWidgets.QGroupBox:
        group = QtWidgets.QGroupBox("Routing Instructions & Tips")
        layout = QtWidgets.QVBoxLayout(group)
        text = QtWidgets.QPlainTextEdit()
        text.setPlainText(INSTRUCTIONS + "\nTroubleshooting:\n- If you hear echoes, disable 'Drift Correction' on the non-master devices.\n- When no audio passes through, confirm macOS output points at the Multi-Output device and restart this app.\n- Latency grows with larger buffer sizes; 256 frames @ 48 kHz ≈ 5.3 ms.")
        text.setReadOnly(True)
        layout.addWidget(text)
        return group

    def _make_meter(self, label: str) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QtWidgets.QLabel(label))
        bar = QtWidgets.QProgressBar()
        bar.setRange(-60, 0)
        bar.setFormat("%v dBFS")
        bar.setValue(-60)
        layout.addWidget(bar, 1)
        widget.progress = bar  # type: ignore[attr-defined]
        return widget

    # Device logic ------------------------------------------------------
    def device_refresh(self) -> None:
        try:
            devices = AudioBackend.list_devices()
        except Exception as exc:
            self.status_bar.showMessage(f"Audio device query failed: {exc}", 5000)
            return
        self._populate_device_combo(self.input_combo, devices, require_input=True)
        self._populate_device_combo(self.output_combo, devices, require_output=True)
        if devices:
            sr = int(devices[0].default_samplerate)
            self.sample_rate_spin.setValue(sr)

    def _populate_device_combo(
        self,
        combo: QtWidgets.QComboBox,
        devices: List[DeviceMetadata],
        require_input: bool = False,
        require_output: bool = False,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        for dev in devices:
            if require_input and dev.max_input_channels < 2:
                continue
            if require_output and dev.max_output_channels < 2:
                continue
            combo.addItem(f"{dev.index}: {dev.name}", dev.index)
        combo.blockSignals(False)

    # Band management ---------------------------------------------------
    def add_band(self) -> None:
        band = EQBand(frequency=1000.0, gain_db=0.0, q=1.0)
        self.bands.append(band)
        self._append_band_row(band)
        self._push_bands()

    def _append_band_row(self, band: EQBand) -> None:
        self._updating_table = True
        row = self.band_table.rowCount()
        self.band_table.insertRow(row)
        for col, value in enumerate([band.frequency, band.gain_db, band.q]):
            item = QtWidgets.QTableWidgetItem(f"{value:.3f}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, value)
            self.band_table.setItem(row, col, item)
        self._updating_table = False

    def remove_selected_band(self) -> None:
        rows = sorted({idx.row() for idx in self.band_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.band_table.removeRow(row)
            del self.bands[row]
        if rows:
            self._push_bands()

    def _on_band_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._updating_table:
            return
        row, col = item.row(), item.column()
        try:
            value = float(item.text())
        except ValueError:
            value = float(item.data(QtCore.Qt.ItemDataRole.UserRole) or 0.0)
        item.setText(f"{value:.3f}")
        item.setData(QtCore.Qt.ItemDataRole.UserRole, value)
        band = self.bands[row]
        if col == 0:
            band.frequency = value
        elif col == 1:
            band.gain_db = value
        elif col == 2:
            band.q = value
        self._push_bands()

    def _push_bands(self) -> None:
        self.audio.set_bands(self.bands)
        self.curve_canvas.update_curve(self.bands, self.sample_rate_spin.value())

    def _on_preamp_changed(self, slider_value: int) -> None:
        gain_db = slider_value / 10.0
        self.preamp_value.setText(f"{gain_db:+.1f} dB")
        self.audio.set_output_gain(gain_db)

    # Audio control -----------------------------------------------------
    def start_audio(self) -> None:
        input_id = self._current_device(self.input_combo)
        output_id = self._current_device(self.output_combo)
        if input_id is None or output_id is None:
            self.status_bar.showMessage("Select both input and output devices", 4000)
            return
        sample_rate = self.sample_rate_spin.value()
        block_size = self.block_size_spin.value()
        self.audio.configure(sample_rate, block_size, input_id, output_id)
        try:
            self.audio.start()
        except Exception as exc:
            self.status_bar.showMessage(f"Failed to start audio: {exc}", 5000)
            return
        latency_ms = 1000 * block_size / sample_rate
        self.latency_label.setText(f"Buffer ≈ {latency_ms:.1f} ms")
        self.status_bar.showMessage("Audio running", 2000)

    def stop_audio(self) -> None:
        self.audio.stop()
        self.status_bar.showMessage("Audio stopped", 2000)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # noqa: N802
        self.audio.close()
        return super().closeEvent(event)

    def _toggle_bypass(self, checked: bool) -> None:
        self.audio.set_bypass(checked)
        if checked:
            self.status_bar.showMessage("EQ bypassed (direct signal)", 2000)
        else:
            self.status_bar.showMessage("EQ engaged", 2000)

    def _current_device(self, combo: QtWidgets.QComboBox) -> Optional[int]:
        idx = combo.currentIndex()
        if idx < 0:
            return None
        return combo.currentData()

    # Telemetry ---------------------------------------------------------
    def _poll_meters(self) -> None:
        meter = self.audio.get_meter()
        self._set_meter(self.input_meter, meter.input_dbfs)
        self._set_meter(self.output_meter, meter.output_dbfs)

    def _set_meter(self, widget: QtWidgets.QWidget, value_db: float) -> None:
        bar = widget.progress  # type: ignore[attr-defined]
        bar.setValue(int(value_db))

    def _poll_backend_status(self) -> None:
        for message in self.audio.poll_status():
            self.status_log.appendPlainText(message)


def run() -> None:
    import sys

    app = QtWidgets.QApplication(sys.argv)
    window = EqualiserWindow()
    window.show()
    sys.exit(app.exec())
