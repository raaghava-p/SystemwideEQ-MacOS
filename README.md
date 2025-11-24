# Systemwide Equaliser for MacOS

A Python + PyQt6 desktop app that captures all MacOS audio via the BlackHole virtual driver, applies configurable parametric EQ bands in real-time, and forwards the processed mix to your preferred output device, created with GPT-5 codex.

![ImageOfGUI](https://github.com/raaghava-p/SystemwideEQ-MacOS/blob/f570fdd89ad0c9fd38adf8e06f7c62fe774818fe/6104384A-4D7A-4183-A3A9-5C685E01FAB6.png)
## Prerequisites
- **Homebrew packages**: Install [Homebrew](https://brew.sh) and run `brew install blackhole-2ch portaudio python@3.11` to pull [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole), [PortAudio](https://www.portaudio.com), and [Python 3.11](https://www.python.org).
- **Virtual environment**: `python3 -m venv .venv && source .venv/bin/activate`
- **Python deps**: `pip install -r requirements.txt`
- **Expose the package**: `pip install -e .` (or set `PYTHONPATH=src` before running commands)
- Grant microphone/input permissions to the terminal or app bundle when macOS prompts you.

## Device Routing Setup
1. Open **Audio MIDI Setup** ➝ click `+` ➝ **Create Multi-Output Device**.
2. Enable **BlackHole** and your real speakers/headphones. Set the physical device as the master clock and enable drift correction on BlackHole.
3. (Optional) Create an **Aggregate Device** when you need DAW capture + playback simultaneously.
4. In **System Settings → Sound → Output**, select the Multi-Output Device so all system audio flows into BlackHole.
5. Launch this app and pick **BlackHole** as the input device, and the physical device as the output device.

## Running the App
```bash
source .venv/bin/activate
pip install -e .  # ensures `python -m equaliser` works without tweaking PYTHONPATH
python -m equaliser
```
When the GUI opens:
- Use **Audio Devices** to choose input/output, sample rate (match Audio MIDI Setup), and buffer size (256 frames ≈ 5.3 ms @ 48 kHz).
- Click **Start Audio**; use **Stop** before changing devices.
- Add parametric bands with `Add Band`, edit frequency/gain/Q directly in the table, and remove unwanted rows.
- Use the **Global Gain / Preamp** slider below the band table to trim or boost the overall mix (±12 dB, default -3 dB) for extra headroom.
- Toggle `EQ Bypass (A/B)` for instant comparison.
- Watch the live EQ curve and input/output meters to confirm levels.

## Testing the DSP Core
Use the offline harness to validate the filter math without real audio hardware:
```bash
python3 tools/test_dsp.py --freq 1000 --gain 6 --q 1.5 --duration 1.0
```
This generates a sine wave, runs it through the EQ engine, and prints RMS levels.

## Troubleshooting
- **No sound**: Confirm MacOS output is set to the Multi-Output Device and that this app shows `Audio running` in the status bar. Restart the audio stream after changing system devices.
- **Device missing**: Click `Refresh`. If BlackHole is absent, reinstall via Homebrew and reopen Audio MIDI Setup.
- **Pops or latency**: Lower the buffer size, close heavy apps, or lock everything to the same sample rate (44.1 kHz or 48 kHz). Larger buffers add latency but increase stability.
- **Clipping**: Reduce band gain or enable negative overall gain in the DSP (default -3 dB headroom). Watch the meters; anything near 0 dBFS risks clipping.
- **Permission errors**: Allow microphone/input monitoring for the terminal/Python interpreter in System Settings.

## Building the MacOS App Bundle (py2app)
Use `py2app` when you want a self-contained `.app` bundle that can be launched from Finder like any other macOS application.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e .
python setup.py py2app
```

The build drops `dist/Equaliser.app`. Copy that bundle into `/Applications` (or anywhere else) and launch it; the first run may take a few seconds while macOS verifies the binary. If you plan to distribute the app beyond your own machine, follow Apple’s signing/notarization flow after running `py2app`.

## Known Limitations
- Uses the system default stereo sample format; surround formats are not yet supported.
- Requires the app to keep running; background/menubar packaging not provided.
- Device hot-plugging is not automatic—stop/start the stream after wiring changes.
