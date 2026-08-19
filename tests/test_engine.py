"""
Aegis Ingestion Engine Test Suite (Python)
Unit and integration tests for Rate Limiter, Circuit Breaker, Resilient Parser, and Stealth Client.
"""
import unittest
from server.stealth.rate_limiter import AdaptiveRateLimiter
from server.engine.circuit_breaker import CircuitBreaker, CircuitState
from server.engine.parser import ResilientParser
from server.stealth.stealth_client import StealthClient


class TestAegisEngine(unittest.TestCase):

    def test_01_rate_limiter_gaussian_jitter_and_throttle(self):
        print("-> Test 1: Adaptive Rate Limiter & Gaussian Jitter")
        limiter = AdaptiveRateLimiter(min_delay_ms=100, max_delay_ms=300)
        jitter = limiter.calculate_jitter()
        self.assertTrue(100 <= jitter <= 300, f"Jitter {jitter} should be between 100 and 300ms")

        limiter.report_rate_limit(retry_after_seconds=2)
        status = limiter.get_status()
        self.assertTrue(status["isThrottled"], "Rate limiter should be throttled after 429 signal")
        print("  [OK] Rate limiter pacing and backoff verified.")

    def test_02_circuit_breaker_state_machine(self):
        print("-> Test 2: Circuit Breaker State Machine")
        cb = CircuitBreaker({"failureThreshold": 3, "recoveryTimeMs": 500})
        domain = "test-api.io"

        self.assertEqual(cb.check_state(domain)["state"], CircuitState.CLOSED)
        cb.report_failure(domain, "500 Server Error")
        cb.report_failure(domain, "502 Bad Gateway")
        cb.report_failure(domain, "429 Rate Limited")

        # After 3 failures, state must be OPEN
        tripped = cb.check_state(domain)
        self.assertEqual(tripped["state"], CircuitState.OPEN, "Circuit must trip to OPEN after 3 failures")
        self.assertFalse(tripped["allowed"], "Requests must be rejected when circuit is OPEN")
        print("  [OK] Circuit breaker tripping verified.")

    def test_03_resilient_parser_json_ld_fallback(self):
        print("-> Test 3: Resilient Multi-Strategy Parser (Schema Drift Recovery - JSON-LD)")
        json_ld_html = """
        <html>
        <head>
          <script type="application/ld+json">
          {
            "@type": "JobPosting",
            "title": "Lead Anti-Bot Security Engineer",
            "hiringOrganization": {"@type": "Organization", "name": "Acdyon Engineering"},
            "jobLocation": {"address": {"addressLocality": "San Francisco", "addressRegion": "CA"}},
            "baseSalary": {"value": {"value": "$220,000"}}
          }
          </script>
        </head>
        <body><div class="empty-unrelated-layout">No standard classes here</div></body>
        </html>
        """

        result = ResilientParser.parse(json_ld_html, {"container": ".legacy-class-that-broke"})
        self.assertEqual(result["strategy"], "TIER_2_JSON_LD", "Parser must fall back to JSON-LD")
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["title"], "Lead Anti-Bot Security Engineer")
        self.assertEqual(result["jobs"][0]["company"], "Acdyon Engineering")
        self.assertEqual(result["quality"]["status"], "HEALTHY")
        print("  [OK] JSON-LD Tier 2 schema fallback verified.")

    def test_04_resilient_parser_heuristic_fallback(self):
        print("-> Test 4: Resilient Multi-Strategy Parser (Heuristic Fallback)")
        heuristic_html = """
        <html>
        <body>
          <article class="_random_hashed_container">
            <h3>Principal Backend Systems Architect</h3>
            <p>Nexus Distributed Corp</p>
            <span>Remote - North America</span>
          </article>
        </body>
        </html>
        """

        result = ResilientParser.parse(heuristic_html, None)
        self.assertEqual(result["strategy"], "TIER_3_HEURISTIC", "Parser must fall back to Heuristic extraction")
        self.assertEqual(len(result["jobs"]), 1)
        self.assertEqual(result["jobs"][0]["title"], "Principal Backend Systems Architect")
        print("  [OK] Heuristic Tier 3 content-density fallback verified.")

    def test_05_anti_bot_challenge_detection(self):
        print("-> Test 5: Bot Challenge Signature Detection")
        client = StealthClient()
        cf_challenge = client.detect_anti_bot_challenge(
            "<html><body><title>Just a moment... Cloudflare Turnstile Verification</title></body></html>",
            403,
        )
        self.assertIsNotNone(cf_challenge)
        self.assertEqual(cf_challenge["type"], "CLOUDFLARE_CHALLENGE")

        dd_challenge = client.detect_anti_bot_challenge(
            '<html><body><script src="https://geo.captcha-delivery.com/captcha/"></script></body></html>',
            403,
        )
        self.assertIsNotNone(dd_challenge)
        self.assertEqual(dd_challenge["type"], "DATADOME_CAPTCHA")
        print("  [OK] Anti-bot signature detection verified.")


if __name__ == "__main__":
    unittest.main()
