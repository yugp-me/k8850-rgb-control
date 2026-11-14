import json
import tkinter as tk
from tkinter import ttk, colorchooser, messagebox, filedialog
from pathlib import Path

try:
    import hid
except ImportError:
    hid = None

VID, PID = 0x514C, 0x8850
REPORT_SIZE = 64
ROOT = Path(__file__).resolve().parent
PROFILE_FILE = ROOT / "profiles.json"
PROFILE_VERSION = 3
MODES = {"Off": 0, "Static": 1, "Reactive": 2, "Ripple": 3,
         "Rainbow (rows)": 4, "Rainbow (columns)": 5}
DEFAULT_COLOR = "#FFFFFF"


def valid_color(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return False
    try:
        int(value[1:], 16)
        return True
    except ValueError:
        return False


def rgb(value):
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def scale_color(value, percent):
    return tuple(max(0, min(255, round(c * percent / 100))) for c in rgb(value))


class K8850Manager:
    def __init__(self, root):
        self.root = root
        root.title("K8850 RGB Manager")
        root.geometry("790x700")
        root.minsize(720, 650)
        self.device = None
        self.profiles = self.load_profiles()
        self.layer = tk.IntVar(value=0)
        self.mode = tk.StringVar()
        self.brightness = tk.IntVar()
        self.brightness_label = tk.StringVar()
        self.status = tk.StringVar(value="Disconnected")
        self.selected = tk.IntVar(value=0)
        self.base_color = tk.StringVar()
        self.key_buttons = []
        self.build()
        self.load_layer()
        root.protocol("WM_DELETE_WINDOW", self.close)

    def default_profile(self):
        return {"mode": "Static", "brightness": 35,
                "colors": [DEFAULT_COLOR] * 15 + ["#000000"],
                "base_color": DEFAULT_COLOR}

    def load_profiles(self):
        defaults = [self.default_profile() for _ in range(3)]
        try:
            raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != PROFILE_VERSION:
                return defaults
            layers = raw.get("layers")
            if not isinstance(layers, dict):
                return defaults

            loaded = []
            for i in range(3):
                candidate = layers.get(str(i))
                if not isinstance(candidate, dict):
                    return defaults
                mode = candidate.get("mode")
                brightness = candidate.get("brightness")
                colors = candidate.get("colors")
                base_color = candidate.get("base_color")
                if mode not in MODES or not isinstance(brightness, int):
                    return defaults
                if not 0 <= brightness <= 100:
                    return defaults
                if not isinstance(colors, list) or len(colors) != 16:
                    return defaults
                if not all(valid_color(c) for c in colors) or not valid_color(base_color):
                    return defaults
                loaded.append({
                    "mode": mode,
                    "brightness": brightness,
                    "colors": [c.upper() for c in colors],
                    "base_color": base_color.upper(),
                })
            return loaded
        except (OSError, ValueError, TypeError):
            return defaults

    def save_profiles(self, quiet=False):
        data = {"version": PROFILE_VERSION,
                "device": "K8850 (USB VID 514C, PID 8850)",
                "layers": {str(i): self.profiles[i] for i in range(3)}}
        PROFILE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if not quiet:
            messagebox.showinfo("Profiles saved", f"Saved locally to:\n{PROFILE_FILE}", parent=self.root)

    def build(self):
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="K8850 RGB Manager", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(outer, text="16-key | 3-knob macropad | USB 514C:8850",
                  foreground="#666").pack(anchor="w", pady=(0, 10))

        dev = ttk.LabelFrame(outer, text="Device connection", padding=9)
        dev.pack(fill="x", pady=(0, 10))
        ttk.Button(dev, text="Connect", command=self.connect).pack(side="left")
        ttk.Button(dev, text="Disconnect", command=self.disconnect).pack(side="left", padx=6)
        ttk.Label(dev, textvariable=self.status).pack(side="left", padx=10)
        ttk.Label(dev, text="Use wired USB mode.",
                  foreground="#666").pack(side="right")

        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True)
        left = ttk.LabelFrame(body, text="Key colors (click a key to edit)", padding=10)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.key_grid = ttk.Frame(left)
        self.key_grid.pack(pady=8)
        for r in range(4):
            for c in range(4):
                idx = r * 4 + c
                b = tk.Button(self.key_grid, text=f"{idx + 1:02d}", width=7, height=3,
                              relief="raised", bd=2, command=lambda n=idx: self.edit_key(n))
                b.grid(row=r, column=c, padx=4, pady=4)
                self.key_buttons.append(b)
        ttk.Button(left, text="Set all keys to one color", command=self.set_all_color).pack(anchor="w", pady=(10, 0))

        right = ttk.LabelFrame(body, text="Layer settings", padding=12)
        right.pack(side="right", fill="y")
        ttk.Label(right, text="Layer").pack(anchor="w")
        layer_box = ttk.Combobox(right, state="readonly", width=20,
                                 values=["Layer 1", "Layer 2", "Layer 3"])
        layer_box.current(0)
        layer_box.pack(fill="x", pady=(3, 12))
        layer_box.bind("<<ComboboxSelected>>", lambda e: self.change_layer(layer_box.current()))
        self.layer_box = layer_box

        ttk.Label(right, text="LED effect").pack(anchor="w")
        mode_box = ttk.Combobox(right, state="readonly", width=20,
                                textvariable=self.mode, values=list(MODES))
        mode_box.pack(fill="x", pady=(3, 12))
        mode_box.bind("<<ComboboxSelected>>", lambda e: self.update_mode_note())

        ttk.Label(right, text="Brightness (static / reactive / ripple)").pack(anchor="w")
        slider = ttk.Scale(right, from_=0, to=100, orient="horizontal",
                           command=self.on_brightness)
        slider.pack(fill="x", pady=(5, 0))
        self.slider = slider
        ttk.Label(right, textvariable=self.brightness_label).pack(anchor="e")

        ttk.Label(right, text="Key 1 color").pack(anchor="w", pady=(12, 3))
        base_row = ttk.Frame(right)
        base_row.pack(fill="x")
        self.base_swatch = tk.Label(base_row, width=4, relief="solid", bd=1)
        self.base_swatch.pack(side="left")
        ttk.Button(base_row, text="Choose", command=self.choose_base).pack(side="left", padx=6)

        ttk.Separator(right).pack(fill="x", pady=8)
        ttk.Button(right, text="Apply selected layer", command=self.apply_selected).pack(fill="x", pady=3)
        ttk.Button(right, text="Apply all 3 layers", command=self.apply_all).pack(fill="x", pady=3)
        ttk.Button(right, text="Save profile", command=self.save_profiles).pack(fill="x", pady=3)
        ttk.Button(right, text="Load profile", command=self.load_profile_dialog).pack(fill="x", pady=3)

        apply_notice = ("Applying replaces the LED effects and colors for the selected layer(s). "
                        "Key bindings and knob assignments are not modified.")
        ttk.Label(outer, text=apply_notice, wraplength=760, justify="left",
                  foreground="#666").pack(anchor="w", pady=(12, 0))

    def current_profile(self):
        p = self.profiles[self.layer.get()]
        p["mode"] = self.mode.get() if self.mode.get() in MODES else "Static"
        p["brightness"] = int(self.brightness.get())
        p["base_color"] = self.base_color.get()
        return p

    def load_layer(self):
        p = self.profiles[self.layer.get()]
        self.mode.set(p["mode"])
        self.brightness.set(p["brightness"])
        self.slider.set(p["brightness"])
        self.brightness_label.set(f"{p['brightness']}%")
        self.base_color.set(p["base_color"])
        self.refresh_keys()
        self.update_mode_note()

    def change_layer(self, index):
        self.current_profile()
        self.layer.set(index)
        self.selected.set(0)
        self.load_layer()

    def refresh_keys(self):
        colors = self.profiles[self.layer.get()]["colors"]
        for i, button in enumerate(self.key_buttons):
            color = colors[self.physical_key_to_slot(i)]
            lum = sum(rgb(color))
            button.configure(bg=color, activebackground=color,
                             fg=("black" if lum > 380 else "white"),
                             activeforeground=("black" if lum > 380 else "white"))
        self.base_color.set(colors[0])
        self.base_swatch.configure(bg=colors[0])

    @staticmethod
    def physical_key_to_slot(index):
        return 0 if index in (0, 1) else index - 1

    def edit_key(self, index):
        slot = self.physical_key_to_slot(index)
        self.selected.set(index)
        initial = self.profiles[self.layer.get()]["colors"][slot]
        chosen = colorchooser.askcolor(color=initial, parent=self.root,
                                       title=f"Choose color for key {index + 1}")
        if chosen and chosen[1]:
            self.profiles[self.layer.get()]["colors"][slot] = chosen[1].upper()
            if slot == 0:
                self.base_color.set(chosen[1].upper())
            self.refresh_keys()

    def set_all_color(self):
        chosen = colorchooser.askcolor(color=self.base_color.get(), parent=self.root,
                                       title="Set all key colors")
        if chosen and chosen[1]:
            self.profiles[self.layer.get()]["colors"] = [chosen[1].upper()] * 15 + ["#000000"]
            self.base_color.set(chosen[1].upper())
            self.refresh_keys()

    def choose_base(self):
        chosen = colorchooser.askcolor(color=self.base_color.get(), parent=self.root,
                                       title="Choose color for key 1")
        if chosen and chosen[1]:
            self.base_color.set(chosen[1].upper())
            self.profiles[self.layer.get()]["colors"][0] = chosen[1].upper()
            self.refresh_keys()

    def on_brightness(self, value):
        n = round(float(value))
        self.brightness.set(n)
        self.brightness_label.set(f"{n}%")

    def update_mode_note(self):
        mode = self.mode.get()
        if mode in ("Rainbow (rows)", "Rainbow (columns)", "Off"):
            self.slider.configure(state="disabled")
        else:
            self.slider.configure(state="normal")

    def find_device(self):
        if hid is None:
            raise RuntimeError("The hidapi package is not installed. Install it and try again.")
        items = [d for d in hid.enumerate(VID, PID) if d.get("usage_page") == 0xFF00]
        if not items:
            raise RuntimeError("No vendor-defined configuration HID interface found. Connect by USB cable in wired mode.")
        items.sort(key=lambda d: (d.get("interface_number", 99), d.get("path", b"")))
        return items[0]

    def connect(self):
        if self.device:
            return
        try:
            info = self.find_device()
            self.device = hid.device()
            self.device.open_path(info["path"])
            self.device.set_nonblocking(0)
            self.status.set("Connected | 514C:8850")
        except Exception as exc:
            self.disconnect()
            messagebox.showerror("Connection failed", str(exc), parent=self.root)

    def disconnect(self):
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
        self.device = None
        self.status.set("Disconnected")

    def send(self, payload):
        if not self.device:
            raise RuntimeError("Connect the macropad first.")
        if len(payload) > REPORT_SIZE:
            raise ValueError("HID report exceeds 64 bytes.")
        report = bytes(payload + [0] * (REPORT_SIZE - len(payload)))
        if self.device.write(report) <= 0:
            raise RuntimeError("HID write failed. Reconnect the device and try again.")

    def make_led_packet(self, layer_index):
        p = self.profiles[layer_index]
        mode = MODES[p["mode"]]
        factor = p["brightness"]
        colors = p["colors"]
        base = scale_color(colors[0], factor) if mode in (1, 2, 3) else rgb(colors[0])
        payload = [0x03, 0xFE, 0xB0, layer_index, mode, *base]
        for color in colors:
            value = scale_color(color, factor) if mode in (1, 2, 3) else rgb(color)
            payload.extend(value)
        return payload

    def send_layer(self, layer_index):
        self.send([0x03, 0xFB, 0xFB, 0xFB])
        self.send(self.make_led_packet(layer_index))

    def apply_selected(self):
        self.current_profile()
        layer = self.layer.get()
        try:
            self.send_layer(layer)
            self.save_profiles(quiet=True)
        except Exception as exc:
            messagebox.showerror("Could not apply", str(exc), parent=self.root)

    def apply_all(self):
        self.current_profile()
        try:
            for i in range(3):
                self.send_layer(i)
            self.save_profiles(quiet=True)
        except Exception as exc:
            messagebox.showerror("Could not apply all layers", str(exc), parent=self.root)

    def load_profile_dialog(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load K8850 profile",
                                          filetypes=[("JSON profiles", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != PROFILE_VERSION:
                raise ValueError("This profile format is not supported by this version of the app.")
            layers = data.get("layers", {})
            loaded = []
            for i in range(3):
                p = self.default_profile()
                p.update(layers.get(str(i), {}))
                if not isinstance(p.get("colors"), list) or len(p["colors"]) != 16:
                    raise ValueError(f"Layer {i + 1} must contain exactly 16 colors.")
                if p.get("mode") not in MODES:
                    raise ValueError(f"Layer {i + 1} has an unsupported LED mode.")
                if not valid_color(p.get("base_color")) or len(p.get("colors", [])) != 16 or not all(valid_color(c) for c in p["colors"]):
                    raise ValueError(f"Layer {i + 1} must contain a base color and exactly 16 valid #RRGGBB colors.")
                p["brightness"] = max(0, min(100, int(p["brightness"])))
                loaded.append(p)
            self.profiles = loaded
            self.load_layer()
            messagebox.showinfo("Profile loaded", "Profile loaded into the editor. Apply it to send it to the macropad.", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Could not load profile", str(exc), parent=self.root)

    def close(self):
        try:
            self.current_profile()
            self.save_profiles(quiet=True)
        except Exception:
            pass
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    K8850Manager(root)
    root.mainloop()


if __name__ == "__main__":
    main()
