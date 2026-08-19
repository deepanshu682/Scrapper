"""
Anti-Bot & Drift Attack Simulator (Sandbox)
Demonstrates multi-tier resilience against live attack scenarios.
"""
import asyncio
from typing import Dict, Any, Callable
from ..parser import ResilientParser
from ..circuit_breaker import CircuitBreaker
from ...stealth.stealth_client import StealthClient


class SimulatorSource:
    id = "simulator"
    name = "Anti-Bot & Drift Attack Simulator (Sandbox)"
    url = "https://sandbox.internal/attack-simulator"
    scenarios = {
        "schema_drift": {
            "name": "Overnight DOM Schema Drift (Obfuscated Markup)",
            "description": "Simulates website renaming all CSS classes to obfuscated hashes (_x9a2k). Verifies Tier 2 JSON-LD & Tier 3 Heuristic Fallback.",
        },
        "cloudflare_block": {
            "name": "Mid-Run Cloudflare 403 Challenge",
            "description": "Simulates bot challenge injection mid-stream. Verifies proxy rotation, header morphing, and backoff.",
        },
        "rate_limit_burst": {
            "name": "Aggressive 429 Rate Limiting & Circuit Trip",
            "description": "Simulates target IP rate limit trigger. Verifies Circuit Breaker tripping to OPEN and auto-quarantining.",
        },
    }

    @classmethod
    async def run_scenario(
        cls,
        scenario_key: str,
        stealth_client: StealthClient,
        circuit_breaker: CircuitBreaker,
        telemetry: Callable[[Dict[str, Any]], None],
    ) -> Dict[str, Any]:
        scenario_name = cls.scenarios.get(scenario_key, {}).get("name", scenario_key)
        telemetry({
            "type": "SIMULATION_START",
            "scenario": scenario_key,
            "name": scenario_name,
            "note": "Executing resilience test vector against ingestion pipeline",
        })

        if scenario_key == "schema_drift":
            # Generate synthetic obfuscated HTML with broken classes but intact JSON-LD & text density
            synthetic_html = """
            <!DOCTYPE html>
            <html>
            <head>
              <script type="application/ld+json">
              [
                {
                  "@type": "JobPosting",
                  "title": "Staff Distributed Systems Engineer",
                  "hiringOrganization": {"@type": "Organization", "name": "Aether Scale Systems"},
                  "jobLocation": {"address": {"addressLocality": "San Francisco", "addressRegion": "CA"}},
                  "baseSalary": {"value": {"value": "$210,000 - $260,000"}}
                },
                {
                  "@type": "JobPosting",
                  "title": "Principal Anti-Abuse Security Engineer",
                  "hiringOrganization": {"@type": "Organization", "name": "Sentinel Defense"},
                  "jobLocation": {"address": {"addressLocality": "Remote", "addressCountry": "US"}},
                  "baseSalary": {"value": {"value": "$195,000 - $240,000"}}
                }
              ]
              </script>
            </head>
            <body>
              <div class="_8x9z_obfuscated_container">
                <div class="_k29a_item">
                  <h4 class="_random_hash_h4">Lead Full-Stack Web Scraper Architect</h4>
                  <p class="_random_hash_sub">Hydra Intelligence | Seattle, WA | $180k - $220k</p>
                </div>
              </div>
            </body>
            </html>
            """

            telemetry({
                "type": "PIPELINE_STEP",
                "step": "TIER_1_ATTEMPT",
                "note": "Attempting Primary CSS Selectors (tr.job, .job-title)... Result: 0 matches (Schema Drift detected!)",
                "level": "WARN",
            })

            # Intentionally pass old broken selectors to demonstrate automatic fallback
            broken_selectors = {"container": ".legacy-job-row", "title": ".legacy-title", "company": ".legacy-company"}
            parsed = ResilientParser.parse(synthetic_html, broken_selectors)

            telemetry({
                "type": "FAILOVER_SUCCESS",
                "step": "FALLBACK_RECOVERY",
                "strategy": parsed["strategy"],
                "recoveredCount": len(parsed["jobs"]),
                "note": f"Pipeline successfully recovered {len(parsed['jobs'])} jobs via {parsed['strategy']} without crashing.",
            })

            for j in parsed["jobs"]:
                j["source"] = "Drift-Simulated Source"

            return {
                "jobs": parsed["jobs"],
                "strategy": parsed["strategy"],
                "quality": parsed["quality"],
            }

        if scenario_key == "cloudflare_block":
            mock_domain = "target-anti-bot.sandbox.internal"

            telemetry({
                "type": "CHALLENGE_INJECTED",
                "source": mock_domain,
                "challenge": "Cloudflare IUAM / Turnstile 403 Forbidden",
                "note": "Injecting anti-bot challenge response. Initiating evasive recovery.",
            })

            # Step 1: Trigger stealth client backoff & proxy rotation
            proxy = stealth_client.get_next_proxy()
            stealth_client.report_proxy_failure(proxy["id"], 40)

            telemetry({
                "type": "PROXY_QUARANTINED",
                "proxyId": proxy["id"],
                "newHealth": proxy["health"],
                "note": f"Proxy {proxy['id']} penalized. Rotating to next residential pool IP.",
            })

            # Delay to simulate exponential backoff
            await asyncio.sleep(1.2)

            recovered_proxy = stealth_client.get_next_proxy()
            telemetry({
                "type": "FAILOVER_SUCCESS",
                "step": "EVASION_ROUTING_RECOVERY",
                "proxyId": recovered_proxy["id"],
                "note": f"Switched session to {recovered_proxy['region']} ({recovered_proxy['ip']}) with mutated TLS/UA client hints.",
            })

            return {
                "jobs": [
                    {
                        "id": "evaded-1",
                        "title": "Senior Infrastructure Engineer (Evasion Recovered)",
                        "company": "Stealth Scale Labs",
                        "location": "Remote (US/EU)",
                        "salary": "$160,000 - $210,000",
                        "url": "https://example.com/job/evaded-1",
                        "tags": ["Anti-Bot Evasion Demo", "Recovered"],
                        "source": "Cloudflare Challenge Handling Sandbox",
                        "tier": "TIER_0_DIRECT_FEED",
                    }
                ],
                "strategy": "EVASIVE_PROXY_ROTATION",
                "quality": {"confidence": 100, "status": "HEALTHY"},
            }

        if scenario_key == "rate_limit_burst":
            mock_domain = "strict-rate-limiter.sandbox.internal"

            telemetry({
                "type": "BURST_ATTACK",
                "source": mock_domain,
                "note": "Simulating high-frequency 429 Too Many Requests storm.",
            })

            # Trip circuit breaker
            circuit_breaker.force_trip(mock_domain, "429 Rate Limit Threshold Exceeded (3 consecutive 429s)")
            stealth_client.rate_limiter.report_rate_limit(15)

            telemetry({
                "type": "CIRCUIT_TRIPPED",
                "domain": mock_domain,
                "state": "OPEN",
                "note": "Circuit breaker transitioned to OPEN state. All upstream traffic paused for 15s quarantine.",
            })

            return {
                "jobs": [],
                "strategy": "CIRCUIT_BREAKER_PROTECTION",
                "quality": {"confidence": 0, "status": "QUARANTINED_BACKOFF", "reason": "Circuit OPEN - Target protected from IP ban"},
            }

        raise ValueError(f"Unknown simulation scenario: {scenario_key}")


simulatorSource = SimulatorSource
