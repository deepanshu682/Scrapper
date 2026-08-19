"""
Ingestion Orchestrator
Coordinates queue execution, stealth client dispatch, circuit breakers,
telemetry broadcasts to SSE subscribers, and multi-tier schema recovery.
"""
import time
import random
import string
import datetime
from urllib.parse import urlparse
from typing import Dict, Any, List, Optional, Set
import asyncio

from ..stealth.stealth_client import StealthClient
from .circuit_breaker import CircuitBreaker
from .sources.remoteok import remoteOkSource
from .sources.jobicy import jobicySource
from .sources.hackernews import hackerNewsSource
from .sources.linkedin import linkedInSource
from .sources.simulator import simulatorSource


class IngestionOrchestrator:
    def __init__(self):
        self.stealth_client = StealthClient({
            "rateLimitConfig": {
                "minDelayMs": 800,
                "maxDelayMs": 2500,
                "tokensPerInterval": 8,
                "intervalMs": 10000,
            }
        })

        self.circuit_breaker = CircuitBreaker({
            "failureThreshold": 3,
            "recoveryTimeMs": 15000,
        })

        self.sources = {
            "remoteok": remoteOkSource,
            "jobicy": jobicySource,
            "hackernews": hackerNewsSource,
            "linkedin": linkedInSource,
            "simulator": simulatorSource,
        }

        self.subscribers: Set[asyncio.Queue] = set()
        self.history: List[Dict[str, Any]] = []
        self.stats = {
            "totalRuns": 0,
            "totalJobsExtracted": 0,
            "challengesEvaded": 0,
            "schemaFallbacksRecovered": 0,
            "circuitBreaks": 0,
        }

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)

    def broadcast(self, event_data: Dict[str, Any]) -> None:
        rand_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
        enriched = {
            "id": f"evt-{int(time.time() * 1000)}-{rand_id}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            **event_data,
        }

        for q in list(self.subscribers):
            try:
                q.put_nowait(enriched)
            except Exception:
                pass

    def get_system_status(self) -> Dict[str, Any]:
        return {
            "rateLimiter": self.stealth_client.rate_limiter.get_status(),
            "circuitBreakers": self.circuit_breaker.get_metrics(),
            "proxies": self.stealth_client.proxies,
            "stats": self.stats,
            "availableSources": [
                {
                    "id": k,
                    "name": src.name,
                    "url": getattr(src, "url", ""),
                }
                for k, src in self.sources.items()
            ],
        }

    async def run_ingestion(self, source_id: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = options or {}
        source = self.sources.get(source_id)
        if not source:
            raise ValueError(f"Invalid source identifier: {source_id}")

        run_id = f"run-{int(time.time() * 1000)}"
        self.stats["totalRuns"] += 1

        self.broadcast({
            "type": "INGESTION_START",
            "runId": run_id,
            "sourceId": source_id,
            "sourceName": source.name,
            "params": options,
        })

        def telemetry_forwarder(data: Dict[str, Any]) -> None:
            t = data.get("type")
            if t in ("CHALLENGE_DETECTED", "CHALLENGE_INJECTED"):
                self.stats["challengesEvaded"] += 1
            if t == "FAILOVER_SUCCESS":
                self.stats["schemaFallbacksRecovered"] += 1
            if t == "CIRCUIT_TRIPPED":
                self.stats["circuitBreaks"] += 1
            self.broadcast({**data, "runId": run_id, "sourceId": source_id})

        domain = "sandbox.internal"
        if getattr(source, "url", None):
            try:
                parsed_host = urlparse(source.url).hostname
                if parsed_host:
                    domain = parsed_host
            except Exception:
                pass

        try:
            circuit_check = self.circuit_breaker.check_state(domain)
            if not circuit_check["allowed"]:
                self.broadcast({
                    "type": "CIRCUIT_REJECTED",
                    "runId": run_id,
                    "domain": domain,
                    "reason": circuit_check["reason"],
                })
                raise RuntimeError(circuit_check["reason"])

            if source_id == "simulator":
                scenario = options.get("scenario") or "schema_drift"
                result = await source.run_scenario(scenario, self.stealth_client, self.circuit_breaker, telemetry_forwarder)
            else:
                result = await source.extract(self.stealth_client, telemetry_forwarder, options)

            self.circuit_breaker.report_success(domain)
            jobs_count = len(result.get("jobs", []))
            self.stats["totalJobsExtracted"] += jobs_count

            self.broadcast({
                "type": "INGESTION_COMPLETED",
                "runId": run_id,
                "sourceId": source_id,
                "jobsExtracted": jobs_count,
                "strategyUsed": result.get("strategy", "DEFAULT"),
                "quality": result.get("quality", {}),
            })

            record = {
                "runId": run_id,
                "sourceId": source_id,
                "sourceName": source.name,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "jobsCount": jobs_count,
                "strategy": result.get("strategy", "DEFAULT"),
                "quality": result.get("quality", {}),
                "jobs": result.get("jobs", []),
            }

            self.history.insert(0, record)
            if len(self.history) > 50:
                self.history.pop()

            return record

        except Exception as err:
            self.circuit_breaker.report_failure(domain, str(err))
            self.broadcast({
                "type": "INGESTION_ERROR",
                "runId": run_id,
                "sourceId": source_id,
                "error": str(err),
            })
            raise err
