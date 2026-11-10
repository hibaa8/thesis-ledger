"""Optional, source-linked X commentary from the xAI Responses API."""

import os
import re
from datetime import date, timedelta

import httpx

POST_URL = re.compile(
    r"https://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})/status/([0-9]+)(?:[?#][^\s)]*)?",
    re.IGNORECASE,
)
INLINE_CITATION = re.compile(r"\[\[\d+\]\]\((https://[^\s)]+)\)")
MAX_POSTS = 2


def cited_posts(payload, start, end):
    posts = {}
    for message in payload.get("output", []):
        if message.get("type") != "message":
            continue
        for content in message.get("content", []):
            if content.get("type") != "output_text":
                continue
            citations = {
                url for citation in content.get("annotations", [])
                if citation.get("type") == "url_citation"
                and (url := citation.get("url"))
            }
            for line in content.get("text", "").splitlines():
                day, _, summary = line.strip().lstrip("- ").partition(" ")
                try:
                    published = date.fromisoformat(day)
                except ValueError:
                    continue
                links = INLINE_CITATION.findall(summary)
                if not start <= published <= end or len(links) != 1 or links[0] not in citations:
                    continue
                match = POST_URL.fullmatch(links[0])
                description = INLINE_CITATION.sub("", summary).strip(" -")
                if not match or not description:
                    continue
                handle, post_id = match.groups()
                posts.setdefault(post_id, dict(
                    id=f"x-post-{post_id}", kind="sentiment",
                    title=f"X post by @{handle}", source="X · Grok X Search",
                    url=f"https://x.com/{handle}/status/{post_id}",
                    published=published.isoformat(),
                    text=f"Grok summary of the cited post: {description[:400]}",
                ))
                if len(posts) == MAX_POSTS:
                    return list(posts.values())
    return list(posts.values())


async def x_post_evidence(client, ticker, as_of):
    if not (key := os.getenv("XAI_API_KEY")):
        return []
    start = as_of - timedelta(days=3)
    try:
        response = await client.post(
            "https://api.x.ai/v1/responses",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": os.getenv("LEDGER_XAI_MODEL") or "grok-4.7",
                "input": (
                    f"Use X Search for US-listed ${ticker}. Find up to {MAX_POSTS} recent, "
                    "material original posts from relevant company accounts, named executives, "
                    "regulators, or established industry leaders speaking in their area of expertise. "
                    "Check the account identity and prefer first-hand statements over reactions. "
                    "Exclude rumors, reposts, impersonators, and engagement bait. "
                    "Use one line per post: YYYY-MM-DD (UTC publication date), a space, "
                    "then a short neutral paraphrase ending with one inline citation to the original post. "
                    "If none qualify, say so. Use one search round and avoid fetching threads or profiles."
                ),
                "tools": [{
                    "type": "x_search", "from_date": start.isoformat(),
                    "to_date": (as_of + timedelta(days=1)).isoformat(),
                }],
                "max_turns": 2,
                "store": False,
            },
            timeout=12,
        )
        response.raise_for_status()
        return cited_posts(response.json(), start, as_of)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return []
