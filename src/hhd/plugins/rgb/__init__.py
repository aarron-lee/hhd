import logging
import time
from typing import Sequence, cast, Literal

from hhd.controller import Event, RgbMode
from hhd.plugins import Config, Context, HHDPlugin, load_relative_yaml
from hhd.utils import get_distro_color

logger = logging.getLogger(__name__)

RGB_SET_TIMES = 3
RGB_SET_INTERVAL = 7
RGB_MIN_INTERVAL = 0.05


def hsb_to_rgb(h: int, s: int | float, v: int | float):
    # https://www.rapidtables.com/convert/color/hsv-to-rgb.html
    if h >= 360:
        h = 359
    s = s / 100
    v = v / 100

    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        rgb = (c, x, 0)
    elif h < 120:
        rgb = (x, c, 0)
    elif h < 180:
        rgb = (0, c, x)
    elif h < 240:
        rgb = (0, x, c)
    elif h < 300:
        rgb = (x, 0, c)
    else:
        rgb = (c, 0, x)

    return [int((v + m) * 255) for v in rgb]


class RgbPlugin(HHDPlugin):
    def __init__(self) -> None:
        self.name = f"controller_rgb"
        self.priority = 15
        self.log = "LEDS"

        self.modes = None
        self.controller = False
        self.loaded = False
        self.enabled = False
        self.last_set = 0

        self.init_count = 0
        self.init_last = 0
        self.init = True
        self.uniq = None

        self.prev = None

    def open(
        self,
        emit,
        context: Context,
    ):
        self.started = False
        self.emit = emit

    def settings(self):
        if not self.modes:
            self.loaded = False
            return {}
        self.loaded = True

        # If RGB support is disabled
        # return enable option only
        base = load_relative_yaml("settings.yml")
        if not self.enabled:
            del base["rgb"]
            return base

        if self.controller:
            # Remove RGB settings because the controller has control
            del base["rgb"]["handheld"]["children"]["mode"]
        else:
            # Remove disclaimer
            del base["rgb"]["handheld"]["children"]["controller"]
            modes = load_relative_yaml("modes.yml")
            capabilities = load_relative_yaml("capabilities.yml")

            # Set a sane default color
            dc = get_distro_color()

            supported = {}
            for mode, caps in self.modes.items():
                if mode in modes:
                    m = modes[mode]
                    m["children"] = {}
                    for cap in caps:
                        m["children"].update(capabilities[cap])
                        if cap == "color":
                            m["children"]["hue"]["default"] = dc
                    supported[mode] = m

            # Add supported modes
            base["rgb"]["handheld"]["children"]["mode"]["modes"] = supported

            # Set a sane default mode
            for default in ("solid", "pulse", "disabled"):
                if default in supported:
                    base["rgb"]["handheld"]["children"]["mode"]["default"] = default
                    break
            else:
                # fallback to any supported mode to have persistence in the mode
                base["rgb"]["handheld"]["children"]["mode"]["default"] = next(
                    iter(supported)
                )
        return base

    def update(self, conf: Config):
        cap = self.emit.get_capabilities()
        if not cap:
            if self.modes:
                self.modes = None
                self.emit({"type": "settings"})
            return

        # Check controller id and force setting the leds if it changed.
        # This will reset the led color after suspend or after exitting
        # dualsense emulation.
        uniq = next(iter(cap))
        ccap = cap[uniq]
        if uniq != self.uniq:
            self.prev = None
            self.uniq = uniq

        rgb = ccap["rgb"]
        refresh_settings = False
        if rgb:
            # Refresh on initial load
            if not self.modes:
                refresh_settings = True

            # Refresh if controller takes control of the LEDs
            new_controller = rgb["controller"]
            if self.controller != new_controller:
                refresh_settings = True

            self.controller = new_controller
            self.modes = rgb["modes"]

        if self.loaded:
            new_enabled = conf["hhd"]["settings"]["rgb"].to(bool)
            if new_enabled != self.enabled:
                refresh_settings = True
                self.enabled = new_enabled

        if refresh_settings:
            self.init_count = 0
            self.init_last = 0
            self.emit({"type": "settings"})
            return

        # All checks were ran and settings were updated
        # if the controller has control of the LEDs
        # or they are not enabled, exit.
        if not self.enabled or self.controller:
            return

        rgb_conf = conf["rgb"]["handheld"]["mode"]
        if self.prev and self.prev != rgb_conf:
            self.init = False
        elif self.init:
            # Initialize by setting the LEDs 3 times
            # to avoid early boot having it not set
            if self.init_count >= RGB_SET_TIMES:
                self.init = False
                return

            # Wait inbetween setting the LEDS
            curr = time.perf_counter()
            if curr - self.init_last < RGB_SET_INTERVAL:
                return

            self.init_count += 1
            self.init_last = curr
            logger.info(
                f"Initializing RGB (repeat {self.init_count}/{RGB_SET_TIMES}, interval: {RGB_SET_INTERVAL})"
            )
        elif self.prev and self.prev == rgb_conf:
            return

        # Avoid setting the LEDs too fast.
        curr = time.perf_counter()
        if curr - self.last_set < RGB_MIN_INTERVAL:
            return
        self.last_set = curr

        self.prev = rgb_conf.copy()

        # Get event info
        mode = rgb_conf["mode"].to(str)
        if mode in rgb_conf:
            info = cast(dict, rgb_conf[mode].conf)
        else:
            info = {}
        ev: Event | None = None
        if not self.modes or mode not in self.modes:
            return

        brightness = 1
        level = "high"
        speed = 1
        red = 0
        green = 0
        blue = 0

        log = f"Setting RGB to mode '{mode}'"
        for cap in self.modes[cast(RgbMode, mode)]:
            match cap:
                case "color":
                    red, green, blue = hsb_to_rgb(
                        info["hue"],
                        info["saturation"],
                        info["brightness"],
                    )
                    log += f" with color: {red:3d}, {green:3d}, {blue:3d}"
                case "brightness":
                    log += f", brightness: {info['brightness']}"
                    brightness = info["brightness"] / 100
                case "speed":
                    log += f", speed: {info['speed']}"
                    speed = info["speed"] / 100
                case "level":
                    log += f", level: {info['level']}"
                    level = cast(Literal["low", "medium", "high"], info["level"])
        log += "."
        logger.info(log)

        ev = {
            "type": "led",
            "code": "main",
            "mode": cast(RgbMode, mode),
            "brightness": brightness,
            "level": level,
            "speed": speed,
            "red": red,
            "green": green,
            "blue": blue,
        }
        self.emit.inject(ev)


def autodetect(existing: Sequence[HHDPlugin]) -> Sequence[HHDPlugin]:
    if len(existing):
        return existing

    return [RgbPlugin()]