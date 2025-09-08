import threading
import time

class SimpleCache:
    def __init__(self, default_ttl=600):
        self._cache = {}
        self._lock = threading.Lock()
        self.default_ttl = default_ttl

    def set(self, key, value, ttl=None):
        expire_at = time.time() + (ttl or self.default_ttl)
        with self._lock:
            self._cache[key] = (value, expire_at)

    def get(self, key):
        with self._lock:
            item = self._cache.get(key)
            if not item:
                return None
            value, expire_at = item
            if time.time() > expire_at:
                del self._cache[key]
                return None
            return value

    def invalidate(self, key):
        with self._lock:
            if key in self._cache:
                del self._cache[key]

    def clear(self):
        with self._lock:
            self._cache.clear()

# Instância global para uso na aplicação
cache = SimpleCache()
