# EQ Preset Persistence Feature

## Summary
Added persistence for EQ presets so settings survive app restarts.

## Changes Made

### New File: `equaliser/storage.py`
Storage module for saving/loading presets and session state.

**Functions:**
- `get_app_data_dir()` - Returns `~/Library/Application Support/Equaliser/`
- `save_session(bands, output_gain_db)` - Auto-save current state
- `load_session()` - Load last session on startup
- `save_preset(name, bands, output_gain_db)` - Save named preset
- `load_preset(name)` - Load named preset
- `list_presets()` - List all saved presets
- `delete_preset(name)` - Remove a preset

### Modified: `equaliser/gui/main_window.py`
- Added `from equaliser import storage` import
- Added `_load_session()` call in `__init__` to restore state on startup
- Added `_save_session()` call in `closeEvent()` to save on close
- Added preset management UI row with:
  - Preset dropdown (combo box)
  - Load button
  - Save As... button
  - Delete button
- Added methods: `_get_current_gain()`, `_save_session()`, `_load_session()`, `_apply_preset()`, `_refresh_preset_list()`, `_save_preset_dialog()`, `_load_selected_preset()`, `_delete_selected_preset()`

### Fixed: `equaliser/gui/__init__.py`
- Fixed `AttributeError: 'SourceFileLoader' object has no attribute 'origin'`
- Changed `spec.origin` to use `loader.get_filename()` instead

## Storage Format
```json
{
  "version": 1,
  "output_gain_db": -3.0,
  "bands": [
    {"frequency": 100.0, "gain_db": 3.0, "q": 1.0, "enabled": true}
  ]
}
```

## Storage Locations
- Session: `~/Library/Application Support/Equaliser/session.json`
- Presets: `~/Library/Application Support/Equaliser/presets/<name>.json`

## Known Issues
- py2app build was interrupted/failed during testing
- Qt platform plugin issue when running from source (architecture-related)
- App may need to be run with `arch -arm64` on Apple Silicon

## Testing Status
- Code syntax verified with `python -m py_compile`
- Storage module imports successfully
- Full app testing incomplete due to Qt plugin issues
