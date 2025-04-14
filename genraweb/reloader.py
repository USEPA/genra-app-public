"""Wrapper to reload a resource periodically"""
import time


class Reloader:
    """Wrapper to reload a resource periodically"""

    def __init__(self, seconds=6):
        self.__seconds = seconds
        # Could lazy load, but don't, so we don't wait 10 min. to find DB can't connect
        self.__load_time = 0  # epoch time zero
        self.__reload()

    def _get_resource(self):
        """Override this to define resource, can't make this __private."""
        # demo implementation
        return dict(now=time.time())

    def __reload(self):
        """Reload if needed."""
        if time.time() - self.__load_time >= self.__seconds:
            self.__resource = self._get_resource()
            self.__load_time = time.time()

    def __getattr__(self, attr):
        """Return resource attribute, reloading if expired"""
        self.__reload()
        return getattr(self.__resource, attr)

    def __getitem__(self, key):
        """Return resource item, reloading if expired"""
        self.__reload()
        return self.__resource[key]


if __name__ == "__main__":
    r = Reloader()
    for i in range(20):
        print(r["now"])
        time.sleep(2)
