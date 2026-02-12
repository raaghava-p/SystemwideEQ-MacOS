"""PyQt6 main window for the system-wide EQ."""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from equaliser.audio.stream import AudioBackend, DeviceMetadata
from equaliser.dsp import EQBand, FILTER_TYPES
from equaliser import storage
from equaliser.autoeq import parse_autoeq_file
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


class PeakMeterBar(QtWidgets.QProgressBar):
    """QProgressBar with a red peak-hold tick mark."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._peak_hold_value: float = -60.0
        self._hold_ticks: int = 0  # ticks remaining at hold
        self._HOLD_DURATION: int = 10  # ticks (~1s at 100ms poll)
        self._DECAY_RATE: float = 1.5  # dB per tick

    def update_peak(self, new_peak_db: float) -> None:
        if new_peak_db > self._peak_hold_value:
            self._peak_hold_value = new_peak_db
            self._hold_ticks = self._HOLD_DURATION
        elif self._hold_ticks > 0:
            self._hold_ticks -= 1
        else:
            self._peak_hold_value = max(
                float(self.minimum()), self._peak_hold_value - self._DECAY_RATE
            )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._peak_hold_value <= self.minimum():
            return
        painter = QtGui.QPainter(self)
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 40, 40), 2))
        r = self.rect()
        frac = (self._peak_hold_value - self.minimum()) / max(
            1, self.maximum() - self.minimum()
        )
        x = int(r.left() + frac * r.width())
        painter.drawLine(x, r.top() + 1, x, r.bottom() - 1)
        painter.end()


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
        # Spectrum analyzer overlay (secondary y-axis)
        self.ax2 = self.ax.twinx()
        self.ax2.set_ylim(-80, 0)
        self.ax2.set_ylabel("Level (dBFS)")
        self.spectrum_line, = self.ax2.plot([], [], color="cyan", alpha=0.4, lw=1)
        # Cached FFT state (computed on GUI thread, not in RT audio)
        self._fft_window: Optional[np.ndarray] = None
        self._fft_freqs: Optional[np.ndarray] = None
        self._fft_sr: float = 0.0

    def update_curve(self, bands: List[EQBand], sample_rate: float) -> None:
        if not bands:
            self.line.set_data([], [])
            self.draw_idle()
            return
        freqs, magnitude = frequency_response(bands, sample_rate)
        self.line.set_data(freqs, np.clip(magnitude, -24, 24))
        self.draw_idle()

    def update_spectrum(self, mono_block: np.ndarray, sample_rate: float) -> None:
        """Compute FFT from a mono audio block and update the spectrum line.

        All FFT math runs here on the GUI thread, not in the RT audio callback.
        """
        n = len(mono_block)
        if n < 2:
            return
        if (self._fft_window is None or len(self._fft_window) != n
                or self._fft_sr != sample_rate):
            self._fft_window = np.hanning(n)
            self._fft_freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)
            self._fft_sr = sample_rate
        windowed = mono_block * self._fft_window
        fft = np.fft.rfft(windowed)
        magnitude = np.abs(fft) * 2.0 / n
        magnitude[0] /= 2.0  # DC component
        with np.errstate(divide="ignore"):
            db = 20 * np.log10(magnitude + 1e-20)
        db = np.clip(db, -120.0, 0.0)
        self.spectrum_line.set_data(self._fft_freqs, db)


class EqualiserWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("macOS System EQ (BlackHole)")
        self.resize(1100, 720)
        self.audio = AudioBackend()
        self.bands: List[EQBand] = []
        self._updating_table = False
        self._quitting = False

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
        self._load_session()
        self._setup_tray_icon()

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

        self.band_table = QtWidgets.QTableWidget(0, 5)
        self.band_table.setHorizontalHeaderLabels(
            ["On", "Type", "Frequency (Hz)", "Gain (dB)", "Q"]
        )
        self.band_table.horizontalHeader().setStretchLastSection(True)
        self.band_table.verticalHeader().setVisible(False)
        self.band_table.setColumnWidth(0, 40)
        self.band_table.setColumnWidth(1, 90)
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

        preset_row = QtWidgets.QHBoxLayout()
        preset_row.addWidget(QtWidgets.QLabel("Presets:"))
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setMinimumWidth(150)
        self._refresh_preset_list()
        preset_row.addWidget(self.preset_combo)
        self.load_preset_button = QtWidgets.QPushButton("Load")
        self.load_preset_button.clicked.connect(self._load_selected_preset)
        self.save_preset_button = QtWidgets.QPushButton("Save As...")
        self.save_preset_button.clicked.connect(self._save_preset_dialog)
        self.delete_preset_button = QtWidgets.QPushButton("Delete")
        self.delete_preset_button.clicked.connect(self._delete_selected_preset)
        self.import_autoeq_button = QtWidgets.QPushButton("Import AutoEQ...")
        self.import_autoeq_button.clicked.connect(self._import_autoeq)
        preset_row.addWidget(self.load_preset_button)
        preset_row.addWidget(self.save_preset_button)
        preset_row.addWidget(self.delete_preset_button)
        preset_row.addWidget(self.import_autoeq_button)
        preset_row.addStretch(1)
        layout.addLayout(preset_row)

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
        bar = PeakMeterBar()
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
        was_updating = self._updating_table
        self._updating_table = True
        row = self.band_table.rowCount()
        self.band_table.insertRow(row)
        # Column 0: enabled checkbox
        chk = QtWidgets.QTableWidgetItem()
        chk.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(
            QtCore.Qt.CheckState.Checked if band.enabled else QtCore.Qt.CheckState.Unchecked
        )
        self.band_table.setItem(row, 0, chk)
        # Column 1: filter type combo
        combo = QtWidgets.QComboBox()
        combo.addItems(FILTER_TYPES)
        combo.setCurrentText(band.filter_type)
        combo.currentTextChanged.connect(lambda text, c=combo: self._on_filter_type_changed(c, text))
        self.band_table.setCellWidget(row, 1, combo)
        # Columns 2-4: frequency, gain, Q
        for col, value in enumerate([band.frequency, band.gain_db, band.q], start=2):
            item = QtWidgets.QTableWidgetItem(f"{value:.3f}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole, value)
            self.band_table.setItem(row, col, item)
        self._update_gain_editable(row, band.filter_type)
        self._updating_table = was_updating

    def _on_filter_type_changed(self, combo: QtWidgets.QComboBox, text: str) -> None:
        if self._updating_table:
            return
        # Resolve the actual row at signal time to avoid stale captured indices
        row = -1
        for r in range(self.band_table.rowCount()):
            if self.band_table.cellWidget(r, 1) is combo:
                row = r
                break
        if row < 0 or row >= len(self.bands):
            return
        self.bands[row].filter_type = text
        self._update_gain_editable(row, text)
        self._push_bands()

    def _update_gain_editable(self, row: int, filter_type: str) -> None:
        """Disable the Gain cell for filter types that ignore it (HP/LP)."""
        gain_item = self.band_table.item(row, 3)
        if gain_item is None:
            return
        if filter_type in ("highpass", "lowpass"):
            gain_item.setFlags(
                gain_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable
            )
            gain_item.setForeground(QtGui.QColor(150, 150, 150))
        else:
            gain_item.setFlags(
                gain_item.flags() | QtCore.Qt.ItemFlag.ItemIsEditable
            )
            gain_item.setForeground(
                self.band_table.palette().color(QtGui.QPalette.ColorRole.Text)
            )

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
        if row < 0 or row >= len(self.bands):
            return
        band = self.bands[row]
        if col == 0:
            band.enabled = item.checkState() == QtCore.Qt.CheckState.Checked
            self._push_bands()
            return
        if col == 1:
            # Type column handled by combo widget signal
            return
        try:
            value = float(item.text())
        except ValueError:
            value = float(item.data(QtCore.Qt.ItemDataRole.UserRole) or 0.0)
        item.setText(f"{value:.3f}")
        item.setData(QtCore.Qt.ItemDataRole.UserRole, value)
        if col == 2:
            band.frequency = value
        elif col == 3:
            band.gain_db = value
        elif col == 4:
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
        if self._quitting:
            super().closeEvent(event)
            return
        if self.tray_icon.isVisible():
            self._save_session()
            self.hide()
            event.ignore()
            return
        self._quit_app()
        super().closeEvent(event)

    def _toggle_bypass(self, checked: bool) -> None:
        self.audio.set_bypass(checked)
        if hasattr(self, "tray_bypass_action"):
            self.tray_bypass_action.setChecked(checked)
        if checked:
            self.status_bar.showMessage("EQ bypassed (direct signal)", 2000)
        else:
            self.status_bar.showMessage("EQ engaged", 2000)

    def _current_device(self, combo: QtWidgets.QComboBox) -> Optional[int]:
        idx = combo.currentIndex()
        if idx < 0:
            return None
        return combo.currentData()

    # Tray icon ---------------------------------------------------------
    def _setup_tray_icon(self) -> None:
        icon_path = Path(__file__).resolve().parents[2] / "docs" / "icon.png"
        if icon_path.is_file():
            icon = QtGui.QIcon(str(icon_path))
        else:
            icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaVolume)
        self.tray_icon = QtWidgets.QSystemTrayIcon(icon, self)
        self.tray_icon.activated.connect(self._on_tray_activated)

        menu = QtWidgets.QMenu()
        self.tray_show_action = menu.addAction("Show/Hide Window")
        self.tray_show_action.triggered.connect(self._toggle_window_visibility)
        menu.addSeparator()
        self.tray_bypass_action = menu.addAction("Bypass EQ")
        self.tray_bypass_action.setCheckable(True)
        self.tray_bypass_action.setChecked(self.bypass_button.isChecked())
        self.tray_bypass_action.triggered.connect(self._tray_toggle_bypass)
        menu.addSeparator()
        self.tray_presets_menu = menu.addMenu("Presets")
        self._refresh_tray_presets()
        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit_app)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def _on_tray_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window_visibility()

    def _toggle_window_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _tray_toggle_bypass(self, checked: bool) -> None:
        self.bypass_button.setChecked(checked)
        self._toggle_bypass(checked)

    def _refresh_tray_presets(self) -> None:
        self.tray_presets_menu.clear()
        for name in storage.list_presets():
            action = self.tray_presets_menu.addAction(name)
            action.triggered.connect(lambda checked, n=name: self._tray_load_preset(n))

    def _tray_load_preset(self, name: str) -> None:
        result = storage.load_preset(name)
        if result is None:
            return
        bands, output_gain_db = result
        self._apply_preset(bands, output_gain_db)

    def _quit_app(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._save_session()
        self.audio.close()
        self.tray_icon.hide()
        QtWidgets.QApplication.quit()

    # Telemetry ---------------------------------------------------------
    def _poll_meters(self) -> None:
        meter = self.audio.get_meter()
        self._set_meter(self.input_meter, meter.input_dbfs, meter.input_peak_dbfs)
        self._set_meter(self.output_meter, meter.output_dbfs, meter.output_peak_dbfs)
        if meter.spectrum_block is not None:
            self.curve_canvas.update_spectrum(
                meter.spectrum_block.copy(), self.sample_rate_spin.value()
            )
            self.curve_canvas.draw_idle()

    def _set_meter(self, widget: QtWidgets.QWidget, value_db: float, peak_db: float = -120.0) -> None:
        bar: PeakMeterBar = widget.progress  # type: ignore[attr-defined]
        bar.setValue(int(value_db))
        bar.update_peak(peak_db)

    def _poll_backend_status(self) -> None:
        for message in self.audio.poll_status():
            self.status_log.appendPlainText(message)

    # Persistence -----------------------------------------------------------
    def _get_current_gain(self) -> float:
        """Get current preamp gain in dB from slider value."""
        return self.preamp_slider.value() / 10.0

    def _save_session(self) -> None:
        """Save current state to session file."""
        storage.save_session(self.bands, self._get_current_gain())

    def _load_session(self) -> None:
        """Load session state from disk if available."""
        result = storage.load_session()
        if result is None:
            return
        bands, output_gain_db = result
        self._apply_preset(bands, output_gain_db)
        self.status_bar.showMessage("Session restored", 2000)

    def _apply_preset(self, bands: List[EQBand], output_gain_db: float) -> None:
        """Apply a preset to the UI and audio backend."""
        was_updating = self._updating_table
        self._updating_table = True
        self.band_table.setRowCount(0)
        self.bands.clear()
        for band in bands:
            self.bands.append(band)
            self._append_band_row(band)
        self._updating_table = was_updating
        self.preamp_slider.setValue(int(output_gain_db * 10))
        self._push_bands()

    def _refresh_preset_list(self) -> None:
        """Refresh the preset combo box with available presets."""
        self.preset_combo.clear()
        for name in storage.list_presets():
            self.preset_combo.addItem(name)
        if hasattr(self, "tray_presets_menu"):
            self._refresh_tray_presets()

    def _save_preset_dialog(self) -> None:
        """Show dialog to save current preset with a name."""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Preset", "Preset name:"
        )
        if ok and name.strip():
            name = name.strip()
            storage.save_preset(name, self.bands, self._get_current_gain())
            self._refresh_preset_list()
            idx = self.preset_combo.findText(name)
            if idx >= 0:
                self.preset_combo.setCurrentIndex(idx)
            self.status_bar.showMessage(f"Preset '{name}' saved", 2000)

    def _load_selected_preset(self) -> None:
        """Load the currently selected preset."""
        name = self.preset_combo.currentText()
        if not name:
            return
        result = storage.load_preset(name)
        if result is None:
            self.status_bar.showMessage(f"Preset '{name}' not found", 2000)
            return
        bands, output_gain_db = result
        self._apply_preset(bands, output_gain_db)
        self.status_bar.showMessage(f"Preset '{name}' loaded", 2000)

    def _delete_selected_preset(self) -> None:
        """Delete the currently selected preset."""
        name = self.preset_combo.currentText()
        if not name:
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete preset '{name}'?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            storage.delete_preset(name)
            self._refresh_preset_list()
            self.status_bar.showMessage(f"Preset '{name}' deleted", 2000)

    def _import_autoeq(self) -> None:
        """Import an AutoEQ ParametricEQ.txt file."""
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import AutoEQ Profile", "", "Text files (*.txt);;All files (*)"
        )
        if not filepath:
            return
        try:
            bands, preamp_db = parse_autoeq_file(filepath)
        except Exception as exc:
            self.status_bar.showMessage(f"AutoEQ import failed: {exc}", 5000)
            return
        if not bands:
            self.status_bar.showMessage("No filters found in file", 3000)
            return
        self._apply_preset(bands, preamp_db)
        self.status_bar.showMessage(f"Imported {len(bands)} bands from AutoEQ", 3000)


def run() -> None:
    import sys

    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = EqualiserWindow()
    window.show()
    sys.exit(app.exec())
