import threading
import time

class LeaseTimer(threading.Timer):
    def __init__(self, interval, function, args=None, kwargs=None):
        super().__init__(interval, function, args, kwargs)
        self.start_time = time.time()

    def time_left(self):
        return max(0, self.interval - (time.time() - self.start_time))

def print_hello():
    print("Hello, world!")

# Create a LeaseTimer object
lease_timer = LeaseTimer(6, print_hello)

# # Start the timer
lease_timer.start()

# Wait for a while
time.sleep(3)

# Check the time left
print("Time left:", lease_timer.time_left())

# Wait for the remaining time
time.sleep(8)
