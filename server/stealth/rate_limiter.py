"""
Adaptive Jittered Token Bucket Rate Limiter

Prevents mechanical periodicity detection by anti-scraping systems.
Uses Poisson/Gaussian-distributed random jitter delays and respects
dynamic server backoff responses (Retry-After headers or 429 warnings).
"""
import time
import math
import random
import asyncio
from typing import Dict, Any, Optional


class AdaptiveRateLimiter:
    def __init__(
        self,
        min_delay_ms: int = 1200,
        max_delay_ms: int = 3500,
        tokens_per_interval: int = 5,
        interval_ms: int = 10000,
    ):
        self.min_delay_ms = min_delay_ms
        self.max_delay_ms = max_delay_ms
        self.tokens_per_interval = tokens_per_interval
        self.interval_ms = interval_ms
        self.tokens = tokens_per_interval
        self.last_refill = time.time() * 1000
        self.consecutive_failures = 0
        self.penalized_until = 0.0

    def _refill(self) -> None:
        now = time.time() * 1000
        elapsed = now - self.last_refill
        if elapsed > self.interval_ms:
            added_tokens = int(elapsed // self.interval_ms) * self.tokens_per_interval
            self.tokens = min(self.tokens_per_interval, self.tokens + added_tokens)
            self.last_refill = now

    def calculate_jitter(self, custom_min: Optional[int] = None, custom_max: Optional[int] = None) -> int:
        min_val = custom_min if custom_min is not None else self.min_delay_ms
        max_val = custom_max if custom_max is not None else self.max_delay_ms

        # Box-Muller transform for normal distribution around center
        u1 = random.random() or 0.0001
        u2 = random.random() or 0.0001
        rand_std_normal = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

        mean = (min_val + max_val) / 2.0
        std_dev = (max_val - min_val) / 6.0
        jitter = int(round(mean + rand_std_normal * std_dev))

        if jitter < min_val:
            jitter = min_val
        if jitter > max_val:
            jitter = max_val

        # Apply failure backoff multiplier if recent 429/403 occurred
        if self.consecutive_failures > 0:
            backoff_multiplier = math.pow(1.8, min(self.consecutive_failures, 4))
            jitter = int(round(jitter * backoff_multiplier))

        return jitter

    async def acquire(self, domain: str = "default") -> int:
        now = time.time() * 1000
        if self.penalized_until > now:
            wait_time = min(2000.0, self.penalized_until - now)
            await asyncio.sleep(wait_time / 1000.0)

        self._refill()
        delay = self.calculate_jitter()
        await asyncio.sleep(min(delay, 1200) / 1000.0)
        self.tokens = max(0, self.tokens - 1)
        return delay

    def report_success(self) -> None:
        self.consecutive_failures = max(0, self.consecutive_failures - 1)

    def report_rate_limit(self, retry_after_seconds: Optional[int] = None) -> float:
        self.consecutive_failures += 1
        if retry_after_seconds:
            backoff_ms = retry_after_seconds * 1000.0
        else:
            backoff_ms = min(10000.0, 1500.0 * math.pow(1.5, self.consecutive_failures))

        self.penalized_until = (time.time() * 1000) + backoff_ms
        return backoff_ms

    def get_status(self) -> Dict[str, Any]:
        self._refill()
        now = time.time() * 1000
        is_throttled = self.penalized_until > now
        return {
            "tokensRemaining": self.tokens,
            "maxTokens": self.tokens_per_interval,
            "consecutiveFailures": self.consecutive_failures,
            "isThrottled": is_throttled,
            "throttledRemainingMs": max(0, int(self.penalized_until - now)),
        }
