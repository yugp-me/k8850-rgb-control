# K8850 RGB Control

A desktop app for configuring the RGB lighting on the K8850 16-key, 3-layer macropad.

The macropad uses proprietary vendor firmware. Its bundled software supports colors
and lighting modes but does not provide RGB brightness control. This app communicates
with the device over USB HID (Vendor ID `514c`, Product ID `8850`) to add brightness control.

## Requirements

- Python 3.10 - 3.12 recommended.
- K8850 macropad connected by USB in wired mode

Install required dependencies:

```
python -m pip install -r requirements.txt
```

## Usage

Run the application:

```
python main.py
```

Click **Connect**, select a layer, and configure its key colors, LED effect,
and brightness. Use **Apply selected layer** or **Apply all 3 layers** to send
the settings to the macropad.

Supported effects:

- Off
- Static
- Reactive
- Ripple
- Rainbow by rows
- Rainbow by columns

Profiles are saved locally as `profiles.json` beside `main.py`. Loading or
saving a profile does not change key bindings or knob assignments.
