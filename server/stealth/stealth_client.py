"""
Stealth HTTP Client
Dispatches requests with randomized fingerprint headers, human pacing,
anti-bot signature detection, and automated backoff retry using async HTTPX.
"""
import time
import datetime
import math
import asyncio
from typing import Dict, Any, Optional, Callable, List
from urllib.parse import urlparse
import httpx

from .fingerprints import get_random_profile
from .rate_limiter import AdaptiveRateLimiter


class StealthClient:
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        options = options or {}
        rate_limit_cfg = options.get("rateLimitConfig", {})
        self.rate_limiter = AdaptiveRateLimiter(
            min_delay_ms=rate_limit_cfg.get("minDelayMs", 800),
            max_delay_ms=rate_limit_cfg.get("maxDelayMs", 2500),
            tokens_per_interval=rate_limit_cfg.get("tokensPerInterval", 8),
            interval_ms=rate_limit_cfg.get("intervalMs", 10000),
        )
        self.cookie_jar: Dict[str, Dict[str, str]] = {}
        self.proxies: List[Dict[str, Any]] = options.get(
            "proxies",
            [
                {"id": "direct", "ip": "198.51.100.12", "region": "us-east-1 (residential)", "health": 100, "requests": 0},
                {"id": "proxy-res-1", "ip": "142.250.190.46", "region": "us-west-2 (residential)", "health": 100, "requests": 0},
                {"id": "proxy-res-2", "ip": "185.220.101.5", "region": "eu-central-1 (residential)", "health": 100, "requests": 0},
                {"id": "proxy-res-3", "ip": "103.245.222.133", "region": "ap-southeast-1 (residential)", "health": 100, "requests": 0},
            ],
        )
        self.current_proxy_index = 0

    def get_next_proxy(self) -> Dict[str, Any]:
        active_proxies = [p for p in self.proxies if p["health"] > 20]
        if not active_proxies:
            for p in self.proxies:
                p["health"] = 80
            return self.proxies[0]

        self.current_proxy_index = (self.current_proxy_index + 1) % len(active_proxies)
        selected = active_proxies[self.current_proxy_index]
        selected["requests"] += 1
        return selected

    def report_proxy_failure(self, proxy_id: str, penalty: int = 25) -> None:
        for p in self.proxies:
            if p["id"] == proxy_id:
                p["health"] = max(0, p["health"] - penalty)
                break

    def report_proxy_success(self, proxy_id: str) -> None:
        for p in self.proxies:
            if p["id"] == proxy_id and p["health"] < 100:
                p["health"] = min(100, p["health"] + 5)
                break

    def _format_cookies(self, url: str) -> str:
        try:
            hostname = urlparse(url).hostname or ""
            cookies = self.cookie_jar.get(hostname, {})
            return "; ".join([f"{k}={v}" for k, v in cookies.items()])
        except Exception:
            return ""

    def _store_cookies(self, url: str, headers: httpx.Headers) -> None:
        try:
            hostname = urlparse(url).hostname or ""
            set_cookie = headers.get("set-cookie")
            if not set_cookie:
                return

            current_cookies = self.cookie_jar.setdefault(hostname, {})
            parts = set_cookie.split(",")
            for part in parts:
                pair = part.split(";")[0]
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        current_cookies[k] = v
        except Exception:
            pass

    def detect_anti_bot_challenge(self, html: Optional[str], status: int) -> Optional[Dict[str, Any]]:
        """Inspect HTML response for bot detection challenge markers"""
        if not html or not isinstance(html, str):
            return None

        lower = html.lower()
        if status in (403, 429, 999):
            if "cloudflare" in lower and ("turnstile" in lower or "cf-browser-verification" in lower or "just a moment" in lower):
                return {"type": "CLOUDFLARE_CHALLENGE", "status": status, "message": "Cloudflare Turnstile/Under-Attack challenge encountered"}
            if "datadome" in lower or "geo.captcha-delivery.com" in lower:
                return {"type": "DATADOME_CAPTCHA", "status": status, "message": "DataDome device fingerprinting block"}
            if "perimeterx" in lower or "press & hold" in lower:
                return {"type": "PERIMETERX_BLOCK", "status": status, "message": "PerimeterX behavioral biometric block"}
            if "rate limit" in lower or "too many requests" in lower:
                return {"type": "RATE_LIMITED", "status": status, "message": "Strict IP rate-limiting enforced"}
            return {"type": "HTTP_FORBIDDEN", "status": status, "message": f"Access denied with status {status}"}

        if "enable javascript and cookies to continue" in lower or "cf-chl-bypass" in lower:
            return {"type": "JAVASCRIPT_REQUIRED", "status": status, "message": "JS execution fingerprint requirement"}

        return None

    async def fetch(
        self,
        url: str,
        options: Optional[Dict[str, Any]] = None,
        telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> Dict[str, Any]:
        """Performs an evasive stealth fetch with pacing, profile rotation, and retry"""
        options = options or {}
        max_retries = options.get("maxRetries", 1)
        attempt = 0

        while attempt <= max_retries:
            attempt += 1
            profile = options.get("profile") or get_random_profile()
            proxy = self.get_next_proxy()

            hostname = urlparse(url).hostname or "default"
            jitter_delay = await self.rate_limiter.acquire(hostname)

            request_headers = {
                "User-Agent": profile["userAgent"],
                **profile["headers"],
                **(options.get("headers") or {}),
            }

            cookie_header = self._format_cookies(url)
            if cookie_header:
                request_headers["Cookie"] = cookie_header

            start_time = time.time()

            if telemetry_callback:
                telemetry_callback(
                    {
                        "type": "REQUEST_START",
                        "url": url,
                        "attempt": attempt,
                        "profileName": profile["name"],
                        "proxy": proxy["id"],
                        "proxyRegion": proxy["region"],
                        "jitterDelay": jitter_delay,
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                )

            try:
                timeout_sec = (options.get("timeoutMs") or 8000) / 1000.0

                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=timeout_sec,
                    verify=False,  # Allow resilient scraping without cert hurdles
                ) as client:
                    response = await client.request(
                        method=options.get("method", "GET"),
                        url=url,
                        headers=request_headers,
                    )

                duration = int((time.time() - start_time) * 1000)
                self._store_cookies(url, response.headers)

                text = response.text
                challenge = self.detect_anti_bot_challenge(text, response.status_code)

                if challenge:
                    self.report_proxy_failure(proxy["id"], 30)
                    self.rate_limiter.report_rate_limit()

                    if telemetry_callback:
                        telemetry_callback(
                            {
                                "type": "CHALLENGE_DETECTED",
                                "url": url,
                                "challenge": challenge,
                                "status": response.status_code,
                                "attempt": attempt,
                                "duration": duration,
                            }
                        )

                    if attempt <= max_retries:
                        wait_sec = (1500 * math.pow(2, attempt)) / 1000.0
                        await asyncio.sleep(wait_sec)
                        continue

                    raise RuntimeError(f"Bot challenge tripped [{challenge['type']}]: {challenge['message']}")

                if not response.is_success:
                    if response.status_code in (500, 502, 503, 504, 429) and attempt <= max_retries:
                        self.report_proxy_failure(proxy["id"], 15)
                        wait_sec = (1000 * math.pow(2, attempt)) / 1000.0
                        await asyncio.sleep(wait_sec)
                        continue
                    raise RuntimeError(f"HTTP Request failed with status {response.status_code} {response.reason_phrase}")

                # Success
                self.report_proxy_success(proxy["id"])
                self.rate_limiter.report_success()

                if telemetry_callback:
                    telemetry_callback(
                        {
                            "type": "REQUEST_SUCCESS",
                            "url": url,
                            "status": response.status_code,
                            "duration": duration,
                            "bodyLength": len(text),
                            "attempt": attempt,
                            "proxy": proxy["id"],
                        }
                    )

                return {
                    "status": response.status_code,
                    "headers": dict(response.headers),
                    "data": text,
                    "duration": duration,
                    "profileUsed": profile["name"],
                    "proxyUsed": proxy["id"],
                }

            except Exception as err:
                self.report_proxy_failure(proxy["id"], 20)

                if attempt <= max_retries:
                    if telemetry_callback:
                        telemetry_callback(
                            {
                                "type": "REQUEST_RETRY",
                                "url": url,
                                "attempt": attempt,
                                "error": str(err),
                            }
                        )
                    await asyncio.sleep(1.0 * attempt)
                    continue

                if telemetry_callback:
                    telemetry_callback(
                        {
                            "type": "REQUEST_FAILURE",
                            "url": url,
                            "error": str(err),
                            "duration": int((time.time() - start_time) * 1000),
                        }
                    )
                raise err
