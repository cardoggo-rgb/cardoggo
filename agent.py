#!/usr/bin/env python3
"""
CarDoggo Daily Content Agent
=============================
Researches a car-related topic, writes an article, sources a free image,
and publishes (or drafts) it to cardoggo.com via the WordPress REST API.

Run manually:   python3 agent.py
Run as a dry run (no publish, just print): python3 agent.py --dry-run
Schedule it with cron, e.g. once a day at 8am:
    0 8 * * * cd /path/to/cardoggo_agent && /usr/bin/python3 agent.py >> agent.log 2>&1

Configuration lives in a .env file (see .env.example).
"""

import os
import re
import sys
import json
import socket
import base64
import random
import argparse
import datetime
from pathlib import Path

import requests
import urllib3.util.connection as urllib3_cn

# GitHub Actions runners sometimes can't route IPv6, but some hosts (like
# cardoggo.com) return an IPv6 address first. Force IPv4-only DNS resolution
# so we don't hit "Network is unreachable" errors.
def _allowed_gai_family():
    return socket.AF_INET

urllib3_cn.allowed_gai_family = _allowed_gai_family

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is optional if you export vars another way

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WP_BASE_URL = os.environ.get("WP_BASE_URL", "https://cardoggo.com").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")  # WordPress "Application Password"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")  # free at pexels.com/api

PUBLISH_STATUS = os.environ.get("PUBLISH_STATUS", "draft")  # "draft" or "publish"

STATE_FILE = Path(__file__).parent / "state.json"

# Rotating topic pool, tagged with a suggested WP category name.
# Edit this freely -- the agent will pick the next un-used one each run,
# and reshuffles once the pool is exhausted.
TOPIC_POOL = [
    ("Best Budget-Friendly SUVs in 2026", "Car Buying Tips"),
    ("How EV Battery Warranties Actually Work", "Electric and Hybrid Vehicles"),
    ("Signs Your Timing Belt Needs Replacing", "Car Maintenance and Repair"),
    ("Sedan vs Hatchback: Which Fits Your Lifestyle", "Car Comparisons"),
    ("The Rise of Plug-In Hybrids: Worth the Hype?", "Electric and Hybrid Vehicles"),
    ("How to Read a Car's VIN Number", "Car Buying Tips"),
    ("Classic Muscle Cars That Are Still Affordable", "Classic Cars"),
    ("Winter Car Maintenance Checklist", "Car Maintenance and Repair"),
    ("Best Road Trip Snacks and Car Organization Hacks", "Blog"),
    ("Used Car vs Certified Pre-Owned: What's the Difference", "Car Buying Tips"),
    ("Top Safety Features to Look For in a New Car", "Cars"),
    ("How Often Should You Really Rotate Your Tires?", "Car Maintenance and Repair"),
    ("Electric Truck Market: Who's Leading in 2026", "Electric and Hybrid Vehicles"),
    ("Understanding Car Depreciation Before You Buy", "Car Buying Tips"),
    ("Manual vs Automatic Transmission in 2026: Does It Matter?", "Car Comparisons"),
]


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ---------------------------------------------------------------------------
# State (avoid repeating topics)
# ---------------------------------------------------------------------------

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"used_topics": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def pick_topic(state, existing_titles):
    used = set(state["used_topics"])
    candidates = [t for t in TOPIC_POOL if t[0] not in used and t[0] not in existing_titles]
    if not candidates:
        # Pool exhausted / all covered on-site -- reset local memory and try again
        log("Topic pool exhausted locally, resetting rotation.")
        state["used_topics"] = []
        candidates = [t for t in TOPIC_POOL if t[0] not in existing_titles]
    if not candidates:
        raise RuntimeError(
            "All topics in TOPIC_POOL already exist as posts on the site. "
            "Add more topics to TOPIC_POOL in agent.py."
        )
    topic, category = random.choice(candidates)
    state["used_topics"].append(topic)
    save_state(state)
    return topic, category


WP_CATEGORIES = [
    "Blog", "Car Buying Tips", "Car Comparisons", "Car Maintenance and Repair",
    "Car Reviews", "Cars", "Classic Cars", "Electric and Hybrid Vehicles",
    "Latest", "Trending", "US Market",
]


def find_trending_topic(existing_titles):
    """Asks Claude to search for a genuinely current automotive news/trend angle
    and propose one fresh topic. Returns (topic, category) or None if it can't
    confidently produce one (caller should fall back to the fixed TOPIC_POOL)."""
    already_covered = "\n".join(f"- {t}" for t in existing_titles[:60]) or "(none yet)"
    prompt = (
        "Search the web for what's currently trending or newsworthy in the automotive "
        "industry today -- new model launches, industry news, EV developments, recalls, "
        "buying-advice angles tied to current events, etc. Then propose ONE specific, "
        "fresh blog post topic for an automotive blog (CarDoggo) that a reader would "
        "want to click on right now.\n\n"
        f"Do NOT propose a topic that duplicates or closely overlaps any of these "
        f"already-published posts:\n{already_covered}\n\n"
        f"Pick the best-fitting category from this exact list: {', '.join(WP_CATEGORIES)}.\n\n"
        "Respond with ONLY these two lines, nothing else:\n"
        "TOPIC: <the topic, phrased as a headline-style blog post title>\n"
        "CATEGORY: <one category from the list above, exactly as written>"
    )
    try:
        data = _call_claude([{"role": "user", "content": prompt}], max_tokens=2000)
        text = "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")
        topic_m = re.search(r"^TOPIC:\s*(.+)$", text, re.MULTILINE)
        cat_m = re.search(r"^CATEGORY:\s*(.+)$", text, re.MULTILINE)
        if not topic_m or not cat_m:
            log("Trending-topic search didn't return a clean result, falling back to topic list.")
            return None
        topic = topic_m.group(1).strip()
        category = cat_m.group(1).strip()
        if category not in WP_CATEGORIES:
            category = "Blog"  # safe default if the model picks something off-list
        if topic in existing_titles:
            log("Trending-topic search proposed a duplicate, falling back to topic list.")
            return None
        return topic, category
    except Exception as e:
        log(f"Trending-topic search failed ({e}), falling back to fixed topic list.")
        return None


# ---------------------------------------------------------------------------
# WordPress REST API client
# ---------------------------------------------------------------------------

class WordPressClient:
    def __init__(self, base_url, username, app_password):
        self.api = f"{base_url}/wp-json/wp/v2"
        token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def get_recent_titles(self, per_page=100, max_pages=3):
        titles = []
        for page in range(1, max_pages + 1):
            r = requests.get(
                f"{self.api}/posts",
                headers=self.headers,
                params={"per_page": per_page, "page": page, "_fields": "title"},
                timeout=30,
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            titles.extend([p["title"]["rendered"] for p in batch])
            if len(batch) < per_page:
                break
        return titles

    def get_or_create_category(self, name):
        r = requests.get(
            f"{self.api}/categories",
            headers=self.headers,
            params={"search": name, "per_page": 20},
            timeout=30,
        )
        r.raise_for_status()
        for cat in r.json():
            if cat["name"].lower() == name.lower():
                return cat["id"]
        r = requests.post(
            f"{self.api}/categories",
            headers=self.headers,
            json={"name": name},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["id"]

    def get_or_create_tag(self, name):
        r = requests.get(
            f"{self.api}/tags",
            headers=self.headers,
            params={"search": name, "per_page": 20},
            timeout=30,
        )
        r.raise_for_status()
        for tag in r.json():
            if tag["name"].lower() == name.lower():
                return tag["id"]
        r = requests.post(
            f"{self.api}/tags",
            headers=self.headers,
            json={"name": name},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["id"]

    def upload_media(self, image_bytes, filename, alt_text=""):
        headers = dict(self.headers)
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        headers["Content-Type"] = "image/jpeg"
        r = requests.post(
            f"{self.api}/media",
            headers=headers,
            data=image_bytes,
            timeout=60,
        )
        r.raise_for_status()
        media = r.json()
        media_id = media["id"]
        if alt_text:
            requests.post(
                f"{self.api}/media/{media_id}",
                headers=self.headers,
                json={"alt_text": alt_text},
                timeout=30,
            )
        return media_id

    def create_post(self, title, content_html, category_ids, tag_ids, featured_media, status, meta_description=None):
        payload = {
            "title": title,
            "content": content_html,
            "status": status,
            "categories": category_ids,
            "tags": tag_ids,
        }
        if featured_media:
            payload["featured_media"] = featured_media
        if meta_description:
            # Requires the Yoast REST-exposure snippet from README/YOAST_SEO_SETUP.md.
            # If that snippet isn't installed, WordPress just silently ignores this key --
            # harmless either way, so it's safe to always send it.
            payload["meta"] = {"_yoast_wpseo_metadesc": meta_description}
        r = requests.post(f"{self.api}/posts", headers=self.headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Content generation via Claude
# ---------------------------------------------------------------------------

def _call_claude(messages, max_tokens=8000):
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "system": _SYSTEM_PROMPT,
            "messages": messages,
            "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        },
        timeout=240,
    )
    if r.status_code != 200:
        log(f"Anthropic API error {r.status_code}: {r.text}")
    r.raise_for_status()
    return r.json()


_SYSTEM_PROMPT = (
    "You are a staff writer for CarDoggo, an automotive blog covering car reviews, buying "
    "advice, maintenance, EVs, and industry news. Write in a clear, friendly, informative "
    "tone aimed at everyday car owners and shoppers -- not gearheads. Use web search to "
    "ground any facts, prices, or model-year details in current reality.\n\n"
    "Once you're done researching, output the article using EXACTLY this plain-text format "
    "(no JSON, no markdown code fences, no <cite> tags or citation markers -- write facts "
    "directly into the sentences):\n\n"
    "TITLE: <a punchy SEO-friendly headline>\n"
    "META: <one sentence meta description, under 160 characters>\n"
    "TAGS: <3-6 lowercase tags, comma-separated>\n"
    "IMAGE_QUERY: <a short 2-5 word stock photo search phrase>\n"
    "---ARTICLE---\n"
    "<the full 500-900 word article body as clean HTML, using <p>, <h2>, <h3>, <ul>/<li> as "
    "appropriate. No <html>/<body> wrapper, no title heading repeated as h1.>\n"
    "---END---\n\n"
    "You may write research notes or commentary before the TITLE: line if you need to think "
    "out loud -- that's fine, it will be discarded. But everything from TITLE: onward must "
    "follow the exact format above, and the article must always be closed with a line that "
    "says exactly ---END--- as the very last thing you write."
)


def _extract_article(raw):
    """Pulls the structured fields out of the model's plain-text response. Returns None
    if the ---END--- marker is missing (response was truncated)."""
    if "---END---" not in raw:
        return None

    title_m = re.search(r"^TITLE:\s*(.+)$", raw, re.MULTILINE)
    meta_m = re.search(r"^META:\s*(.+)$", raw, re.MULTILINE)
    tags_m = re.search(r"^TAGS:\s*(.+)$", raw, re.MULTILINE)
    image_m = re.search(r"^IMAGE_QUERY:\s*(.+)$", raw, re.MULTILINE)
    article_m = re.search(r"---ARTICLE---\s*\n(.*?)\n---END---", raw, re.DOTALL)

    if not all([title_m, meta_m, tags_m, image_m, article_m]):
        return None

    content_html = article_m.group(1).strip()
    # Defense in depth: strip any <cite> tags the model added anyway, keeping the inner text.
    content_html = re.sub(r"<cite[^>]*>(.*?)</cite>", r"\1", content_html, flags=re.DOTALL)

    return {
        "title": title_m.group(1).strip(),
        "meta_description": meta_m.group(1).strip(),
        "tags": [t.strip().lower() for t in tags_m.group(1).split(",") if t.strip()],
        "image_query": image_m.group(1).strip(),
        "content_html": content_html,
    }


def generate_article(topic):
    """Calls the Anthropic API (with web search) to research and write the post.
    Automatically continues the generation if the response gets cut off mid-article."""
    messages = [{"role": "user", "content": f"Write today's article. Topic: {topic}"}]

    data = _call_claude(messages)
    text_parts = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    raw = "\n".join(text_parts)

    # If the model got cut off before writing ---END---, ask it to continue exactly
    # where it left off, then stitch the two responses together. Try this once.
    if data.get("stop_reason") == "max_tokens" or "---END---" not in raw:
        log("Response looked cut off -- requesting continuation...")
        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (
                "Continue exactly where you left off, with no repetition and no "
                "re-introduction -- pick up mid-sentence if needed. Make sure to still "
                "close with ---END--- when the article is complete."
            ),
        })
        data2 = _call_claude(messages)
        text_parts2 = [b["text"] for b in data2.get("content", []) if b.get("type") == "text"]
        raw = raw + "\n" + "\n".join(text_parts2)

    article = _extract_article(raw)
    if article is None:
        raise RuntimeError(
            "Could not find a complete, correctly-formatted article in the model's "
            f"output even after a continuation attempt.\n---\n{raw[:3000]}"
        )
    if not article["title"] or not article["content_html"]:
        raise RuntimeError(f"Article fields came back empty. Raw output:\n---\n{raw[:3000]}")

    return article


# ---------------------------------------------------------------------------
# Free image sourcing
# ---------------------------------------------------------------------------

def fetch_image_pexels(query):
    if not PEXELS_API_KEY:
        return None
    r = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": PEXELS_API_KEY},
        params={"query": query, "per_page": 5, "orientation": "landscape"},
        timeout=30,
    )
    if r.status_code != 200:
        return None
    photos = r.json().get("photos", [])
    if not photos:
        return None
    photo = random.choice(photos)
    img_url = photo["src"]["large"]
    img_bytes = requests.get(img_url, timeout=30).content
    return img_bytes, photo.get("photographer", "Pexels")


def fetch_image_openverse(query):
    """Fallback: Openverse, filtered to CC0 / public-domain-equivalent so no attribution is required."""
    r = requests.get(
        "https://api.openverse.org/v1/images/",
        params={"q": query, "license": "cc0", "page_size": 5},
        timeout=30,
    )
    if r.status_code != 200:
        return None
    results = r.json().get("results", [])
    if not results:
        return None
    img = random.choice(results)
    img_bytes = requests.get(img["url"], timeout=30).content
    return img_bytes, img.get("creator", "Openverse")


def fetch_free_image(query):
    result = fetch_image_pexels(query)
    if result:
        return result
    log("Pexels had no match (or no API key set) -- trying Openverse fallback.")
    result = fetch_image_openverse(query)
    if result:
        return result
    log("No free image found for this query. Post will publish without a featured image.")
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Generate everything but don't touch WordPress")
    args = parser.parse_args()

    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not args.dry_run:
        if not WP_USERNAME:
            missing.append("WP_USERNAME")
        if not WP_APP_PASSWORD:
            missing.append("WP_APP_PASSWORD")
    if missing:
        log(f"Missing required environment variables: {', '.join(missing)}. See .env.example.")
        sys.exit(1)

    wp = WordPressClient(WP_BASE_URL, WP_USERNAME, WP_APP_PASSWORD) if not args.dry_run else None

    state = load_state()
    existing_titles = wp.get_recent_titles() if wp else []

    log("Checking what's currently trending in the auto industry...")
    trending = find_trending_topic(existing_titles)
    if trending:
        topic, category_name = trending
        state["used_topics"].append(topic)
        save_state(state)
        log(f"Using trending topic: {topic}  (category: {category_name})")
    else:
        topic, category_name = pick_topic(state, existing_titles)
        log(f"Using fallback topic: {topic}  (category: {category_name})")

    log("Generating article with Claude...")
    article = generate_article(topic)
    log(f"Generated title: {article['title']}")

    log(f"Sourcing free image for query: {article['image_query']}")
    image_result = fetch_free_image(article["image_query"])

    if args.dry_run:
        log("--- DRY RUN OUTPUT ---")
        print(json.dumps(article, indent=2))
        print(f"Image found: {'yes' if image_result else 'no'}")
        return

    category_id = wp.get_or_create_category(category_name)
    tag_ids = [wp.get_or_create_tag(t) for t in article["tags"]]

    featured_media_id = None
    if image_result:
        img_bytes, credit = image_result
        slug = article["title"].lower().replace(" ", "-")[:40]
        featured_media_id = wp.upload_media(img_bytes, f"{slug}.jpg", alt_text=article["title"])
        log(f"Uploaded image (credit: {credit}), media id {featured_media_id}")

    post = wp.create_post(
        title=article["title"],
        content_html=article["content_html"],
        category_ids=[category_id],
        tag_ids=tag_ids,
        featured_media=featured_media_id,
        status=PUBLISH_STATUS,
        meta_description=article.get("meta_description"),
    )
    log(f"Post created: {post.get('link', post.get('id'))} (status: {PUBLISH_STATUS})")


if __name__ == "__main__":
    main()
