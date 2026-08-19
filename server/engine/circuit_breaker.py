"""
Domain-Level Circuit Breaker

Prevents cascading failures and IP blacklisting by cutting off traffic
to a target endpoint as soon as elevated 403s, 429s, or latency spikes occur.
Automatically recovers via HALF_OPEN canary probes.
"""
import time
import math
from typing import Dict, Any, Optional


class CircuitState:
    CLOSED = "CLOSED"        # Normal operation
    OPEN = "OPEN"            # Tripped / In Quarantine
    HALF_OPEN = "HALF_OPEN"  # Canary probing


class CircuitBreaker:
    def __init__(self, options: Optional[Dict[str, Any]] = None):
        options = options or {}
        self.failure_threshold = options.get("failureThreshold", 3)
        self.recovery_time_ms = options.get("recoveryTimeMs", 15000)
        self.domains: Dict[str, Dict[str, Any]] = {}

    def _get_record(self, domain: str) -> Dict[str, Any]:
        if domain not in self.domains:
            self.domains[domain] = {
                "state": CircuitState.CLOSED,
                "failureCount": 0,
                "successCount": 0,
                "lastFailureTime": 0,
                "trippedReason": None,
                "totalRequests": 0,
                "successfulRequests": 0,
            }
        return self.domains[domain]

    def check_state(self, domain: str) -> Dict[str, Any]:
        record = self._get_record(domain)
        now = time.time() * 1000

        if record["state"] == CircuitState.OPEN:
            if now - record["lastFailureTime"] > self.recovery_time_ms:
                record["state"] = CircuitState.HALF_OPEN
                record["trippedReason"] = "Canary recovery probe in progress"
            else:
                remaining_sec = math.ceil((self.recovery_time_ms - (now - record["lastFailureTime"])) / 1000)
                return {
                    "allowed": False,
                    "state": CircuitState.OPEN,
                    "reason": f"Circuit OPEN for {domain}: {record['trippedReason']} (Quarantined for {remaining_sec}s)",
                }

        return {"allowed": True, "state": record["state"]}

    def report_success(self, domain: str) -> None:
        record = self._get_record(domain)
        record["totalRequests"] += 1
        record["successfulRequests"] += 1

        if record["state"] == CircuitState.HALF_OPEN:
            record["successCount"] += 1
            if record["successCount"] >= 2:
                record["state"] = CircuitState.CLOSED
                record["failureCount"] = 0
                record["successCount"] = 0
                record["trippedReason"] = None
        else:
            record["failureCount"] = max(0, record["failureCount"] - 1)

    def report_failure(self, domain: str, reason: str = "Unknown error") -> None:
        record = self._get_record(domain)
        record["totalRequests"] += 1
        record["failureCount"] += 1
        record["lastFailureTime"] = time.time() * 1000

        if record["failureCount"] >= self.failure_threshold or record["state"] == CircuitState.HALF_OPEN:
            record["state"] = CircuitState.OPEN
            record["trippedReason"] = reason

    def force_trip(self, domain: str, reason: str) -> None:
        record = self._get_record(domain)
        record["state"] = CircuitState.OPEN
        record["lastFailureTime"] = time.time() * 1000
        record["trippedReason"] = reason

    def get_metrics(self) -> Dict[str, Any]:
        result = {}
        for domain, record in self.domains.items():
            tot = record["totalRequests"]
            succ = record["successfulRequests"]
            rate = f"{((succ / tot) * 100):.1f}%" if tot > 0 else "100%"
            result[domain] = {
                "state": record["state"],
                "failureCount": record["failureCount"],
                "totalRequests": tot,
                "successRate": rate,
                "trippedReason": record["trippedReason"],
            }
        return result
