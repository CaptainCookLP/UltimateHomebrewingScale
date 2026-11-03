# Debug Mode Guide

## Configuration

### Enable or Disable Debug Traces

In `config.py`:

```python
# Debug mode (set to True to enable debug prints)
DEBUG = False  # Default: no traces
DEBUG = True   # Enable traces
```

### Behavior

With `DEBUG = False` by default:
- No console debug prints
- Smooth UI with no debug slowdown
- Only fatal errors are displayed

With `DEBUG = True`:
- Startup traces
- Launcher events
- App startup traces
- Long-press detection
- Scale calibration traces
- Detailed errors
- Memory markers with Python heap and ESP-IDF C-heap values

## Modified Files

All `print()` calls are gated by `DEBUG`:

- `main.py` - System initialization
- `apps/launcher_app.py` - Launcher navigation logic
- `ui/launcher_screen.py` - Launcher UI
- `apps/base_app.py` - Long-press detection
- `apps/scale_app.py` - Calibration and weighing
- Other apps: grain, hop, keg, settings

## Long Press to Return to the Launcher

### How to Use

From any app:

1. Hold the center button.
2. Wait 3 seconds.
3. The app closes and returns to the launcher.

### Implementation

Detection is handled in `BaseApp.check_return_to_launcher()`:

```python
# Long press duration
LONG_PRESS_DURATION = 3000  # 3 seconds in ms

# Automatically called in the main loop
# of every app inheriting from BaseApp
```

### Covered Apps

All apps inheriting from `BaseApp`:
- Scale App
- Grain Assistant
- Hop Assistant
- Keg Filler
- Settings

### Debug Long Press

With `DEBUG = True`, this message is printed:

```text
Long press detected - returning to launcher
```

## Deployment

Upload these modified files to the M5Dial:

- `config.py` with `DEBUG = False` or `DEBUG = True`
- `main.py`
- `apps/launcher_app.py`
- `ui/launcher_screen.py`
- `apps/base_app.py`
- `apps/scale_app.py`

## Manual Check

```python
# On the M5Dial
exec(open("main.py").read())

# 1. The launcher is displayed, with no traces if DEBUG=False.
# 2. Select Scale.
# 3. Hold the center button for 3 seconds.
# 4. The app returns to the launcher automatically.
```

## Performance

Memory impact: none when `DEBUG = False`, because debug strings are not created.

Smoothness: improved when debug traces are disabled.

Long-press latency: less than 50 ms.

## Memory validation markers

Capture the three values printed by `[MEM]` markers:

- `py_free`: free MicroPython heap.
- `c_free`: total free ESP-IDF heap, when supported by the firmware.
- `c_largest`: largest contiguous C-heap block; this is the fragmentation-
  sensitive value that matters most before LVGL, TLS, and JSON allocations.

Useful boundaries are `boot.after_m5_begin`, `boot.after_hardware`,
`boot.after_api_factory`, `screen.memory_cleanup`, `wifi.ensure.*`,
`api.body.spooled`, `api.body.closed`, `api.json.parsed`,
`updater.workflow.after_archive_download`, and the portal request logs.
Compare values before/after each boundary and after repeated app transitions.
The `collect=True` flag now performs one Python GC before the measurement;
disabled snapshots do not query heap diagnostics. `verbose=True` on
`memory_debug.snapshot()` additionally requests the MicroPython allocator dump.

## Passive Windows capture across USB resets

For repeated USB disconnects use the host-only `tools/serial_capture.py`. It
writes timestamped device lines and host connection/disconnection markers to a
unique file in Downloads. It appends if an explicit existing output filename
is used. It does not enter raw REPL, send Ctrl-C/Ctrl-D or issue reset commands.
RTS/DTR are set false before opening; OS/USB drivers may still affect control
lines, so this cannot guarantee a reset-free serial open on every platform.

```powershell
py -3.13 -m pip install --upgrade pyserial
py -3.13 .\tools\serial_capture.py --port COM7
```

Only one monitor can own COM7; close mpremote, esptool and other serial tools
first. Start the logger, reproduce a problem using the Dial, and keep it open
through a disconnect/reconnect. Ctrl-C stops the PC logger without transmitting
Ctrl-C to the device. The console prints the exact logfile path at startup.

When a unique USB serial number is available, the logger follows that device
even if Windows assigns a different COM number. Without one it waits for the
requested port rather than guessing among other attached boards. USB events
alone do not prove a CPU reset; use any captured boot/panic/reset messages to
classify the event. Very early boot output can occur before USB enumerates.

This tool does not change DEBUG or device configuration. Enable DEBUG on the
device beforehand as described above; a full firmware flash can replace that
setting. `Weight Unit not found in Grove` indicates the real hardware driver
could not find the unit on that boot. For hardware-free tests, explicitly enable
`SIMULATION_ENABLED` and restart. A `local=dev` version value is not a uniquely
identifiable release. Low free memory without a MemoryError/panic is a clue,
not proof of a reset cause.

Host-side regression checks: `python tools/verify_serial_capture.py`.
