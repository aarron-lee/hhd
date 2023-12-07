from hhd.controller import Button, Axis
from hhd.controller.physical.evdev import to_map, B
from ...controller.physical.hidraw import AM, BM

LGO_TOUCHPAD_BUTTON_MAP: dict[int, Button] = to_map(
    {
        "touchpad_touch": [B("BTN_TOOL_FINGER")],  # also BTN_TOUCH
        "touchpad_click": [B("BTN_TOOL_DOUBLETAP")],
    }
)

LGO_TOUCHPAD_AXIS_MAP: dict[int, Axis] = to_map(
    {
        "touchpad_x": [B("ABS_X")],  # also ABS_MT_POSITION_X
        "touchpad_y": [B("ABS_Y")],  # also ABS_MT_POSITION_Y
    }
)

LGO_RAW_INTERFACE_BTN_MAP: dict[int | None, dict[Button, BM]] = {
    0x04: {
        # Misc
        "mode": BM((18 << 3)),
        "share": BM((18 << 3) + 1),
        # Sticks
        "ls": BM((18 << 3) + 2),
        "rs": BM((18 << 3) + 3),
        # D-PAD
        "dpad_up": BM((18 << 3) + 4),
        "dpad_down": BM((18 << 3) + 5),
        "dpad_left": BM((18 << 3) + 6),
        "dpad_right": BM((18 << 3) + 7),
        # Thumbpad
        "a": BM((19 << 3) + 0),
        "b": BM((19 << 3) + 1),
        "x": BM((19 << 3) + 2),
        "y": BM((19 << 3) + 3),
        # Bumpers
        "lb": BM((19 << 3) + 4),
        "lt": BM((19 << 3) + 5),
        "rb": BM((19 << 3) + 6),
        "rt": BM((19 << 3) + 7),
        # Back buttons
        "extra_l1": BM((20 << 3)),
        "extra_l2": BM((20 << 3) + 1),
        "extra_r1": BM((20 << 3) + 2),
        "extra_r2": BM((20 << 3) + 5),
        "extra_r3": BM((20 << 3) + 4),
        # Select
        "start": BM((20 << 3) + 7),
        "select": BM((20 << 3) + 6),
        # Mouse
        "btn_middle": BM((21 << 3)),
    }
}


LGO_RAW_INTERFACE_AXIS_MAP: dict[int | None, dict[Axis, AM]] = {
    0x04: {
        "ls_x": AM(14 << 3, "m8"),
        "ls_y": AM(15 << 3, "m8"),
        "rs_x": AM(16 << 3, "m8"),
        "rs_y": AM(17 << 3, "m8"),
        "lt": AM(22 << 3, "u8"),
        "rt": AM(23 << 3, "u8"),
        # "mouse_wheel": AM(25 << 3, "m8", scale=1), # TODO: Fix weird behavior
        "touchpad_x": AM(26 << 3, "u16"),
        "touchpad_y": AM(28 << 3, "u16"),
        "left_gyro_x": AM(30 << 3, "m8"),
        "left_gyro_y": AM(31 << 3, "m8"),
        "right_gyro_x": AM(32 << 3, "m8"),
        "right_gyro_y": AM(33 << 3, "m8"),
    }
}
