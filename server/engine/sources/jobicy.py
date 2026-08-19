"""
Jobicy Remote Tech Ingestion Source
Direct JSON Feed with Fallback
"""
import json
from typing import Dict, Any, Callable, Optional
from ..parser import ResilientParser
from ...stealth.stealth_client import StealthClient


class JobicySource:
    id = "jobicy"
    name = "Jobicy Remote Tech (Live Real Source)"
    url = "https://jobicy.com/api/v2/remote-jobs?count=20"

    @classmethod
    async def extract(
        cls,
        stealth_client: StealthClient,
        telemetry: Callable[[Dict[str, Any]], None],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        options = options or {}
        limit = options.get("limit", 25)

        telemetry({
            "type": "PIPELINE_STEP",
            "step": "PRIMARY_SOURCE_INGESTION",
            "source": "Jobicy Feed",
            "note": f"Ingesting {limit} global remote engineering postings",
        })

        request_count = min(limit, 50)
        response = await stealth_client.fetch(
            f"https://jobicy.com/api/v2/remote-jobs?count={request_count}",
            {"headers": {"Accept": "application/json"}},
            telemetry,
        )

        try:
            parsed = json.loads(response["data"])
            items = parsed.get("jobs", [])[:limit]

            jobs = []
            for item in items:
                min_sal = item.get("annualSalaryMin")
                max_sal = item.get("annualSalaryMax")
                if min_sal and max_sal:
                    sal_str = f"${min_sal:,} - ${max_sal:,}"
                elif min_sal:
                    sal_str = f"${min_sal:,}+"
                else:
                    sal_str = "Not Specified"

                tags = []
                if item.get("jobIndustry"):
                    tags.append(item["jobIndustry"])
                if item.get("jobType"):
                    tags.append(item["jobType"])
                if not tags:
                    tags = ["Engineering"]

                jobs.append({
                    "id": f"jobicy-{item.get('id', '')}",
                    "title": item.get("jobTitle", "Remote Engineer"),
                    "company": item.get("companyName", "Tech Employer"),
                    "location": item.get("jobGeo") or "Anywhere",
                    "salary": sal_str,
                    "url": item.get("url", ""),
                    "tags": tags,
                    "source": "Jobicy",
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
                "source": "Jobicy",
                "reason": f"JSON parsing failed: {err}. Attempting HTML heuristic extraction.",
                "level": "WARN",
            })
            return ResilientParser.parse(response.get("data", ""))


jobicySource = JobicySource
