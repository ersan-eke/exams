import time
from collections import defaultdict, deque


class RateLimiter:
    """Sliding window: at most `limit` calls per `window` seconds per client."""

    # shortcut: in-memory, per process (several workers each allow `limit`); move to Redis/DB when we run more than one.
    def __init__(self, limit: int = 30, window: float = 60.0):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.swept = 0.0

    def allow(self, client: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if now - self.swept >= self.window:  # forget clients whose window is empty, or the dict grows with every IP ever seen
            self.swept = now
            for k in [k for k, h in self.hits.items() if not h or h[-1] <= now - self.window]:
                del self.hits[k]
        q = self.hits[client]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


grade_limiter = RateLimiter()
ask_limiter = RateLimiter()
