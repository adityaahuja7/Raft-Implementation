import threading
import time

class TimerWithRemainingTime(threading.Timer):
    def __init__(self, interval, function, args=None, kwargs=None):
        super().__init__(interval, function, args, kwargs)
        self.start_time = time.time()

    def time_left(self):
        return max(0, self.interval - (time.time() - self.start_time))