# Repository Guidelines

## Project Structure & Module Organization
Source now lives directly under `equaliser/`: `audio/stream.py` owns the sounddevice capture/playback loop, `dsp/{engine,filters,signals}.py` implement the parametric EQ math with NumPy, and `gui/{main_window,plotting}.py` hosts the PyQt6 UI and visualizers. `__main__.py` is the CLI entry for `python -m equaliser`, while `tools/` contains utility scripts such as the offline DSP harness. Build artifacts live in `build/` and `dist/Equaliser.app`; only touch them when packaging with py2app.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate` – create the local macOS env.
- `pip install -r requirements.txt && pip install -e .` (append `-r requirements-dev.txt` before packaging) – install runtime deps and expose the package.
- `python -m equaliser` – launch the GUI for debugging.
- `python tools/test_dsp.py --freq 1000 --gain 6 --q 1.5` – smoke-test filter math without audio hardware.
- `python setup.py py2app` – assemble `dist/Equaliser.app` after activating the venv and installing dev deps.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation, descriptive snake_case for functions, UpperCamelCase for PyQt widgets, and dataclasses for domain objects (see `dsp/engine.py:EQEngine`). Favor explicit type hints and shape checks for NumPy arrays; log or raise `ValueError` when inputs violate expectations. Keep modules focused (audio I/O, DSP, GUI) and avoid mixing UI code inside DSP files.

## Testing Guidelines
Prefer `pytest` for new unit tests (create a `tests/` package next to `tools/` and run with `python -m pytest`). Exercise DSP changes through `tools/test_dsp.py` using representative frequencies and gain values, and document any new CLI flags. For GUI/audio routing work, note the manual scenario you used so reviewers can reproduce it.

## Commit & Pull Request Guidelines
Use short, imperative commit subjects similar to the existing `initialise` history entry, optionally following `component: action` (e.g., `dsp: fix meter clip`). Each PR should link related issues, summarize architecture or UI impacts, list the commands you ran (tests, `python -m equaliser`, `py2app` builds), and attach screenshots when UI changes touch `gui/main_window.py`. Keep PRs focused on one feature/fix to simplify QA.

## Security & Configuration Tips
This app requests microphone access because it captures macOS system audio through BlackHole. Verify Audio MIDI Setup before demos: create a Multi-Output Device, set consistent sample rates (44.1 or 48 kHz), and restart the in-app stream after rewiring devices. Never commit secrets or machine-specific paths; redact device logs before sharing.
