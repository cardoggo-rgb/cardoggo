#!/usr/bin/env python3
"""
Yoast SEO Backfill Script
==========================
A ONE-TIME (or occasional) script that goes through your EXISTING WordPress
posts and fills in missing Yoast fields (focus keyphrase, meta description,
SEO title) using Claude to analyze each post's actual content.

This is separate from agent.py on purpose -- agent.py runs daily and only
touches NEW posts it creates. This script only touches OLD posts that are
missing Yoast data, and is safe to re-run any time (it skips posts that
already have a focus keyphrase set, so running it twice won't waste API
calls or overwrite anything).

Requires the same .env setup as agent.py, plus the REST-exposure snippet
from YOAST_SEO_SETUP.md (all three fields) must be installed on WordPress,
or this script's changes will be silently ignored by WordPress.

Usage:
    python3 backfill_yoast.py --dry-run     # see what it WOULD do, no changes
    python3 backfill_yoast.py               # actually apply changes
    python3 backfill_yoast.py --limit 5     # only process the first 5 posts
                                             # (good for testing before a full run)
"""

import os
import re
import sys
import time
import base64
import argparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

WP_BASE_URL = os.environ.get("WP_BASE_URL", "https://cardoggo.com").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def log(msg):
    print(f"[backfill] {msg}")


class WP:
    def __init__(self, base_url, username, app_password):
        self.api = f"{base_url}/wp-json/wp/v2"
        token = base64.b64encode(f"{username}:{app_password}".encode()).decode()
        self.headers = {"Authorization": f"Basic {token}"}

    def list_all_posts(self):
        """Fetch every post with its content and current Yoast meta (if exposed)."""
        posts = []
        page = 1
        while True:
            r = requests.get(
                f"{self.api}/posts",
                headers=self.headers,
                params={
                    "per_page": 50,
                    "page": page,
                    "_fields": "id,title,link,content,meta",
                },
                timeout=30,
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            posts.extend(batch)
            if len(batch) < 50:
                break
            page += 1
        return posts

    def update_post_meta(self, post_id, keyphrase, meta_description, seo_title):
        payload = {
            "meta": {
                "_yoast_wpseo_focuskw": keyphrase,
                "_yoast_wpseo_metadesc": meta_description,
                "_yoast_wpseo_title": seo_title,
            }
        }
        r = requests.patch(f"{self.api}/posts/{post_id}", headers=self.headers, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()


def strip_html(html):
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def analyze_post(title, plain_text_content):
    """Asks Claude to read the existing post and propose Yoast fields for it.
    No web search needed here -- just analyzing content that already exists."""
    excerpt = plain_text_content[:3000]  # plenty for the model to work from
    prompt = (
        f"Here is an existing blog post from CarDoggo, an automotive blog.\n\n"
        f"TITLE: {title}\n\n"
        f"CONTENT:\n{excerpt}\n\n"
        "Based on this actual content, propose SEO metadata for it. Respond with "
        "ONLY these three lines, nothing else:\n"
        "KEYPHRASE: <a specific 2-4 word focus keyphrase this post should rank for, "
        "based on what it actually covers>\n"
        "META: <a one-sentence meta description under 150 characters that includes "
        "the keyphrase and accurately summarizes THIS post>\n"
        "SEO_TITLE: <an SEO title under 60 characters, starting with the keyphrase, "
        "based on the existing title but tightened if needed>"
    )
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": ANTHROPIC_MODEL,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    text = "\n".join(b["text"] for b in data.get("content", []) if b.get("type") == "text")

    keyphrase_m = re.search(r"^KEYPHRASE:\s*(.+)$", text, re.MULTILINE)
    meta_m = re.search(r"^META:\s*(.+)$", text, re.MULTILINE)
    title_m = re.search(r"^SEO_TITLE:\s*(.+)$", text, re.MULTILINE)

    if not all([keyphrase_m, meta_m, title_m]):
        raise RuntimeError(f"Could not parse model response:\n{text}")

    return {
        "keyphrase": keyphrase_m.group(1).strip(),
        "meta_description": meta_m.group(1).strip(),
        "seo_title": title_m.group(1).strip(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Show what would change, without writing anything")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N posts needing backfill")
    args = parser.parse_args()

    missing = [n for n, v in [("WP_USERNAME", WP_USERNAME), ("WP_APP_PASSWORD", WP_APP_PASSWORD),
                               ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)] if not v]
    if missing:
        log(f"Missing required environment variables: {', '.join(missing)}")
        sys.exit(1)

    wp = WP(WP_BASE_URL, WP_USERNAME, WP_APP_PASSWORD)
    log("Fetching all posts...")
    posts = wp.list_all_posts()
    log(f"Found {len(posts)} total posts.")

    needing_backfill = [p for p in posts if not (p.get("meta") or {}).get("_yoast_wpseo_focuskw")]
    log(f"{len(needing_backfill)} posts are missing a focus keyphrase (need backfill).")

    if args.limit:
        needing_backfill = needing_backfill[: args.limit]
        log(f"Limiting this run to {len(needing_backfill)} posts.")

    for i, post in enumerate(needing_backfill, 1):
        title = post["title"]["rendered"]
        log(f"[{i}/{len(needing_backfill)}] {title}")

        plain_text = strip_html(post["content"]["rendered"])
        if len(plain_text) < 50:
            log("  Skipping -- post body looks empty or too short to analyze.")
            continue

        try:
            fields = analyze_post(title, plain_text)
        except Exception as e:
            log(f"  Skipped due to error: {e}")
            continue

        log(f"  Keyphrase: {fields['keyphrase']}")
        log(f"  SEO title: {fields['seo_title']}")
        log(f"  Meta: {fields['meta_description']}")

        if not args.dry_run:
            wp.update_post_meta(post["id"], fields["keyphrase"], fields["meta_description"], fields["seo_title"])
            log("  Saved.")
            time.sleep(1)  # be gentle on both APIs
        else:
            log("  (dry run -- not saved)")

    log("Done.")


if __name__ == "__main__":
    main()
