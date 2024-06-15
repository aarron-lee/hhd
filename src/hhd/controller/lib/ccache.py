from threading import Condition, Thread, Event
import time

CACHE_TIMEOUT = 10
UPDATE_FREQ = 25
UPDATE_T = 1 / UPDATE_FREQ


class ControllerCache:
    def __init__(self) -> None:
        self._t = None
        self._cond = Condition()
        self._cached = None
        self._should_exit = Event()

    def _close_cached(self):
        with self._cond:
            start = time.perf_counter()
            curr = time.perf_counter()
            while curr - start < CACHE_TIMEOUT and not self._should_exit.is_set():
                self._cond.wait(UPDATE_T)
                next = time.perf_counter()
                if self._cached:
                    # Send fake events to keep everyone happy
                    # Both steam and kernel
                    self._cached.produce([self._cached.fd])
                    # Bridge timestamps to prevent jump after the error
                    # when disconnecting and reconnecting the controller
                    # provided the imu timestamp does not break after reloading
                    # Use .95 to prevent racing ahead of the IMU ts
                    if hasattr(self._cached, "last_imu_ts"):
                        ctime = getattr(self._cached, "last_imu_ts") + int(
                            (next - curr) * 0.95 * 1e9
                        )
                    else:
                        ctime = int(next * 1e9)

                    self._cached.consume(
                        [
                            {"type": "axis", "code": "left_imu_ts", "value": ctime},
                            {"type": "axis", "code": "right_imu_ts", "value": ctime},
                            {"type": "axis", "code": "imu_ts", "value": ctime},
                        ]
                    )
                else:
                    # Exit if cached became null during sleep
                    break
                curr = next
            if self._cached:
                self._cached.close(True)
                self._cached = None

    def add(self, c):
        tmp = None
        with self._cond:
            if self._t:
                self._should_exit.set()
                self._cond.notify_all()
                tmp = self._t
                self._t = None
        if tmp:
            tmp.join()

        with self._cond:
            self._cached = c
            self._should_exit.clear()
            self._t = Thread(target=self._close_cached)
            self._t.start()

    def get(self):
        with self._cond:
            tmp = self._cached
            self._cached = None
            self._should_exit.set()
            self._cond.notify_all()
            tmp2 = self._t
            self._t = None
        if tmp2:
            tmp2.join()
        return tmp

    def close(self):
        with self._cond:
            if self._cached:
                self._cached.close(True)
                self._cached = None
            self._should_exit.set()
            self._cond.notify_all()