#!/usr/bin/env python3
"""
Startup Lead Tracker (V2 - Active Hiring Intent & Scoring Engine)

Scans public sources for startups, founders, and hiring managers with active
intent for contract, freelance, and automation work (tailored for Python,
scraping, bot, and LLM/automation gigs).

SOURCES INCLUDED (all free, no API key, no login required):
  1. Hacker News "Ask HN: Who is hiring?" monthly thread (top-level job posts)
  2. Hacker News "Ask HN: Seeking freelancer?" monthly thread (hiring clients)
  3. Hacker News Targeted Hiring comments (real-time developer searches)
  4. Hacker News "Show HN" posts (fresh products and solo founders)
  5. Reddit Public Hiring RSS feeds (r/forhire, r/jobbit, r/SideProject)
  6. (Optional) African Tech News RSS feeds (Techpoint, TechCabal via --include-news)

SCORING ENGINE (0 - 100 pts):
  - Intent Strength (Max 35 pts): Contract/freelance posts score highest (+35)
  - Skill/Stack Fit (Max 30 pts): Python, scraping, bots, AI/LLM, automation (+15 to +30)
  - Stage & Team Size (Max 20 pts): Solo founders, seed, small teams (+20), enterprise (-20)
  - Budget Plausibility (Max 15 pts): Sweet spot $100-$500 / $20-$50/hr (+15), unpaid (-15)

CSV SCHEMA (article_link is strictly last):
  score,score_breakdown,intent_type,found_at,source,company_or_author,title_or_role,domain,guessed_emails,other_contact,summary_snippet,article_link
"""

import argparse
import csv
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from html import unescape
from urllib.parse import urlparse

import feedparser
import requests

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

DEFAULT_DAYS_BACK = 7
DEFAULT_MIN_SCORE = 20
DEFAULT_CSV_PATH = "leads.csv"

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
    "google.com",
    "forms.gle",
    "substack.com",
}

GITHUB_API_BASE = "https://api.github.com/users/"

EMAIL_PREFIXES = ["hello", "hi", "info", "team", "founders", "contact", "jobs"]

HN_ALGOLIA_SEARCH_DATE = "https://hn.algolia.com/api/v1/search_by_date"
HN_ALGOLIA_SEARCH = "https://hn.algolia.com/api/v1/search"

HTTP_TIMEOUT = 12
DEFAULT_HEADERS = {
    "User-Agent": "StartupLeadTracker/2.0 (lead-generation-automation; +https://github.com)"
}
REDDIT_HEADERS = {
    "User-Agent": "python:StartupLeadTracker:v2.0 (by /u/dev_lead_tracker)"
}

NEWS_RSS_SOURCES = [
    {"name": "Techpoint Africa", "url": "https://techpoint.africa/feed"},
    {"name": "TechCabal", "url": "https://techcabal.com/feed"},
]

NEWS_FUNDING_KEYWORDS = [
    "raises", "raised", "secures", "funding", "seed round",
    "series a", "series b", "pre-seed", "investment", "backed by",
]
NEWS_LAUNCH_KEYWORDS = [
    "launches", "launch", "unveils", "introduces", "debuts", "rolls out",
]

FIELDNAMES = [
    "score",
    "score_breakdown",
    "intent_type",
    "found_at",
    "source",
    "company_or_author",
    "title_or_role",
    "domain",
    "guessed_emails",
    "other_contact",
    "summary_snippet",
    "article_link",
]

# ---------------------------------------------------------------------------
# Helpers & Contact Resolution
# ---------------------------------------------------------------------------

def cutoff_datetime(days_back):
    return datetime.now(timezone.utc) - timedelta(days=days_back)


def clean_html_text(html_content):
    if not html_content:
        return ""
    text = unescape(html_content)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_links_from_text(text_or_html):
    if not text_or_html:
        return []
    # Match href attributes or raw http/https links
    href_links = re.findall(r'href=["\']([^"\']+)["\']', text_or_html, re.IGNORECASE)
    raw_links = re.findall(r'https?://[^\s<>"\'\)]+', text_or_html)
    all_links = []
    for link in href_links + raw_links:
        link = link.strip().rstrip(".,;)>")
        if link and link not in all_links:
            all_links.append(link)
    return all_links


def extract_direct_emails(text):
    if not text:
        return []
    # Exclude common image extensions or fake matches
    matches = re.findall(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text)
    valid = []
    for email in matches:
        email = email.lower().strip(".")
        domain = email.split("@")[-1]
        if domain.endswith(("png", "jpg", "jpeg", "gif", "webp", "svg", "example.com")):
            continue
        if email not in valid:
            valid.append(email)
    return valid


def guess_emails(domain):
    if not domain:
        return []
    return [f"{prefix}@{domain}" for prefix in EMAIL_PREFIXES]


def resolve_github_owner_contact(url):
    match = re.search(r"github\.com/([^/]+)/?", url)
    if not match:
        return {}
    owner = match.group(1).strip()
    if not owner or owner.lower() in ["topics", "features", "explore"]:
        return {}

    result = {"github_profile": f"https://github.com/{owner}"}
    try:
        resp = requests.get(
            GITHUB_API_BASE + owner,
            headers={
                "User-Agent": "StartupLeadTracker/2.0",
                "Accept": "application/vnd.github+json",
            },
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            blog = (data.get("blog") or "").strip()
            if blog:
                if not blog.startswith("http"):
                    blog = "https://" + blog
                blog_domain = urlparse(blog).netloc.lower().replace("www.", "")
                if blog_domain and not any(bad in blog_domain for bad in GENERIC_EXCLUDE_DOMAINS):
                    result["domain"] = blog_domain
            if data.get("email"):
                result["public_email"] = data["email"]
            if data.get("twitter_username"):
                result["twitter"] = f"https://twitter.com/{data['twitter_username']}"
    except Exception:
        pass
    return result


def find_contact_from_links(links):
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


def clean_company_guess(title):
    title = re.split(r"[-–—:|]", title)[0]
    title = re.sub(
        r"\b(raises|secures|launches|unveils|introduces|debuts|rolls out)\b.*",
        "",
        title,
        flags=re.IGNORECASE,
    )
    return title.strip()

# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

def calculate_lead_score(lead):
    title = lead.get("title_or_role", "")
    snippet = lead.get("summary_snippet", "")
    full_text = f"{title} {snippet}".lower()
    intent_type = lead.get("intent_type", "discovery")
    source = lead.get("source", "").lower()

    # 1. Intent Score (Max 35 pts)
    intent_score = 5
    contract_intent_patterns = [
        r"\bseeking freelancer\b",
        r"\[hiring\]",
        r"\bcontract\b",
        r"\bfreelance\b",
        r"\bpart-time\b",
        r"\bpart time\b",
        r"\blooking to hire\b",
        r"\bneed a freelancer\b",
        r"\bhiring a contractor\b",
        r"\bgig\b",
        r"\bbounty\b",
    ]
    if intent_type == "contract_hiring" or any(re.search(p, full_text) for p in contract_intent_patterns):
        intent_score = 35
    elif intent_type == "fulltime_hiring" or "who is hiring" in source:
        intent_score = 20
    elif intent_type == "help_wanted" or any(
        p in full_text for p in ["looking for help", "need help", "collaborator", "co-founder", "looking for developer"]
    ):
        intent_score = 15
    elif intent_type == "discovery":
        intent_score = 5

    # 2. Skill & Stack Relevance (Max 30 pts, Min -10 pts)
    tier1_keywords = [
        "python", "scraping", "scraper", "scrape", "crawler", "crawl",
        "automation", "automate", "bot", "ai", "llm", "gemini", "openai",
        "gpt", "fastapi", "flask", "django", "data extraction", "pipeline",
        "etl", "playwright", "selenium", "beautifulsoup", "bs4", "scripting",
        "script",
    ]
    tier2_keywords = [
        "backend", "api", "full-stack", "fullstack", "database", "sqlite",
        "postgres", "postgresql", "sql", "docker", "aws", "linux",
    ]
    disjoint_keywords = [
        "swift", "ios", "kotlin", "android", "react native", "rust kernel",
        "embedded c", "solidity", "smart contract",
    ]

    tier1_hits = sum(1 for kw in tier1_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text))
    tier2_hits = sum(1 for kw in tier2_keywords if re.search(r"\b" + re.escape(kw) + r"\b", full_text))

    skill_score = 0
    if tier1_hits >= 3:
        skill_score = 30
    elif tier1_hits == 2:
        skill_score = 22
    elif tier1_hits == 1:
        skill_score = 15

    if tier2_hits >= 2:
        skill_score = min(30, skill_score + 10)
    elif tier2_hits == 1:
        skill_score = min(30, skill_score + 5)

    if tier1_hits == 0 and any(re.search(r"\b" + re.escape(kw) + r"\b", full_text) for kw in disjoint_keywords):
        skill_score = -10

    # 3. Stage & Team Size Fit (Max 20 pts, Min -20 pts)
    small_stage_patterns = [
        r"\bsolo founder\b", r"\bbootstrapped\b", r"\bpre-seed\b", r"\bseed\b",
        r"\bsmall team\b", r"\bindie hacker\b", r"<10 people", r"1-5 people",
        r"\bside project\b", r"\bearly stage\b", r"\bmvp\b", r"\bstealth\b",
    ]
    enterprise_patterns = [
        r"\bseries [b-f]\b", r"\b100\+\s*employees\b", r"\b50\+\s*employees\b",
        r"\benterprise\b", r"\bfortune 500\b", r"\bdirector of\b", r"\bvp of\b",
    ]

    stage_score = 5
    if any(re.search(p, full_text) for p in small_stage_patterns):
        stage_score = 20
    elif any(re.search(p, full_text) for p in enterprise_patterns):
        stage_score = -20

    # 4. Budget Plausibility (Max 15 pts, Min -15 pts)
    budget_score = 0
    unpaid_patterns = [
        r"\bunpaid\b", r"\bequity-only\b", r"\bequity only\b", r"\bfree internship\b",
        r"\bno pay\b", r"\bvolunteer\b", r"\bno salary\b",
    ]
    sweet_budget_patterns = [
        r"\$[1-9][0-9]{2}\b",        # $100 - $999
        r"\$[1-5][0-9]\s*/\s*hr",    # $10 - $59 /hr
        r"\bhourly rate\b", r"\bstipend\b", r"\bfixed price\b", r"\bbounty\b",
        r"\b200/month\b", r"\b200/mo\b", r"\b250\b",
    ]

    if any(re.search(p, full_text) for p in unpaid_patterns):
        budget_score = -15
    elif any(re.search(p, full_text) for p in sweet_budget_patterns):
        budget_score = 15
    elif "who is hiring" in source or "funding" in full_text:
        budget_score = 5

    total_score = max(0, min(100, intent_score + skill_score + stage_score + budget_score))
    breakdown = f"Intent:{intent_score}|Skill:{skill_score}|Stage:{stage_score}|Budget:{budget_score}"
    return total_score, breakdown

# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def scan_hn_who_is_hiring(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)
    cutoff_ts = int(cutoff_dt.timestamp())

    try:
        r = requests.get(
            HN_ALGOLIA_SEARCH_DATE,
            params={
                "tags": "story,author_whoishiring",
                "query": "Who is hiring?",
                "hitsPerPage": 1,
            },
            headers=DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        stories = r.json().get("hits", [])
        if not stories:
            return leads
        story = stories[0]
        story_id = story["objectID"]
    except Exception as e:
        print(f"  [HN Who is hiring] Failed to fetch thread ID: {e}")
        return leads

    try:
        c_resp = requests.get(
            HN_ALGOLIA_SEARCH,
            params={
                "tags": f"comment,story_{story_id}",
                "numericFilters": f"created_at_i>={cutoff_ts}",
                "hitsPerPage": 1000,
            },
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        c_resp.raise_for_status()
        comments = c_resp.json().get("hits", [])
    except Exception as e:
        print(f"  [HN Who is hiring] Failed to fetch comments: {e}")
        return leads

    for comment in comments:
        # Only top-level posts in this thread are actual job postings
        if comment.get("parent_id") != int(story_id):
            continue

        raw_html = comment.get("comment_text") or ""
        clean_text = clean_html_text(raw_html)
        if not clean_text:
            continue

        first_line = clean_text.split(". ")[0].split("\n")[0].strip()
        parts = [p.strip() for p in first_line.split("|")]
        company_guess = parts[0] if parts else "Unknown Company"
        role_guess = " | ".join(parts[1:]) if len(parts) > 1 else first_line

        # Check intent (contract/part-time vs full-time)
        is_contract = any(w in first_line.lower() for w in ["contract", "part-time", "part time", "freelance"])
        intent = "contract_hiring" if is_contract else "fulltime_hiring"

        links = extract_links_from_text(raw_html)
        contact = find_contact_from_links(links)
        domain = contact.get("domain", "")

        direct_emails = extract_direct_emails(clean_text)
        other_bits = []
        if contact.get("public_email"):
            other_bits.append(contact["public_email"])
        for de in direct_emails:
            if de not in other_bits:
                other_bits.append(de)
        if contact.get("github_profile"):
            other_bits.append(contact["github_profile"])
        if contact.get("twitter"):
            other_bits.append(contact["twitter"])

        lead = {
            "intent_type": intent,
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "HN Who is hiring",
            "company_or_author": company_guess,
            "title_or_role": role_guess[:150],
            "domain": domain,
            "guessed_emails": ", ".join(guess_emails(domain)),
            "other_contact": "; ".join(other_bits),
            "summary_snippet": clean_text[:350],
            "article_link": f"https://news.ycombinator.com/item?id={comment.get('objectID', '')}",
        }
        score, breakdown = calculate_lead_score(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        leads.append(lead)

    return leads


def scan_hn_seeking_freelancer(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)
    cutoff_ts = int(cutoff_dt.timestamp())

    try:
        r = requests.get(
            HN_ALGOLIA_SEARCH_DATE,
            params={
                "tags": "story,author_whoishiring",
                "query": "Seeking freelancer",
                "hitsPerPage": 1,
            },
            headers=DEFAULT_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        stories = r.json().get("hits", [])
        if not stories:
            return leads
        story = stories[0]
        story_id = story["objectID"]
    except Exception as e:
        print(f"  [HN Seeking freelancer] Failed to fetch thread ID: {e}")
        return leads

    try:
        c_resp = requests.get(
            HN_ALGOLIA_SEARCH,
            params={
                "tags": f"comment,story_{story_id}",
                "numericFilters": f"created_at_i>={cutoff_ts}",
                "hitsPerPage": 1000,
            },
            headers=DEFAULT_HEADERS,
            timeout=15,
        )
        c_resp.raise_for_status()
        comments = c_resp.json().get("hits", [])
    except Exception as e:
        print(f"  [HN Seeking freelancer] Failed to fetch comments: {e}")
        return leads

    for comment in comments:
        if comment.get("parent_id") != int(story_id):
            continue
        raw_html = comment.get("comment_text") or ""
        clean_text = clean_html_text(raw_html)
        if not clean_text:
            continue

        # We specifically want clients seeking freelancers, not freelancers offering services
        if "seeking freelancer" not in clean_text.lower() and "hiring" not in clean_text.lower():
            continue

        first_line = clean_text.split(". ")[0].split("\n")[0].strip()
        links = extract_links_from_text(raw_html)
        contact = find_contact_from_links(links)
        domain = contact.get("domain", "")

        direct_emails = extract_direct_emails(clean_text)
        other_bits = []
        if contact.get("public_email"):
            other_bits.append(contact["public_email"])
        for de in direct_emails:
            if de not in other_bits:
                other_bits.append(de)
        if contact.get("github_profile"):
            other_bits.append(contact["github_profile"])

        lead = {
            "intent_type": "contract_hiring",
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "HN Seeking Freelancer",
            "company_or_author": comment.get("author", "HN User"),
            "title_or_role": first_line[:150],
            "domain": domain,
            "guessed_emails": ", ".join(guess_emails(domain)),
            "other_contact": "; ".join(other_bits),
            "summary_snippet": clean_text[:350],
            "article_link": f"https://news.ycombinator.com/item?id={comment.get('objectID', '')}",
        }
        score, breakdown = calculate_lead_score(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        leads.append(lead)

    return leads


def scan_hn_hiring_queries(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)
    cutoff_ts = int(cutoff_dt.timestamp())

    queries = [
        "seeking freelancer",
        "looking for a developer",
        "hiring python",
        "freelance python",
    ]

    seen_ids = set()

    for q in queries:
        try:
            r = requests.get(
                HN_ALGOLIA_SEARCH_DATE,
                params={
                    "tags": "comment",
                    "query": f'"{q}"',
                    "numericFilters": f"created_at_i>={cutoff_ts}",
                    "hitsPerPage": 25,
                },
                headers=DEFAULT_HEADERS,
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
            hits = r.json().get("hits", [])
        except Exception as e:
            print(f"  [HN Query '{q}'] error: {e}")
            continue

        for hit in hits:
            obj_id = hit.get("objectID")
            if not obj_id or obj_id in seen_ids:
                continue
            seen_ids.add(obj_id)

            raw_html = hit.get("comment_text") or ""
            clean_text = clean_html_text(raw_html)
            if len(clean_text) < 30:
                continue

            links = extract_links_from_text(raw_html)
            contact = find_contact_from_links(links)
            domain = contact.get("domain", "")

            direct_emails = extract_direct_emails(clean_text)
            other_bits = []
            if contact.get("public_email"):
                other_bits.append(contact["public_email"])
            for de in direct_emails:
                if de not in other_bits:
                    other_bits.append(de)
            if contact.get("github_profile"):
                other_bits.append(contact["github_profile"])

            first_line = clean_text.split(". ")[0].split("\n")[0].strip()
            lead = {
                "intent_type": "contract_hiring",
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": "HN Hiring Comments",
                "company_or_author": hit.get("author", "HN User"),
                "title_or_role": first_line[:150],
                "domain": domain,
                "guessed_emails": ", ".join(guess_emails(domain)),
                "other_contact": "; ".join(other_bits),
                "summary_snippet": clean_text[:350],
                "article_link": f"https://news.ycombinator.com/item?id={obj_id}",
            }
            score, breakdown = calculate_lead_score(lead)
            lead["score"] = score
            lead["score_breakdown"] = breakdown
            leads.append(lead)

    return leads


def scan_show_hn(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)
    cutoff_ts = int(cutoff_dt.timestamp())

    params = {
        "tags": "show_hn",
        "numericFilters": f"created_at_i>{cutoff_ts}",
        "hitsPerPage": 100,
    }
    try:
        resp = requests.get(HN_ALGOLIA_SEARCH_DATE, params=params, headers=DEFAULT_HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  [Show HN] request failed: {e}")
        return leads

    for hit in data.get("hits", []):
        title = hit.get("title", "")
        url = hit.get("url") or ""
        text = hit.get("story_text") or ""
        clean_desc = clean_html_text(text)

        all_candidate_links = []
        if url:
            all_candidate_links.append(url)
        all_candidate_links += extract_links_from_text(text)

        contact = find_contact_from_links(all_candidate_links)
        domain = contact.get("domain", "")

        direct_emails = extract_direct_emails(clean_desc)
        other_bits = []
        if contact.get("public_email"):
            other_bits.append(contact["public_email"])
        for de in direct_emails:
            if de not in other_bits:
                other_bits.append(de)
        if contact.get("github_profile"):
            other_bits.append(contact["github_profile"])
        if contact.get("twitter"):
            other_bits.append(contact["twitter"])

        company_guess = clean_company_guess(title.replace("Show HN:", ""))
        haystack = f"{title} {clean_desc}".lower()
        intent = "help_wanted" if any(w in haystack for w in ["looking for help", "need developer", "co-founder", "collaborator"]) else "discovery"

        lead = {
            "intent_type": intent,
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": "Show HN",
            "company_or_author": company_guess,
            "title_or_role": title,
            "domain": domain,
            "guessed_emails": ", ".join(guess_emails(domain)),
            "other_contact": "; ".join(other_bits),
            "summary_snippet": clean_desc[:350] or title,
            "article_link": f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}",
        }
        score, breakdown = calculate_lead_score(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        leads.append(lead)

    return leads


def scan_reddit_hiring(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)

    feeds = [
        {
            "name": "Reddit (r/forhire)",
            "url": "https://www.reddit.com/r/forhire/search.rss?q=flair%3AHiring+python&restrict_sr=on&sort=new&t=all",
            "intent": "contract_hiring",
        },
        {
            "name": "Reddit (r/jobbit)",
            "url": "https://www.reddit.com/r/jobbit/search.rss?q=python&restrict_sr=on&sort=new&t=all",
            "intent": "contract_hiring",
        },
        {
            "name": "Reddit (r/SideProject)",
            "url": "https://www.reddit.com/r/SideProject/new.rss",
            "intent": "discovery",
        },
    ]

    for feed_info in feeds:
        try:
            resp = requests.get(feed_info["url"], headers=REDDIT_HEADERS, timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                print(f"  [{feed_info['name']}] HTTP {resp.status_code}")
                continue
            parsed = feedparser.parse(resp.text)
        except Exception as e:
            print(f"  [{feed_info['name']}] failed: {e}")
            continue

        for entry in parsed.entries:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff_dt:
                    continue

            title = entry.get("title", "")
            summary_raw = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            clean_text = clean_html_text(summary_raw)

            # In r/SideProject, filter for keywords indicating projects or hiring/feedback
            if "SideProject" in feed_info["name"]:
                haystack = f"{title} {clean_text}".lower()
                if not any(k in haystack for k in ["python", "bot", "scraper", "automation", "api", "ai", "looking for", "feedback"]):
                    continue

            links = extract_links_from_text(summary_raw)
            contact = find_contact_from_links(links)
            domain = contact.get("domain", "")

            direct_emails = extract_direct_emails(clean_text)
            other_bits = []
            if contact.get("public_email"):
                other_bits.append(contact["public_email"])
            for de in direct_emails:
                if de not in other_bits:
                    other_bits.append(de)
            if contact.get("github_profile"):
                other_bits.append(contact["github_profile"])

            author = entry.get("author", "Reddit User")
            clean_title = title.replace("[HIRING]", "").replace("[Hiring]", "").strip()

            lead = {
                "intent_type": feed_info["intent"],
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": feed_info["name"],
                "company_or_author": author,
                "title_or_role": clean_title[:150],
                "domain": domain,
                "guessed_emails": ", ".join(guess_emails(domain)),
                "other_contact": "; ".join(other_bits),
                "summary_snippet": clean_text[:350] or clean_title,
                "article_link": entry.get("link", ""),
            }
            score, breakdown = calculate_lead_score(lead)
            lead["score"] = score
            lead["score_breakdown"] = breakdown
            leads.append(lead)

    return leads


def scan_news_sources(days_back):
    leads = []
    cutoff_dt = cutoff_datetime(days_back)

    for source in NEWS_RSS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
        except Exception as e:
            print(f"  [{source['name']}] RSS parse failed: {e}")
            continue

        for entry in feed.entries:
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff_dt:
                    continue

            title = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            haystack = f"{title} {summary}".lower()

            matches = any(kw in haystack for kw in NEWS_FUNDING_KEYWORDS + NEWS_LAUNCH_KEYWORDS)
            if not matches:
                continue

            links = extract_links_from_text(summary)
            contact = find_contact_from_links(links)
            domain = contact.get("domain", "")

            other_bits = []
            if contact.get("public_email"):
                other_bits.append(contact["public_email"])
            if contact.get("github_profile"):
                other_bits.append(contact["github_profile"])
            if contact.get("twitter"):
                other_bits.append(contact["twitter"])

            lead = {
                "intent_type": "discovery",
                "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "source": source["name"],
                "company_or_author": clean_company_guess(title),
                "title_or_role": title[:150],
                "domain": domain,
                "guessed_emails": ", ".join(guess_emails(domain)),
                "other_contact": "; ".join(other_bits),
                "summary_snippet": clean_html_text(summary)[:350],
                "article_link": entry.get("link", ""),
            }
            score, breakdown = calculate_lead_score(lead)
            lead["score"] = score
            lead["score_breakdown"] = breakdown
            leads.append(lead)

    return leads

# ---------------------------------------------------------------------------
# Output & File Management
# ---------------------------------------------------------------------------

def check_and_migrate_csv(csv_path):
    if not os.path.exists(csv_path):
        return set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            first_row = next(reader)
        except StopIteration:
            return set()

    if first_row != FIELDNAMES:
        archive_name = "leads_v1_archive.csv"
        print(
            f"\n[NOTICE] '{csv_path}' uses the previous V1 column format.\n"
            f"  -> Archiving existing file to '{archive_name}' to preserve all old data.\n"
            f"  -> Creating a fresh '{csv_path}' with V2 scoring and intent columns.\n"
        )
        shutil.copyfile(csv_path, archive_name)
        os.remove(csv_path)
        return set()

    with open(csv_path, newline="", encoding="utf-8") as f:
        dict_reader = csv.DictReader(f)
        return {row["article_link"] for row in dict_reader if row.get("article_link")}


def append_leads(csv_path, leads, min_score=0):
    existing_links = check_and_migrate_csv(csv_path)
    new_leads = [
        l for l in leads
        if l["article_link"] not in existing_links and l["score"] >= min_score
    ]

    # Sort descending by score
    new_leads.sort(key=lambda x: x["score"], reverse=True)

    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for lead in new_leads:
            writer.writerow(lead)

    return new_leads

# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scan for high-intent startup leads, freelance contracts, and automation gigs."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS_BACK,
        help=f"How many days back to search (default: {DEFAULT_DAYS_BACK})",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"Minimum score filter (0-100) for saved leads (default: {DEFAULT_MIN_SCORE})",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=DEFAULT_CSV_PATH,
        help=f"CSV file to append results to (default: {DEFAULT_CSV_PATH})",
    )
    parser.add_argument(
        "--include-news",
        action="store_true",
        help="Also scan African tech funding/launch news feeds (Techpoint, TechCabal)",
    )
    args = parser.parse_args()

    print(f"=== Startup Lead Tracker V2 (Lookback: {args.days} days, Min Score: {args.min_score}) ===")

    all_leads = []

    print("\n1. Scanning Hacker News 'Who is hiring?'...")
    hn_hiring = scan_hn_who_is_hiring(args.days)
    print(f"   Found {len(hn_hiring)} job postings.")
    all_leads += hn_hiring

    print("2. Scanning Hacker News 'Seeking freelancer?'...")
    hn_freelance = scan_hn_seeking_freelancer(args.days)
    print(f"   Found {len(hn_freelance)} freelance seeker posts.")
    all_leads += hn_freelance

    print("3. Scanning targeted Hacker News hiring comments...")
    hn_queries = scan_hn_hiring_queries(args.days)
    print(f"   Found {len(hn_queries)} direct developer searches.")
    all_leads += hn_queries

    print("4. Scanning Reddit hiring RSS feeds (r/forhire, r/jobbit, r/SideProject)...")
    reddit_leads = scan_reddit_hiring(args.days)
    print(f"   Found {len(reddit_leads)} Reddit posts.")
    all_leads += reddit_leads

    print("5. Scanning Hacker News Show HN...")
    show_hn_leads = scan_show_hn(args.days)
    print(f"   Found {len(show_hn_leads)} Show HN launches.")
    all_leads += show_hn_leads

    if args.include_news:
        print("6. Scanning African tech news feeds...")
        news_leads = scan_news_sources(args.days)
        print(f"   Found {len(news_leads)} news articles.")
        all_leads += news_leads

    new_saved = append_leads(args.out, all_leads, min_score=args.min_score)

    print("\n" + "=" * 60)
    print(f"Total leads retrieved across sources: {len(all_leads)}")
    print(f"Leads meeting min-score (>={args.min_score}) & newly saved: {len(new_saved)}")
    print(f"Output saved to: {args.out}")

    high_score = [l for l in new_saved if l["score"] >= 60]
    with_contact = [l for l in new_saved if l["domain"] or l["other_contact"]]
    print(f"High-fit leads (Score >= 60): {len(high_score)}")
    print(f"Leads with resolved contact/domain: {len(with_contact)}")

    if new_saved:
        print("\nTop 5 New Leads:")
        for idx, lead in enumerate(new_saved[:5], 1):
            contact_info = lead["other_contact"] or lead["domain"] or "No direct contact"
            print(f" {idx}. [{lead['score']} pts] {lead['company_or_author']} - {lead['title_or_role']}")
            print(f"    Source: {lead['source']} | Contact: {contact_info}")
            print(f"    Link: {lead['article_link']}")


if __name__ == "__main__":
    main()
