"""
Resilient Multi-Strategy Parser with Schema Drift Recovery

When target platforms change class names, obfuscate DOM nodes,
or alter layouts overnight, this multi-tier engine gracefully falls back
across 4 extraction tiers rather than returning empty payloads.
"""
import json
import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup


class ResilientParser:
    """
    Tier 1: Platform-specific CSS Selector extraction
    """
    @staticmethod
    def parse_with_selectors(soup: BeautifulSoup, selector_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        container_sel = selector_config.get("container", "")
        if not container_sel:
            return jobs

        elements = soup.select(container_sel)

        for el in elements:
            # Title
            title_node = el.select_one(selector_config.get("title", "")) if selector_config.get("title") else None
            if not title_node:
                title_node = el.select_one('h2, h3, .title, [data-testid="job-title"]')
            title = title_node.get_text(strip=True) if title_node else ""

            # Company
            company_node = el.select_one(selector_config.get("company", "")) if selector_config.get("company") else None
            if not company_node:
                company_node = el.select_one('.company, .employer, [data-testid="company-name"]')
            company = company_node.get_text(strip=True) if company_node else ""

            # Location
            loc_node = el.select_one(selector_config.get("location", "")) if selector_config.get("location") else None
            if not loc_node:
                loc_node = el.select_one('.location, .region')
            location = loc_node.get_text(strip=True) if loc_node else "Remote"

            # URL
            url_node = el.select_one(selector_config.get("url", "")) if selector_config.get("url") else None
            if not url_node:
                url_node = el.select_one("a")
            url = url_node.get("href", "") if url_node else ""

            # Tags
            tags: List[str] = []
            if selector_config.get("tags"):
                for tag_el in el.select(selector_config["tags"]):
                    t = tag_el.get_text(strip=True)
                    if t and len(t) < 30:
                        tags.append(t)

            if title and (company or location):
                jobs.append({
                    "title": title,
                    "company": company or "Confidential",
                    "location": location or "Remote",
                    "url": url,
                    "tags": tags[:5],
                    "tier": "TIER_1_SELECTORS",
                })

        return jobs

    """
    Tier 2: Schema.org / JSON-LD structured data extraction
    Almost all major job boards (LinkedIn, Indeed, Google Jobs) embed LD+JSON JobPosting schema.
    """
    @staticmethod
    def parse_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        script_tags = soup.find_all("script", type="application/ld+json")

        for script in script_tags:
            try:
                raw = script.string or script.get_text()
                if not raw:
                    continue
                data = json.loads(raw)

                items = data if isinstance(data, list) else data.get("@graph", [data])

                for item in items:
                    if not isinstance(item, dict):
                        continue

                    item_type = item.get("@type", "")
                    if item_type == "JobPosting" or item.get("title") or item.get("hiringOrganization"):
                        title = item.get("title") or item.get("name") or ""
                        hiring_org = item.get("hiringOrganization")
                        if isinstance(hiring_org, str):
                            company = hiring_org
                        elif isinstance(hiring_org, dict):
                            company = hiring_org.get("name", "Undisclosed")
                        else:
                            company = "Undisclosed"

                        location = "Remote"
                        job_loc = item.get("jobLocation")
                        if isinstance(job_loc, str):
                            location = job_loc
                        elif isinstance(job_loc, dict):
                            addr = job_loc.get("address", {})
                            if isinstance(addr, dict):
                                parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                                location = ", ".join([p for p in parts if p]) or "Remote"
                            elif isinstance(addr, str):
                                location = addr

                        salary = ""
                        base_salary = item.get("baseSalary", {})
                        if isinstance(base_salary, dict):
                            val = base_salary.get("value", {})
                            salary = val.get("value") if isinstance(val, dict) else str(val)
                        elif item.get("estimatedSalary"):
                            salary = str(item.get("estimatedSalary"))

                        if title:
                            cat = item.get("occupationalCategory")
                            jobs.append({
                                "title": title,
                                "company": company,
                                "location": location,
                                "salary": str(salary) if salary else None,
                                "url": item.get("url", ""),
                                "tags": [cat] if cat else ["JSON-LD"],
                                "tier": "TIER_2_JSON_LD",
                            })
            except Exception:
                continue

        return jobs

    """
    Tier 3: Heuristic & Content-Density Extraction
    Scans text nodes for job-like entities when both CSS selectors & JSON-LD fail.
    """
    @staticmethod
    def parse_heuristic(soup: BeautifulSoup) -> List[Dict[str, Any]]:
        jobs: List[Dict[str, Any]] = []
        job_keywords = re.compile(
            r"(engineer|developer|architect|designer|manager|lead|specialist|analyst|consultant|fullstack|frontend|backend|devops|data|product)",
            re.IGNORECASE,
        )

        cards = soup.select('article, div[class*="card"], div[class*="item"], div[class*="row"], li[class*="job"]')

        for el in cards:
            text = el.get_text()
            if job_keywords.search(text):
                headings = [
                    h for h in el.select("h1, h2, h3, h4, strong, a")
                    if job_keywords.search(h.get_text())
                ]

                if headings:
                    first_heading = headings[0]
                    title = first_heading.get_text(strip=True)

                    link = ""
                    parent_a = first_heading.find_parent("a")
                    if parent_a and parent_a.get("href"):
                        link = parent_a.get("href", "")
                    else:
                        inner_a = el.select_one("a")
                        link = inner_a.get("href", "") if inner_a else ""

                    subtexts = [
                        p.get_text(strip=True)
                        for p in el.select("p, span, div")
                        if 2 < len(p.get_text(strip=True)) < 50 and p.get_text(strip=True) != title
                    ]

                    company = subtexts[0] if len(subtexts) > 0 else "Verified Employer"
                    location = subtexts[1] if len(subtexts) > 1 else "Remote"

                    if 3 < len(title) < 120:
                        jobs.append({
                            "title": title,
                            "company": company,
                            "location": location,
                            "url": link,
                            "tags": ["Heuristic Inferred"],
                            "tier": "TIER_3_HEURISTIC",
                        })

        # Deduplicate jobs by title + company
        seen = set()
        deduped = []
        for j in jobs:
            key = f"{j['title'].lower()}::{j['company'].lower()}"
            if key not in seen:
                seen.add(key)
                deduped.append(j)

        return deduped

    """
    Validate extraction completeness and calculate confidence score (0 - 100%)
    """
    @staticmethod
    def evaluate_payload_quality(jobs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not jobs:
            return {
                "confidence": 0,
                "status": "EMPTY_PAYLOAD",
                "reason": "Zero job items extracted from document",
            }

        valid_count = 0
        for job in jobs:
            title = job.get("title", "")
            company = job.get("company", "")
            has_title = bool(title and len(title) > 3)
            has_company = bool(company and len(company) > 1)
            not_garbage = "<!doctype" not in title.lower() and "<html" not in title.lower()

            if has_title and has_company and not_garbage:
                valid_count += 1

        confidence = int(round((valid_count / len(jobs)) * 100)) if jobs else 0
        status = "HEALTHY" if confidence >= 70 else ("DEGRADED" if confidence >= 40 else "ANOMALOUS")

        return {
            "confidence": confidence,
            "validCount": valid_count,
            "totalCount": len(jobs),
            "status": status,
        }

    """
    Resilient execute: runs multi-strategy fallback pipeline
    """
    @classmethod
    def parse(cls, html: Optional[str], selector_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not html or not isinstance(html, str):
            return {"jobs": [], "strategy": "NONE", "quality": {"confidence": 0, "status": "INVALID_HTML"}}

        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        jobs: List[Dict[str, Any]] = []
        strategy = "TIER_1_SELECTORS"

        # Step 1: Try Primary CSS Selectors if provided
        if selector_config:
            jobs = cls.parse_with_selectors(soup, selector_config)

        # Step 2: Fallback to JSON-LD if CSS selectors yielded nothing
        if not jobs:
            jobs = cls.parse_json_ld(soup)
            if jobs:
                strategy = "TIER_2_JSON_LD"

        # Step 3: Fallback to Heuristic density analysis
        if not jobs:
            jobs = cls.parse_heuristic(soup)
            if jobs:
                strategy = "TIER_3_HEURISTIC"

        quality = cls.evaluate_payload_quality(jobs)

        return {
            "jobs": jobs,
            "strategy": strategy,
            "quality": quality,
        }
