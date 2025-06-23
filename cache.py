class Cache:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def clear(self):
        self.store.clear()

    def __contains__(self, key):
        return key in self.store