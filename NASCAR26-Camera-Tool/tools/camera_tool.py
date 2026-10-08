"""NASCAR 26 Camera Tool: a window to change the field of view and position of every driving camera (cockpit,
hood, bumper, chase). Settings are saved in %APPDATA%\\NASCAR26 Camera Tool\\settings.json and written into the
running game's memory (camera_core.py) whenever they change and each time the game is found. Same values for every
series. Changes show on cars loaded afterwards, so restart the race to see them; closing the game restores stock.
"""
import json, os, pathlib, queue, sys, threading, time, tkinter as tk
import camera_core as cc

BG, CARD, EDGE = "#111317", "#1a1d23", "#2a2e36"
TEXT, DIM, ACCENT = "#f2f2f2", "#8b909a", "#4da3ff"
OK, WARN, BAD = "#3ddc84", "#ffb020", "#ff4d4d"
FONT = "Segoe UI"
CFG_DIR = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home())) / "NASCAR26 Camera Tool"
CFG = CFG_DIR / "settings.json"
ICON = (pathlib.Path(sys._MEIPASS) if getattr(sys, "frozen", False) else cc.ROOT / "assets") / "tire.ico"
# slider label, settings key, low/high end label, range for on-car views, range for chase views
ROWS = [
    ("Up / down", "up", "Down", "Up", 100, 300),
    ("Left / right", "right", "Left", "Right", 100, 300),
    ("Back / forward", "forward", "Back", "Forward", 100, 500),
]


def load_settings():
    s = cc.blank()
    try:
        saved = json.loads(CFG.read_text(encoding="utf-8"))
        for k, v in saved.items():
            if k in s:
                s[k].update({a: v[a] for a in s[k] if a in v})
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return s


def save_settings(s):
    try:
        CFG_DIR.mkdir(parents=True, exist_ok=True)
        CFG.write_text(json.dumps(s, indent=1), encoding="utf-8")
    except OSError:
        pass


class Worker(threading.Thread):
    """Finds the game and writes the settings; talks to the window only through a queue."""

    def __init__(self, cams, out):
        super().__init__(daemon=True)
        self.cams, self.out = cams, out
        self.pending = None
        self.lock = threading.Lock()
        self.wake = threading.Event()

    def push(self, settings):
        with self.lock:
            self.pending = json.loads(json.dumps(settings))
        self.wake.set()

    def run(self):
        connected, current = False, None
        while True:
            self.wake.wait(2)
            self.wake.clear()
            with self.lock:
                if self.pending is not None:
                    current, self.pending = self.pending, None
                    dirty = True
                else:
                    dirty = False
            try:
                now = self.cams.connect()
            except cc.Unsupported:
                self.out.put(("status", BAD, "This NASCAR 26 version isn't supported yet - nothing was changed."))
                time.sleep(10)
                continue
            if not now:
                if connected or current is None:
                    self.out.put(("status", WARN, "Waiting for NASCAR 26... (start the game, this finds it)"))
                connected = False
                continue
            if not connected or dirty:
                connected = True
                if current is None:
                    continue
                written, problems = self.cams.apply(current)
                if problems and not written:
                    self.cams.disconnect()
                    connected = False
                    self.out.put(("status", BAD, "Couldn't change the cameras: " + problems[0]))
                elif problems:
                    self.out.put(("status", WARN, f"Applied, but skipped {len(problems)}: " + "; ".join(problems[:2])))
                else:
                    self.out.put(("status", OK, "Applied to the game. Restart the race to see changes."))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NASCAR 26 Camera Tool")
        try:
            self.iconbitmap(default=str(ICON))
        except tk.TclError:
            pass
        self.configure(bg=BG)
        self.resizable(False, False)
        self.settings = load_settings()
        self.cams = cc.Cameras()
        self.stock = next(iter(self.cams.stock.values()))   # stock values to show (same for every series)
        self.view = cc.VIEWS[0][0]
        self.loading = False
        self.save_job = None
        self.msgs = queue.Queue()
        self._build()
        self._select(self.view)
        self.worker = Worker(self.cams, self.msgs)
        self.worker.start()
        self.worker.push(self.settings)
        self.after(150, self._poll)

    # ---------- layout ----------
    def _card(self, parent, **pack):
        f = tk.Frame(parent, bg=CARD, highlightbackground=EDGE, highlightthickness=1, padx=14, pady=10)
        f.pack(**pack)
        return f

    def _build(self):
        tk.Label(self, text="NASCAR 26 Camera Tool", bg=BG, fg=TEXT, font=(FONT, 15, "bold")).pack(
            anchor="w", padx=16, pady=(14, 0))
        tk.Label(self, text="Field of view and position of every driving camera. Applies to all series.",
                 bg=BG, fg=DIM, font=(FONT, 9)).pack(anchor="w", padx=16, pady=(0, 10))

        st = self._card(self, fill="x", padx=16, pady=(0, 10))
        self.dot = tk.Label(st, text="●", bg=CARD, fg=WARN, font=(FONT, 11))
        self.dot.pack(side="left")
        self.status = tk.Label(st, text="Starting...", bg=CARD, fg=TEXT, font=(FONT, 10), wraplength=560,
                               justify="left")
        self.status.pack(side="left", padx=(6, 0))

        body = tk.Frame(self, bg=BG)
        body.pack(fill="x", padx=16)
        left = self._card(body, side="left", fill="y", padx=(0, 10))
        tk.Label(left, text="VIEW", bg=CARD, fg=DIM, font=(FONT, 8, "bold")).pack(anchor="w", pady=(0, 6))
        self.view_btns = {}
        for key, label in cc.VIEWS:
            b = tk.Label(left, text=label, bg=CARD, fg=TEXT, font=(FONT, 10), anchor="w", padx=10, pady=4,
                         width=17, cursor="hand2")
            b.pack(fill="x", pady=1)
            b.bind("<Button-1>", lambda e, k=key: self._select(k))
            self.view_btns[key] = b

        right = self._card(body, side="left", fill="both", expand=True)
        self.view_title = tk.Label(right, bg=CARD, fg=TEXT, font=(FONT, 13, "bold"))
        self.view_title.pack(anchor="w")
        self.view_note = tk.Label(right, bg=CARD, fg=DIM, font=(FONT, 9), justify="left", wraplength=360)
        self.view_note.pack(anchor="w", pady=(0, 8))
        self.sliders = {}
        self.sliders["fov"] = self._slider(right, "Field of view", "Narrow 30°", "Wide 130°", 30, 130, "°")
        for title, key, lo, hi, _, _ in ROWS:
            self.sliders[key] = self._slider(right, title, lo, hi, -100, 100, " cm")
        btns = tk.Frame(right, bg=CARD)
        btns.pack(fill="x", pady=(12, 0))
        self._button(btns, "Reset this view", self._reset_view).pack(side="left")
        self._button(btns, "Reset all views", self._reset_all).pack(side="left", padx=8)

        tk.Label(self, text="Changes save automatically and are sent to the game straight away. Restart the race "
                            "(or start a new one) to see them. Closing the game puts the stock cameras back: open this "
                            "tool again next time to reapply. Offline modes only.",
                 bg=BG, fg=DIM, font=(FONT, 9), wraplength=600, justify="left").pack(anchor="w", padx=16,
                                                                                    pady=(10, 14))

    def _button(self, parent, text, cmd):
        b = tk.Label(parent, text=text, bg=EDGE, fg=TEXT, font=(FONT, 9), padx=10, pady=4, cursor="hand2")
        b.bind("<Button-1>", lambda e: cmd())
        return b

    def _slider(self, parent, title, lo_text, hi_text, lo, hi, unit):
        f = tk.Frame(parent, bg=CARD)
        f.pack(fill="x", pady=4)
        head = tk.Frame(f, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text=title, bg=CARD, fg=TEXT, font=(FONT, 10)).pack(side="left")
        value = tk.Label(head, bg=CARD, fg=ACCENT, font=(FONT, 10, "bold"))
        value.pack(side="right")
        row = tk.Frame(f, bg=CARD)
        row.pack(fill="x")
        var = tk.DoubleVar()
        minus = self._button(row, "−", None)
        minus.pack(side="left")
        scale = tk.Scale(row, variable=var, from_=lo, to=hi, orient="horizontal", resolution=1, showvalue=0,
                         length=260, bg=ACCENT, fg=TEXT, troughcolor=EDGE, highlightthickness=0, bd=0, width=12,
                         sliderlength=18, sliderrelief="flat", activebackground="#7dbcff")
        scale.pack(side="left", padx=6, fill="x", expand=True)
        plus = self._button(row, "+", None)
        plus.pack(side="left")
        ends = tk.Frame(f, bg=CARD)
        ends.pack(fill="x", padx=28)
        lo_label = tk.Label(ends, text=lo_text, bg=CARD, fg=DIM, font=(FONT, 8))
        lo_label.pack(side="left")
        hi_label = tk.Label(ends, text=hi_text, bg=CARD, fg=DIM, font=(FONT, 8))
        hi_label.pack(side="right")
        s = {"frame": f, "var": var, "scale": scale, "value": value, "unit": unit, "widgets": [minus, plus],
             "ends": (lo_label, lo_text, hi_label, hi_text)}
        def step(d):
            var.set(max(float(scale.cget("from")), min(float(scale.cget("to")), var.get() + d)))
            self._changed()
        minus.bind("<Button-1>", lambda e: step(-1))
        plus.bind("<Button-1>", lambda e: step(1))
        scale.configure(command=lambda _v: self._changed())
        return s

    # ---------- behaviour ----------
    def _select(self, key):
        self.view = key
        label = dict(cc.VIEWS)[key]
        for k, b in self.view_btns.items():
            b.configure(bg=ACCENT if k == key else CARD, fg="#0b0d10" if k == key else TEXT)
        self.view_title.configure(text=label)
        stock_fov = self.stock[key]["fov"]
        chase = "chase" in key
        self.view_note.configure(text=f"Stock field of view {stock_fov:g}°.")
        self.loading = True
        s = self.settings[key]
        self.sliders["fov"]["var"].set(stock_fov if s["fov"] is None else s["fov"])
        for _, axis, _, _, rng, chase_rng in ROWS:
            sl = self.sliders[axis]
            r = chase_rng if chase else rng
            sl["scale"].configure(from_=-r, to=r)
            lo_label, lo_text, hi_label, hi_text = sl["ends"]
            lo_label.configure(text=f"{lo_text} {r} cm")
            hi_label.configure(text=f"{hi_text} {r} cm")
            sl["var"].set(s[axis])
        self.loading = False
        self._show_values()

    def _show_values(self):
        for key, sl in self.sliders.items():
            v = sl["var"].get()
            if key == "fov":
                stock = self.stock[self.view]["fov"]
                sl["value"].configure(text=f"{v:g}°" + (" (stock)" if abs(v - stock) < 0.01 else ""))
            else:
                lo_text, hi_text = sl["ends"][1], sl["ends"][3]
                sl["value"].configure(text="stock" if v == 0 else
                                      f"{hi_text if v > 0 else lo_text} {abs(v):g} cm ({abs(v) / 2.54:.1f} in)")

    def _changed(self):
        if self.loading:
            return
        s = self.settings[self.view]
        fov = self.sliders["fov"]["var"].get()
        s["fov"] = None if abs(fov - self.stock[self.view]["fov"]) < 0.01 else fov
        for _, axis, *_ in ROWS:
            s[axis] = self.sliders[axis]["var"].get()
        self._show_values()
        if self.save_job:
            self.after_cancel(self.save_job)
        self.save_job = self.after(300, self._commit)

    def _commit(self):
        self.save_job = None
        save_settings(self.settings)
        self.worker.push(self.settings)

    def _reset_view(self):
        self.settings[self.view] = cc.blank()[self.view]
        self._select(self.view)
        self._commit()

    def _reset_all(self):
        self.settings = cc.blank()
        self._select(self.view)
        self._commit()

    def _poll(self):
        try:
            while True:
                _, color, text = self.msgs.get_nowait()
                self.dot.configure(fg=color)
                self.status.configure(text=text)
        except queue.Empty:
            pass
        self.after(150, self._poll)


if __name__ == "__main__":
    App().mainloop()
