"""
Hacker News Ingestion Source
Queries latest 'Who is Hiring' megathread from Firebase API
"""
import json
import re
import asyncio
from typing import Dict, Any, Callable, Optional
from ..parser import ResilientParser
from ...stealth.stealth_client import StealthClient


class HackerNewsSource:
    id = "hackernews"
    name = "Hacker News: Who is Hiring (Live Real Source)"
    url = "https://hacker-news.firebaseio.com/v0/user/whoishiring.json"

    @classmethod
    async def extract(
        cls,
        stealth_client: StealthClient,
        telemetry: Callable[[Dict[str, Any]], None],
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        telemetry({
            "type": "PIPELINE_STEP",
            "step": "FETCHING_HN_THREAD",
            "source": "HackerNews API",
            "note": "Looking up latest Who is Hiring megathread",
        })

        user_res = await stealth_client.fetch(
            "https://hacker-news.firebaseio.com/v0/user/whoishiring.json",
            {},
            telemetry,
        )
        user_data = json.loads(user_res["data"])
        top_submitted = user_data.get("submitted", [])[:1]

        if not top_submitted:
            raise RuntimeError("Could not locate latest Who is Hiring thread ID")

        thread_id = top_submitted[0]
        telemetry({
            "type": "PIPELINE_STEP",
            "step": "FETCHING_HN_COMMENTS",
            "source": "HackerNews Thread",
            "note": f"Querying top job comments from thread #{thread_id}",
        })

        thread_res = await stealth_client.fetch(
            f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json",
            {},
            telemetry,
        )
        thread_data = json.loads(thread_res["data"])
        kid_ids = thread_data.get("kids", [])[:10]

        async def fetch_job(kid_id: int):
            try:
                item_res = await stealth_client.fetch(
                    f"https://hacker-news.firebaseio.com/v0/item/{kid_id}.json",
                    {},
                    telemetry,
                )
                item = json.loads(item_res["data"])
                if item and item.get("text") and not item.get("deleted"):
                    raw_text = item["text"]
                    first_line = re.split(r"<p>|<br\s*/?>|\n", raw_text)[0]
                    first_line = re.sub(r"<[^>]*>?", "", first_line).strip()
                    parts = re.split(r"\s*\|\s*|\s*-\s*", first_line)

                    company = parts[0] if len(parts) > 0 else "YC Tech Startup"
                    title = parts[1] if len(parts) > 1 else "Software Engineer"
                    location = parts[2] if len(parts) > 2 else "Remote / Hybrid"

                    return {
                        "id": f"hn-{item['id']}",
                        "title": title[:77] + "..." if len(title) > 80 else title,
                        "company": company[:47] + "..." if len(company) > 50 else company,
                        "location": location[:37] + "..." if len(location) > 40 else location,
                        "salary": "Competitive Equity + Base",
                        "url": f"https://news.ycombinator.com/item?id={item['id']}",
                        "tags": ["YC Community", "HackerNews"],
                        "source": "HackerNews",
                        "tier": "TIER_1_SELECTORS",
                    }
            except Exception:
                return None
            return None

        job_tasks = [fetch_job(kid_id) for kid_id in kid_ids]
        results = await asyncio.gather(*job_tasks)
        jobs = [j for j in results if j]

        return {
            "jobs": jobs,
            "strategy": "TIER_1_SELECTORS",
            "quality": ResilientParser.evaluate_payload_quality(jobs),
        }


hackerNewsSource = HackerNewsSource
