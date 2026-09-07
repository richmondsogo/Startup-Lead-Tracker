#!/usr/bin/env python3
"""
startup_lead_scanner.py

Scans a few public sources for startups that just launched or just raised
money, pulls out the company's own website domain where it can find one,
and writes a CSV of leads with guessed contact-email addresses so you can
review and send outreach manually (or verify the emails with a tool like
Hunter.io before sending).

SOURCES INCLUDED (all free, no API key, no login):
  1. Techpoint Africa RSS feed   -> filtered for funding/launch keywords
  2. TechCabal RSS feed          -> filtered for funding/launch keywords
  3. "Show HN" posts on Hacker News (via the free Algolia HN Search API)
     -> these are solo devs / small startups posting their own new product,
        globally, not Africa-specific. The HN item usually links straight
        to the product's own site, which is the cleanest domain source
        of the three.

WHAT THIS DOES NOT DO (be honest with yourself about this before relying
on it):
  - It does NOT scan ycombinator.com/launches or Indie Hackers directly.
    Both are JavaScript-rendered pages without a public feed/API, so a
    reliable scraper for them needs a browser-automation tool (Playwright)
    and will break more often as the sites change. That's a fine "phase 2"
    if you want it, but it's a genuinely different level of complexity
    than the RSS-based sources here, so it's left out of this first pass.
  - It does NOT verify that the guessed emails are real. It only builds
    plausible addresses (hello@, info@, founders@, etc.) from the
    company's own domain. Verify before high-volume sending, e.g. with
    Hunter.io's free tier, or just check the company's own "contact" page.
  - RSS/HTML structure can change over time. If a source suddenly returns
    zero results, that's the first thing to check (open the feed URL in
    a browser and see if it still looks like normal RSS).

USAGE:
    python3 startup_lead_scanner.py                # last 2 days, default
    python3 startup_lead_scanner.py --days 1        # last 1 day
    python3 startup_lead_scanner.py --days 7        # last 7 days
    python3 startup_lead_scanner.py --out myfile.csv

Run it daily (cron, Task Scheduler, or just manually) -- it dedupes
against what's already in the CSV, so re-running is safe and additive.

DEPENDENCIES:
    pip install feedparser requests --break-system-packages
"""

import argparse
import csv
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import feedparser
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FUNDING_KEYWORDS = [
    "raises",
    "raised",
    "secures",
    "funding",
    "seed round",
    "series a",
    "series b",
    "pre-seed",
    "investment",
    "backed by",
]
LAUNCH_KEYWORDS = [
    "launches",
    "launch",
    "unveils",
    "introduces",
    "debuts",
    "rolls out",
]

# Domains we never want to treat as "the company's own site" even if they
# show up in an article -- these are the publishers themselves, social
# platforms, or generic code/hosting platforms that are never the actual
# company's own domain (this was the bug: github.com is not Engrim's site,
# it's just where the code lives).
GENERIC_EXCLUDE_DOMAINS = {
    "techpoint.africa",
    "techcabal.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "bit.ly",
    "t.co",
    "wa.me",
    "wordpress.com",
    "medium.com",
    "github.com",
    "github.io",
    "gitlab.com",
    "bitbucket.org",
    "huggingface.co",
    "vercel.app",
    "netlify.app",
    "herokuapp.com",
    "npmjs.com",
    "pypi.org",
    "producthunt.com",
    "news.ycombinator.com",
    "discord.gg",
    "discord.com",
    "reddit.com",
    "notion.site",
}

GITHUB_API_BASE = "https://api.github.com/users/"

EMAIL_PREFIXES = ["hello", "hi", "info", "team", "founders", "contact"]

RSS_SOURCES = [
    {"name": "Techpoint Africa", "url": "https://techpoint.africa/feed"},
    {"name": "TechCabal", "url": "https://techcabal.com/feed"},
]

HN_ALGOLIA_URL = "http://hn.algolia.com/api/v1/search_by_date"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def cutoff_datetime(days_back):
    return datetime.now(timezone.utc) - timedelta(days=days_back)


def matches_keywords(text, keywords):
    text = text.lower()
    return any(kw in text for kw in keywords)


def extract_links_from_html(html_snippet):
    if not html_snippet:
        return []
    return re.findall(r'href=["\']([^"\']+)["\']', html_snippet)


def find_contact_from_links(links):
    """Walk a list of candidate links, return the first real, non-generic
    company domain. If every link is a generic platform but one of them
    was a GitHub repo, fall back to resolving the repo owner's public
    profile (blog/email/twitter) instead of giving up entirely."""
    github_link = None
    for link in links:
        try:
            domain = urlparse(link).netloc.lower().replace("www.", "")
        except Exception:
            continue
        if not domain:
            continue
        if "github.com" in domain and github_link is None:
            github_link = link
        if any(bad in domain for bad in GENERIC_EXCLUDE_DOMAINS):
            continue
        return {"domain": domain}

    if github_link:
        return resolve_github_owner_contact(github_link)
    return {}


def resolve_github_owner_contact(url):
    """When the only link we have is a GitHub repo (common for Show HN dev
    tools), the repo owner's public GitHub profile often has a real
    website, email, or Twitter handle. This turns a dead end (github.com
    is not the company) into an actual usable contact channel."""
    match = re.search(r"github\.com/([^/]+)/?", url)
    if not match:
        return {}
    owner = match.group(1)

    try:
        resp = requests.get(
            GITHUB_API_BASE + owner,
            headers={
                "User-Agent": "startup-lead-scanner",
                "Accept": "application/vnd.github+json",
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return {"github_profile": f"https://github.com/{owner}"}
        data = resp.json()
    except Exception:
        return {"github_profile": f"https://github.com/{owner}"}

    result = {"github_profile": f"https://github.com/{owner}"}

    blog = (data.get("blog") or "").strip()
    if blog:
        if not blog.startswith("http"):
            blog = "https://" + blog
        blog_domain = urlparse(blog).netloc.lower().replace("www.", "")
        if blog_domain and not any(
            bad in blog_domain for bad in GENERIC_EXCLUDE_DOMAINS
        ):
            result["domain"] = blog_domain

    if data.get("email"):
        result["public_email"] = data["email"]

    if data.get("twitter_username"):
        result["twitter"] = f"https://twitter.com/{data['twitter_username']}"

    return result


def guess_emails(domain):
    if not domain:
        return []
    return [f"{prefix}@{domain}" for prefix in EMAIL_PREFIXES]


def clean_company_guess(title):
    """Very rough company-name guess from a headline. Good enough to help
    you scan the CSV, not meant to be perfect -- read the article link for
    the real name if it matters."""
    title = re.split(r"[-–—:]", title)[0]
    title = re.sub(
        r"\b(raises|secures|launches|unveils|introduces|debuts)\b.*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip()


# ---------------------------------------------------------------------------
# Source scanners
# ---------------------------------------------------------------------------


def scan_rss_source(source, days_back):
    leads = []
    cutoff = cutoff_datetime(days_back)
    feed = feedparser.parse(source["url"])

    for entry in feed.entries:
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        if published:
            published_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if published_dt < cutoff:
                continue

        title = entry.get("title", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        haystack = f"{title} {summary}"

        if not matches_keywords(haystack, FUNDING_KEYWORDS + LAUNCH_KEYWORDS):
            continue

        contact = find_contact_from_links(extract_links_from_html(summary))
        domain = contact.get("domain")
        other_bits = []
        if contact.get("public_email"):
            other_bits.append(contact["public_email"])
        if contact.get("github_profile"):
            other_bits.append(contact["github_profile"])
        if contact.get("twitter"):
            other_bits.append(contact["twitter"])

        leads.append(
            {
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": source["name"],
                "company_guess": clean_company_guess(title),
                "headline": title,
                "domain": domain or "",
                "guessed_emails": ", ".join(guess_emails(domain)),
                "other_contact": "; ".join(other_bits),
                "article_link": entry.get("link", ""),
            }
        )

    return leads


def scan_show_hn(days_back):
    leads = []
    cutoff_ts = int(cutoff_datetime(days_back).timestamp())
    params = {
        "tags": "show_hn",
        "numericFilters": f"created_at_i>{cutoff_ts}",
        "hitsPerPage": 100,
    }
    try:
        resp = requests.get(HN_ALGOLIA_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Show HN] request failed: {e}")
        return leads

    for hit in data.get("hits", []):
        title = hit.get("title", "")
        url = hit.get("url") or ""

        contact = find_contact_from_links([url]) if url else {}
        domain = contact.get("domain")
        other_bits = []
        if contact.get("public_email"):
            other_bits.append(contact["public_email"])
        if contact.get("github_profile"):
            other_bits.append(contact["github_profile"])
        if contact.get("twitter"):
            other_bits.append(contact["twitter"])

        leads.append(
            {
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": "Show HN",
                "company_guess": clean_company_guess(title.replace("Show HN:", "")),
                "headline": title,
                "domain": domain or "",
                "guessed_emails": ", ".join(guess_emails(domain)),
                "other_contact": "; ".join(other_bits),
                "article_link": f"https://news.ycombinator.com/item?id={hit.get('objectID','')}",
            }
        )

    return leads


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# article_link is LAST on purpose: some editors/terminals auto-linkify
# URLs and don't treat a bare comma as a hard stop, so a URL followed by
# more text on the same line can render as one broken, swallowed link.
# Putting it last means nothing ever follows it on the line.
FIELDNAMES = [
    "found_at",
    "source",
    "company_guess",
    "headline",
    "domain",
    "guessed_emails",
    "other_contact",
    "article_link",
]


def load_existing_links(csv_path):
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and reader.fieldnames != FIELDNAMES:
            print(
                f"WARNING: {csv_path} was written by an older version of this "
                f"script (different columns). Appending would misalign the "
                f"data. Rename or delete the old file and re-run -- your old "
                f"rows are still safe in the renamed file, nothing is deleted."
            )
            raise SystemExit(1)
        return {row["article_link"] for row in reader if row.get("article_link")}


def append_leads(csv_path, leads):
    existing_links = load_existing_links(csv_path)
    new_leads = [l for l in leads if l["article_link"] not in existing_links]

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for lead in new_leads:
            writer.writerow(lead)

    return new_leads


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Scan for fresh startup leads.")
    parser.add_argument(
        "--days", type=int, default=2, help="How many days back to look (default: 2)"
    )
    parser.add_argument(
        "--out",
        type=str,
        default="leads.csv",
        help="CSV file to append results to (default: leads.csv)",
    )
    args = parser.parse_args()

    all_leads = []

    for source in RSS_SOURCES:
        print(f"Scanning {source['name']}...")
        all_leads += scan_rss_source(source, args.days)

    print("Scanning Show HN...")
    all_leads += scan_show_hn(args.days)

    new_leads = append_leads(args.out, all_leads)

    print(f"\nFound {len(all_leads)} matching items, {len(new_leads)} new.")
    print(f"Saved to {args.out}")
    with_domain = [l for l in new_leads if l["domain"]]
    print(f"{len(with_domain)} of the new leads have a guessed domain/email.")


if __name__ == "__main__":
    main()
