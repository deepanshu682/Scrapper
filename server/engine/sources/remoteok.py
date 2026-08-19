"""
RemoteOK Ingestion Source
Primary JSON API -> Secondary HTML Microdata -> Tertiary Mirror Failover
"""
import json
from typing import Dict, Any, Callable, Optional
from ..parser import ResilientParser
from ...stealth.stealth_client import StealthClient


class RemoteOkSource:
    id = "remoteok"
    name = "RemoteOK (Live Real Source)"
    url = "https://remoteok.com/api"
    fallback_html_url = "https://remoteok.com"
    selector_config = {
        "container": "tr.job",
        "title": 'h2[itemprop="title"]',
        "company": 'h3[itemprop="name"]',
        "location": ".location",
        "url": "a.preventLink",
        "tags": ".tag h3",
    }

    @classmethod
    async def extract(
        cls,
        stealth_client: StealthClient,
        telemetry: Callable[[Dict[str, Any]], None],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        options = options or {}
        limit = options.get("limit", 25)

        # Attempt Primary API ingestion
        try:
            telemetry({
                "type": "PIPELINE_STEP",
                "step": "PRIMARY_SOURCE_INGESTION",
                "source": "RemoteOK API",
                "note": f"Fetching {limit} live job postings",
            })

            response = await stealth_client.fetch(
                "https://remoteok.com/api",
                {"headers": {"Accept": "application/json, text/plain, */*"}},
                telemetry,
            )

            data = json.loads(response["data"])
            if isinstance(data, list):
                valid_items = [
                    item for item in data
                    if isinstance(item, dict) and item.get("id") and item.get("position") and item.get("company")
                ][:limit]

                jobs = []
                for item in valid_items:
                    min_sal = item.get("salary_min")
                    max_sal = item.get("salary_max")
                    if min_sal and max_sal:
                        sal_str = f"${min_sal:,} - ${max_sal:,}"
                    else:
                        sal_str = str(item.get("salary") or "Competitive")

                    jobs.append({
                        "id": f"rok-{item['id']}",
                        "title": item["position"],
                        "company": item["company"],
                        "location": item.get("location") or "Remote",
                        "salary": sal_str,
                        "url": item.get("url") or f"https://remoteok.com/l/{item['id']}",
                        "tags": item.get("tags") or [],
                        "source": "RemoteOK",
                        "tier": "TIER_0_DIRECT_FEED",
                    })

                return {
                    "jobs": jobs,
                    "strategy": "TIER_0_DIRECT_FEED",
                    "quality": ResilientParser.evaluate_payload_quality(jobs),
                }

        except Exception as err:
            telemetry({
                "type": "FAILOVER_TRIGGERED",
                "source": "RemoteOK",
                "reason": f"Primary API path failed: {err}. Triggering Resilient HTML/Microdata Fallback.",
                "level": "WARN",
            })

        # Secondary Failover: Scrape HTML & parse with Resilient Multi-tier Parser
        try:
            html_response = await stealth_client.fetch("https://remoteok.com/remote-dev-jobs", {}, telemetry)
            parsed = ResilientParser.parse(html_response["data"], cls.selector_config)
            if parsed["jobs"]:
                for j in parsed["jobs"]:
                    j["source"] = "RemoteOK (HTML Microdata)"
                return parsed
        except Exception:
            telemetry({
                "type": "FAILOVER_TRIGGERED",
                "source": "RemoteOK",
                "reason": "HTML mirror extraction also blocked. Falling back to structured public remote feed mirror.",
                "level": "WARN",
            })

        # Tertiary Failover: Structured Job RSS/JSON mirror
        mirror_res = await stealth_client.fetch(
            "https://jobicy.com/api/v2/remote-jobs?count=15&tag=dev",
            {},
            telemetry,
        )
        mirror_data = json.loads(mirror_res["data"])
        fallback_jobs = []
        for item in mirror_data.get("jobs", []):
            min_sal = item.get("annualSalaryMin")
            max_sal = item.get("annualSalaryMax")
            sal_str = f"${min_sal:,} - ${max_sal:,}" if min_sal and max_sal else "Competitive"

            fallback_jobs.append({
                "id": f"rok-mirror-{item.get('id', '')}",
                "title": item.get("jobTitle", "Remote Developer"),
                "company": item.get("companyName", "Tech Employer"),
                "location": item.get("jobGeo") or "Remote",
                "salary": sal_str,
                "url": item.get("url", ""),
                "tags": ["Failover Recovered", item.get("jobIndustry") or "Engineering"],
                "source": "RemoteOK (Mirror Fallback)",
                "tier": "TIER_2_JSON_LD",
            })

        return {
            "jobs": fallback_jobs,
            "strategy": "TIER_2_MIRROR_FAILOVER",
            "quality": ResilientParser.evaluate_payload_quality(fallback_jobs),
        }


remoteOkSource = RemoteOkSource
