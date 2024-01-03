import logging
import select
import time
from threading import Event as TEvent
from typing import Literal, Sequence

from hhd.controller import (
    Axis,
    Button,
    Configuration,
    Event,
    KeyboardWrapper,
    Multiplexer,
    can_read,
)
from hhd.controller.base import Event
from hhd.controller.lib.common import AM, BM, CM
from hhd.controller.lib.hid import MAX_REPORT_SIZE
from hhd.controller.physical.evdev import B as EC
from hhd.controller.physical.evdev import GenericGamepadEvdev
from hhd.controller.physical.hidraw import EventCallback, GenericGamepadHidraw
from hhd.controller.physical.imu import CombinedImu, HrtimerTrigger
from hhd.plugins import Config, Context, Emitter, get_outputs

from .hid import rgb_callback

ERROR_DELAY = 1
SELECT_TIMEOUT = 1

logger = logging.getLogger(__name__)

ASUS_VID = 0x0B05
ASUS_KBD_PID = 0x1ABE
GAMEPAD_VID = 0x045E
GAMEPAD_PID = 0x028E

ASUS_KBD_MAP: Sequence[tuple[set[Button], Button]] = [
    ({"key_prog1"}, "share"),  # Armory button
    ({"key_f16"}, "mode"),  # Control center
]


ALLY_MAPPINGS: dict[str, tuple[Axis, str | None, float | None]] = {
    "accel_x": ("accel_z", "accel", 3),
    "accel_y": ("accel_x", "accel", 3),
    "accel_z": ("accel_y", "accel", 3),
    "anglvel_x": ("gyro_z", "anglvel", None),
    "anglvel_y": ("gyro_x", "anglvel", None),
    "anglvel_z": ("gyro_y", "anglvel", None),
    "timestamp": ("gyro_ts", "anglvel", None),
}

MODE_DELAY = 0.3


class AllyHidraw(GenericGamepadHidraw):
    def open(self) -> Sequence[int]:
        self.queue: list[tuple[Event, float]] = []
        return super().open()

    def produce(self, fds: Sequence[int]) -> Sequence[Event]:
        # If we can not read return
        if not self.fd or not self.dev:
            return []

        # Process events
        curr = time.perf_counter()
        out: Sequence[Event] = []

        # Remove events that have been queued
        while len(self.queue):
            ev, ofs = self.queue[0]
            if ofs + MODE_DELAY < curr:
                out.append(ev)
                out.pop(0)
            else:
                break

        # Read new events
        while can_read(self.fd):
            rep = self.dev.read(self.report_size)
            logger.warning(f"Received the following report (debug):\n{rep.hex()}")
            if rep[0] != 0x5a:
                continue

            match rep[1]:
                case 0xA6:
                    # action = "left"
                    out.append({"type": "button", "code": "mode", "value": True})
                    self.queue.append(
                        ({"type": "button", "code": "mode", "value": False}, curr)
                    )
                case 0x38:
                    # action = "right"
                    out.append({"type": "button", "code": "share", "value": True})
                    self.queue.append(
                        ({"type": "button", "code": "share", "value": False}, curr)
                    )
                case 0xA7:
                    # action = "right_hold"
                    pass  # TODO: mode switch
                case 0xA8:
                    # action = "right_hold_release"
                    pass  # TODO: mode switch

        return []


def plugin_run(conf: Config, emit: Emitter, context: Context, should_exit: TEvent):
    while not should_exit.is_set():
        try:
            logger.info("Launching emulated controller.")
            controller_loop(conf, should_exit)
        except Exception as e:
            logger.error(f"Received the following error:\n{e}")
            logger.error(
                f"Assuming controllers disconnected, restarting after {ERROR_DELAY}s."
            )
            # Raise exception
            if conf.get("debug", False):
                raise e
            time.sleep(ERROR_DELAY)


def controller_loop(conf: Config, should_exit: TEvent):
    debug = conf.get("debug", False)

    # Output
    d_producers, d_outs, d_params = get_outputs(
        conf["controller_mode"], None, conf["imu"].to(bool)
    )

    # Imu
    d_imu = CombinedImu(conf["imu_hz"].to(int))
    d_timer = HrtimerTrigger(conf["imu_hz"].to(int))

    # Inputs
    d_xinput = GenericGamepadEvdev(
        vid=[GAMEPAD_VID],
        pid=[GAMEPAD_PID],
        # name=["Generic X-Box pad"],
        capabilities={EC("EV_KEY"): [EC("BTN_A")]},
        required=True,
        hide=True,
    )

    # Vendor
    d_vend = AllyHidraw(
        vid=[ASUS_VID],
        pid=[ASUS_KBD_PID],
        usage_page=[0xFF31],
        usage=[0x0080],
        required=True,
        callback=rgb_callback,
    )

    # Grab shortcut keyboards
    d_kbd_1 = KeyboardWrapper(
        GenericGamepadEvdev(
            vid=[ASUS_VID],
            pid=[ASUS_KBD_PID],
            capabilities={EC("EV_KEY"): [EC("KEY_PROG1")]},
            required=True,
        ),
        ASUS_KBD_MAP,
    )

    multiplexer = Multiplexer(
        trigger="analog_to_discrete",
        dpad="analog_to_discrete",
        share_to_qam=conf["share_to_qam"].to(bool),
    )

    REPORT_FREQ_MIN = 25
    REPORT_FREQ_MAX = 400

    if conf["imu"].to(bool):
        REPORT_FREQ_MAX = max(REPORT_FREQ_MAX, conf["imu_hz"].to(float))

    REPORT_DELAY_MAX = 1 / REPORT_FREQ_MIN
    REPORT_DELAY_MIN = 1 / REPORT_FREQ_MAX

    fds = []
    devs = []
    fd_to_dev = {}

    def prepare(m):
        devs.append(m)
        fs = m.open()
        fds.extend(fs)
        for f in fs:
            fd_to_dev[f] = m

    try:
        d_vend.open()
        prepare(d_xinput)
        if conf.get("imu", False):
            d_timer.open()
            prepare(d_imu)
        # prepare(d_kbd_1)
        for d in d_producers:
            prepare(d)

        logger.info("Emulated controller launched, have fun!")
        while not should_exit.is_set():
            start = time.perf_counter()
            # Add timeout to call consumers a minimum amount of times per second
            r, _, _ = select.select(fds, [], [], REPORT_DELAY_MAX)
            evs = []
            to_run = set()
            for f in r:
                to_run.add(id(fd_to_dev[f]))

            for d in devs:
                if id(d) in to_run:
                    evs.extend(d.produce(r))
            evs.extend(d_vend.produce(r))

            evs = multiplexer.process(evs)
            if evs:
                if debug:
                    logger.info(evs)

                d_vend.consume(evs)
                d_xinput.consume(evs)

            for d in d_outs:
                d.consume(evs)

            # If unbounded, the total number of events per second is the sum of all
            # events generated by the producers.
            # For Legion go, that would be 100 + 100 + 500 + 30 = 730
            # Since the controllers of the legion go only update at 500hz, this is
            # wasteful.
            # By setting a target refresh rate for the report and sleeping at the
            # end, we ensure that even if multiple fds become ready close to each other
            # they are combined to the same report, limiting resource use.
            # Ideally, this rate is smaller than the report rate of the hardware controller
            # to ensure there is always a report from that ready during refresh
            t = time.perf_counter()
            elapsed = t - start
            if elapsed < REPORT_DELAY_MIN:
                time.sleep(REPORT_DELAY_MIN - elapsed)

    except KeyboardInterrupt:
        raise
    finally:
        d_vend.close(True)
        d_timer.close()
        for d in reversed(devs):
            d.close(True)
