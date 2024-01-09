from threading import Event, Thread
from typing import Any, Sequence

from hhd.plugins import (
    Config,
    Context,
    Emitter,
    HHDPlugin,
    load_relative_yaml,
    get_outputs_config,
)
from hhd.plugins.settings import HHDSettings


class GpdGen3ControllersPlugin(HHDPlugin):
    name = "gpd_gen_3_controllers"
    priority = 18
    log = "gpd_gen_3"

    def __init__(self) -> None:
        self.t = None
        self.should_exit = None
        self.updated = Event()
        self.started = False
        self.t = None

    def open(
        self,
        emit: Emitter,
        context: Context,
    ):
        self.emit = emit
        self.context = context
        self.prev = None

    def settings(self) -> HHDSettings:
        base = {"controllers": {"gpd_gen_3": load_relative_yaml("controllers.yml")}}
        base["controllers"]["gpd_gen_3"]["children"]["controller_mode"].update(
            get_outputs_config(can_disable=False)
        )
        return base

    def update(self, conf: Config):
        new_conf = conf["controllers.gpd_gen_3"]
        if new_conf == self.prev:
            return
        if self.prev is None:
            self.prev = new_conf
        else:
            self.prev.update(new_conf.conf)

        self.updated.set()
        self.start(self.prev)

    def start(self, conf):
        from .base import plugin_run

        if self.started:
            return
        self.started = True

        self.close()
        self.should_exit = Event()
        self.t = Thread(
            target=plugin_run,
            args=(conf, self.emit, self.context, self.should_exit, self.updated),
        )
        self.t.start()

    def close(self):
        if not self.should_exit or not self.t:
            return
        self.should_exit.set()
        self.t.join()
        self.should_exit = None
        self.t = None


def autodetect(existing: Sequence[HHDPlugin]) -> Sequence[HHDPlugin]:
    if len(existing):
        return existing

    # Match just product number, should be enough for now
    with open("/sys/devices/virtual/dmi/id/product_name") as f:
        if not f.read().strip() == "G1618-04":
            return []

    return [GpdGen3ControllersPlugin()]
