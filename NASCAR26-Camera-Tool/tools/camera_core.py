"""Driving camera FOV / position edits, in the running game's memory only (used by camera_tool.py). Each series' UChassisDataAsset holds its cameras in Cameras (+0x230, FChassisPhysCamera):
  in_car0/in_car1/hood/alt_hood/bumper  FChassisFixedOnCarCamera at +0x00/+0x70/+0xE0/+0x150/+0x1C0
                                        (forward_camera: Location +0x00, field_of_view +0x20; look-back left alone)
  new_chase/alt_new_chase               FChassisNewChaseCamera at +0x2A0/+0x2F0 (cam: Location +0x00, fov +0x20)
Location is car-relative in cm: X forward, Y right, Z up. Those 7 are the game's 7 driving views. Left alone: the
old-style chase cams near_chase/alt_chase/rear_chase (FChassisPhysChaseCamera, not used by the game), the on-car TV
(replay) cameras and the mirror.
Stock + check values per camera: sheets/camera_stock.json (from the FModel chassis export). A camera is only written
when its check values match stock, or what this module last wrote in this game session (kept in
%TEMP%\\nascar26_camera_views.json, keyed by game process), so a moved offset can't hit other data.
Changes apply to cars loaded afterwards (restart the race). Closing the game restores everything.
"""
import json, pathlib, struct, sys, tempfile
import ue

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEET = (pathlib.Path(sys._MEIPASS) / "camera_stock.json") if getattr(sys, "frozen", False) \
    else ROOT / "sheets" / "camera_stock.json"
STATE = pathlib.Path(tempfile.gettempdir()) / "nascar26_camera_views.json"
CAMERAS = 0x230
SERIES = {"ARCA": "ARCA", "Cup": "Cup", "Xfinity": "O'Reilly", "Truck": "Trucks"}
# (key in camera_stock.json, label)
VIEWS = [
    ("in_car0", "Cockpit"),
    ("in_car1", "Cockpit 2"),
    ("hood", "Hood"),
    ("alt_hood", "Roof"),
    ("bumper", "Bumper"),
    ("new_chase", "Chase"),
    ("alt_new_chase", "Far chase"),
]
VIEW_KEYS = [v[0] for v in VIEWS]
AXES = ("forward", "right", "up")


def load_stock():
    """{chassis asset name: {view: row}} for the driving views of the playable series."""
    raw = json.loads(SHEET.read_text(encoding="utf-8-sig"))
    return {name: {r["view"]: r for r in rows if r["view"] in VIEW_KEYS} for name, rows in raw.items()
            if name.split("_", 1)[1] in SERIES}


def blank():
    """Settings with everything stock: {view: {"fov": deg or None, "forward"/"right"/"up": cm}}."""
    return {k: {"fov": None, "forward": 0.0, "right": 0.0, "up": 0.0} for k in VIEW_KEYS}


class Unsupported(Exception):
    """The running game doesn't look like the version this was made for."""


def close(a, b):
    return all(abs(x - y) <= 0.01 for x, y in zip(a, b))


class Cameras:
    def __init__(self):
        self.stock = load_stock()
        self.g = None
        self.pid = None
        self.chassis = {}

    def connect(self):
        """True once attached to a running game with its chassis data loaded."""
        found = ue.find_game()
        if not found:
            self.disconnect()
            return False
        if self.g and self.pid == found[0]:
            return True
        self.disconnect()
        try:
            g = ue.Game(*found, write=True)
        except Exception:
            return False   # no access yet (still starting)
        try:
            g.sanity_check_names()
            chassis = g.find_by_class(["ChassisDataAsset"])["ChassisDataAsset"]
        except ue.GameNotReady:
            g.close()
            return False
        except Exception as e:
            g.close()
            raise Unsupported(str(e))
        chassis = {n: o for n, o in chassis.items() if n in self.stock}
        if len(chassis) < len(self.stock):
            g.close()
            return False
        self.g, self.pid, self.chassis = g, found[0], chassis
        return True

    def disconnect(self):
        if self.g:
            try:
                self.g.close()
            except Exception:
                pass
        self.g, self.pid, self.chassis = None, None, {}

    def _state(self):
        try:
            s = json.loads(STATE.read_text(encoding="utf-8"))
            return s["cams"] if s.get("pid") == self.pid else {}
        except (OSError, ValueError, KeyError):
            return {}

    def apply(self, settings):
        """Write the settings for every series. -> (cameras written, [problems])."""
        state, written, problems = self._state(), 0, []
        for name, rows in self.stock.items():
            obj = self.chassis.get(name)
            series = SERIES[name.split("_", 1)[1]]
            if not obj:
                continue
            for key, label in VIEWS:
                row, want = rows.get(key), settings.get(key)
                if not row or not want:
                    continue
                skey = f"{name}/{key}"
                try:
                    base = obj + CAMERAS + row["camera"]
                    got = struct.unpack("<3f", self.g.read(base, 12))
                    last = state.get(skey, {}).get("check")
                    if not close(got, row["check"]) and not (last and close(got, last)):
                        raise Unsupported("camera data looks unexpected")
                    fov = row["fov"] if want.get("fov") is None else want["fov"]
                    self.g.write(base + 0x20, struct.pack("<f", fov))
                    pos = [s + want.get(a, 0.0) for s, a in zip(row["check"], AXES)]
                    self.g.write(base, struct.pack("<3f", *pos))
                    state[skey] = {"check": pos}
                    written += 1
                except Exception as e:
                    problems.append(f"{series} {label}: {e}")
        STATE.write_text(json.dumps({"pid": self.pid, "cams": state}), encoding="utf-8")
        return written, problems
