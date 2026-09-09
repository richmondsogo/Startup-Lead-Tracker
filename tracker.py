#!/usr/bin/env python3
"""
Startup Lead Tracker (V2 - Active Hiring Intent, Scoring & Outreach Engine)

Scans public sources for startups, founders, and hiring managers with active
intent for contract, freelance, and automation work (tailored for Python,
scraping, bot, and LLM/automation gigs).

FEATURES & INNOVATIONS:
  1. Multi-Source Active Intent: HN "Who is hiring?", "Seeking freelancer",
     real-time hiring comments, Show HN launches, and Reddit freelance RSS.
  2. 4-Factor Deterministic Scoring Engine (0 - 100 pts) evaluating Intent,
     Python Skill fit, Team stage, and Budget plausibility.
  3. Lead Date Tracking: Captures 'posted_at' (when the post was published)
     alongside 'found_at'.
  4. 1-Click Outreach Engine: Automatically crafts a tailored, high-converting
     cold pitch hook for each lead and generates a pre-filled 'quick_action'
     URL (mailto: or Reddit message compose) for instant outreach.
  5. Interactive HTML Dashboard: Automatically exports a sleek, dark-mode
     'leads.html' board with filters, real-time search, and 1-click pitch copying.
  6. Safe Deduplication & Migration: Preserves older CSV files through automated
     archival and avoids duplicates on re-runs.

CSV SCHEMA (article_link is strictly last):
  score,score_breakdown,intent_type,posted_at,found_at,source,company_or_author,title_or_role,domain,guessed_emails,other_contact,summary_snippet,tailored_pitch,quick_action,article_link
"""

import argparse
import csv
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from urllib.parse import quote, urlparse

import feedparser
import requests

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------

DEFAULT_DAYS_BACK = 7
DEFAULT_MIN_SCORE = 20
DEFAULT_CSV_PATH = "leads.csv"
DEFAULT_HTML_PATH = "leads.html"

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
    "posted_at",
    "found_at",
    "source",
    "company_or_author",
    "title_or_role",
    "domain",
    "guessed_emails",
    "other_contact",
    "summary_snippet",
    "tailored_pitch",
    "quick_action",
    "article_link",
]

# ---------------------------------------------------------------------------
# Helpers & Contact Resolution
# ---------------------------------------------------------------------------

def cutoff_datetime(days_back):
    return datetime.now(timezone.utc) - timedelta(days=days_back)


def format_date(iso_or_ts):
    if not iso_or_ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if isinstance(iso_or_ts, (int, float)):
        return datetime.fromtimestamp(iso_or_ts, tz=timezone.utc).strftime("%Y-%m-%d")
    if isinstance(iso_or_ts, str):
        return iso_or_ts.split("T")[0].strip()
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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
# Outreach Engine (Tailored Pitch & 1-Click Action Link Generator)
# ---------------------------------------------------------------------------

def generate_tailored_pitch(lead):
    author = lead.get("company_or_author", "").strip()
    title = lead.get("title_or_role", "").strip()
    snippet = lead.get("summary_snippet", "").strip()
    source = lead.get("source", "")
    intent = lead.get("intent_type", "")
    full_text = f"{title} {snippet}".lower()

    clean_author = author.replace("/u/", "").replace("u/", "").strip()
    if clean_author and clean_author not in ["Unknown Company", "HN User", "Reddit User"]:
        greeting = f"Hi {clean_author},"
    else:
        greeting = "Hi there,"

    short_title = title[:60].strip().rstrip("-:| ")

    if any(w in full_text for w in ["scraper", "scraping", "crawl", "data extraction"]):
        focus = "web scraping, crawler pipelines, and data extraction"
        offer = "I can deliver a clean, robust Python scraping script for your project within 48 hours for $150-$200."
    elif any(w in full_text for w in ["automate", "automation", "bot", "workflow"]):
        focus = "Python automation workflows and custom bot development"
        offer = "I can build a functional prototype script for your setup within 48 hours for $150-$200."
    elif any(w in full_text for w in ["ai", "llm", "vector database", "embeddings", "openai", "gemini"]):
        focus = "Python AI integrations, LLM workflows, and backend scripting"
        offer = "I can build and test a working prototype integration in 48 hours for $150-$200."
    elif intent == "contract_hiring":
        focus = "Python backend development, API integration, and scripting"
        offer = "I'm available for immediate part-time contract work and can deliver a fast-turnaround prototype."
    elif "show hn" in source.lower() or intent == "discovery":
        return (
            f"{greeting} congrats on launching {short_title}! If you need hands-on help building Python integrations, "
            f"data scrapers, or automation tools as you grow, I'd love to help out on a quick initial milestone."
        )
    else:
        focus = "Python development and data automation"
        offer = "I can build a working prototype with a quick turnaround."

    return (
        f"{greeting} saw your post regarding {short_title}. "
        f"I specialize in {focus}. {offer} Would love to chat if you're interested!"
    )


def generate_quick_action_link(lead, pitch):
    emails = [e.strip() for e in lead.get("other_contact", "").split(";") if "@" in e]
    source = lead.get("source", "").lower()
    author = lead.get("company_or_author", "").replace("/u/", "").replace("u/", "").strip()
    subject = f"Regarding your project: {lead.get('title_or_role', '')[:45]}"

    if emails:
        return f"mailto:{emails[0]}?subject={quote(subject)}&body={quote(pitch)}"
    elif "reddit" in source and author and author != "reddit user":
        return f"https://www.reddit.com/message/compose/?to={author}&subject={quote(subject)}&body={quote(pitch)}"
    else:
        return lead.get("article_link", "")

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

        posted_date = format_date(comment.get("created_at") or comment.get("created_at_i"))

        lead = {
            "intent_type": intent,
            "posted_at": posted_date,
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
        pitch = generate_tailored_pitch(lead)
        lead["tailored_pitch"] = pitch
        lead["quick_action"] = generate_quick_action_link(lead, pitch)
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

        posted_date = format_date(comment.get("created_at") or comment.get("created_at_i"))

        lead = {
            "intent_type": "contract_hiring",
            "posted_at": posted_date,
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
        pitch = generate_tailored_pitch(lead)
        lead["tailored_pitch"] = pitch
        lead["quick_action"] = generate_quick_action_link(lead, pitch)
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
            posted_date = format_date(hit.get("created_at") or hit.get("created_at_i"))

            lead = {
                "intent_type": "contract_hiring",
                "posted_at": posted_date,
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
            pitch = generate_tailored_pitch(lead)
            lead["tailored_pitch"] = pitch
            lead["quick_action"] = generate_quick_action_link(lead, pitch)
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
        posted_date = format_date(hit.get("created_at") or hit.get("created_at_i"))

        lead = {
            "intent_type": intent,
            "posted_at": posted_date,
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
        pitch = generate_tailored_pitch(lead)
        lead["tailored_pitch"] = pitch
        lead["quick_action"] = generate_quick_action_link(lead, pitch)
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
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc) if published else datetime.now(timezone.utc)
            if pub_dt < cutoff_dt:
                continue

            title = entry.get("title", "")
            summary_raw = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
            clean_text = clean_html_text(summary_raw)

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
            posted_date = pub_dt.strftime("%Y-%m-%d")

            lead = {
                "intent_type": feed_info["intent"],
                "posted_at": posted_date,
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
            pitch = generate_tailored_pitch(lead)
            lead["tailored_pitch"] = pitch
            lead["quick_action"] = generate_quick_action_link(lead, pitch)
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
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc) if published else datetime.now(timezone.utc)
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

            posted_date = pub_dt.strftime("%Y-%m-%d")

            lead = {
                "intent_type": "discovery",
                "posted_at": posted_date,
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
            pitch = generate_tailored_pitch(lead)
            lead["tailored_pitch"] = pitch
            lead["quick_action"] = generate_quick_action_link(lead, pitch)
            leads.append(lead)

    return leads

# ---------------------------------------------------------------------------
# Output & File Management
# ---------------------------------------------------------------------------

def safe_open_csv(csv_path, mode="a"):
    try:
        f = open(csv_path, mode, newline="", encoding="utf-8")
        return f, csv_path
    except PermissionError:
        base, ext = os.path.splitext(csv_path)
        fallback = f"{base}_new{ext}"
        print(
            f"\n[WARNING] '{csv_path}' is currently locked by another application (e.g. Excel).\n"
            f"  -> Writing leads to '{fallback}' instead.\n"
            f"  -> Close '{csv_path}' in Excel/viewers to allow direct writes on future runs.\n"
        )
        f = open(fallback, mode, newline="", encoding="utf-8")
        return f, fallback


def check_and_migrate_csv(csv_path):
    if not os.path.exists(csv_path):
        return set(), csv_path

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            try:
                first_row = next(reader)
            except StopIteration:
                return set(), csv_path
    except Exception:
        return set(), csv_path

    if first_row != FIELDNAMES:
        archive_name = "leads_v2_archive.csv"
        print(
            f"\n[NOTICE] '{csv_path}' schema has been upgraded (added posted_at & outreach engine).\n"
            f"  -> Archiving existing file to '{archive_name}' to preserve all prior data.\n"
            f"  -> Creating a fresh '{csv_path}' with the updated columns.\n"
        )
        try:
            shutil.copyfile(csv_path, archive_name)
        except Exception as e:
            print(f"  Notice: could not backup {csv_path}: {e}")

        f, actual_path = safe_open_csv(csv_path, mode="w")
        with f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        return set(), actual_path

    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            dict_reader = csv.DictReader(f)
            return {row["article_link"] for row in dict_reader if row.get("article_link")}, csv_path
    except Exception:
        return set(), csv_path


def append_leads(csv_path, leads, min_score=0):
    existing_links, actual_path = check_and_migrate_csv(csv_path)
    new_leads = [
        l for l in leads
        if l["article_link"] not in existing_links and l["score"] >= min_score
    ]

    new_leads.sort(key=lambda x: x["score"], reverse=True)

    write_header = not os.path.exists(actual_path) or os.path.getsize(actual_path) == 0
    f, final_path = safe_open_csv(actual_path, mode="a")
    with f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        for lead in new_leads:
            writer.writerow(lead)

    return new_leads, final_path

# ---------------------------------------------------------------------------
# Interactive HTML Dashboard Generator
# ---------------------------------------------------------------------------

def export_html_dashboard(leads, html_path=DEFAULT_HTML_PATH):
    # Sort descending by score
    sorted_leads = sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
    leads_json = json.dumps(sorted_leads)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Startup Lead Tracker | Outreach Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: rgba(22, 28, 45, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --green: #10b981;
      --purple: #8b5cf6;
      --amber: #f59e0b;
      --rose: #f43f5e;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 32px 20px;
      min-height: 100vh;
    }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 32px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--card-border);
    }}
    .title h1 {{ font-size: 28px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }}
    .title p {{ color: var(--text-muted); font-size: 14px; margin-top: 4px; }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .stat-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px 20px;
      backdrop-filter: blur(8px);
    }}
    .stat-val {{ font-size: 26px; font-weight: 700; color: #fff; }}
    .stat-label {{ font-size: 13px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
    .controls {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 24px;
      align-items: center;
      justify-content: space-between;
    }}
    .filter-group {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .btn {{
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 500;
      transition: all 0.2s;
    }}
    .btn:hover, .btn.active {{
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
    }}
    .search-input {{
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 14px;
      width: 280px;
      outline: none;
    }}
    .search-input:focus {{ border-color: var(--accent); }}
    .leads-grid {{ display: flex; flex-direction: column; gap: 16px; }}
    .lead-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 22px 24px;
      backdrop-filter: blur(12px);
      transition: transform 0.15s, border-color 0.15s;
    }}
    .lead-card:hover {{
      border-color: rgba(59, 130, 246, 0.4);
      transform: translateY(-2px);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }}
    .badge-score-high {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .badge-score-mid {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
    .badge-score-low {{ background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }}
    .badge-source {{ background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3); }}
    .card-title {{ font-size: 18px; font-weight: 600; color: #fff; line-height: 1.4; }}
    .card-meta {{
      display: flex;
      gap: 16px;
      font-size: 13px;
      color: var(--text-muted);
      margin-top: 6px;
      flex-wrap: wrap;
    }}
    .snippet {{
      font-size: 14px;
      color: #cbd5e1;
      line-height: 1.6;
      margin: 14px 0;
      background: rgba(0, 0, 0, 0.2);
      padding: 12px 14px;
      border-radius: 8px;
    }}
    .pitch-box {{
      background: rgba(59, 130, 246, 0.08);
      border: 1px dashed rgba(59, 130, 246, 0.35);
      border-radius: 10px;
      padding: 14px 16px;
      margin: 14px 0;
    }}
    .pitch-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      font-size: 12px;
      font-weight: 600;
      color: #60a5fa;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .pitch-text {{ font-size: 14px; color: #f1f5f9; line-height: 1.5; font-style: italic; }}
    .card-actions {{
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .btn-action {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: background 0.2s;
    }}
    .btn-reachout {{ background: #2563eb; color: #fff; }}
    .btn-reachout:hover {{ background: #1d4ed8; }}
    .btn-copy {{ background: rgba(255, 255, 255, 0.08); color: #e2e8f0; border: 1px solid var(--card-border); cursor: pointer; }}
    .btn-copy:hover {{ background: rgba(255, 255, 255, 0.15); }}
    .btn-link {{ background: transparent; color: var(--text-muted); border: 1px solid var(--card-border); }}
    .btn-link:hover {{ color: #fff; border-color: rgba(255, 255, 255, 0.3); }}
    .contact-tag {{
      display: inline-flex;
      font-size: 13px;
      color: #34d399;
      background: rgba(16, 185, 129, 0.1);
      padding: 4px 10px;
      border-radius: 6px;
      margin-left: auto;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title">
        <h1>Startup Lead Tracker V2</h1>
        <p>Active Hiring Intent, Scored Gigs & 1-Click Outreach Engine</p>
      </div>
    </header>

    <div class="stats-bar" id="statsBar"></div>

    <div class="controls">
      <div class="filter-group">
        <button class="btn active" onclick="setFilter('all')">All Leads</button>
        <button class="btn" onclick="setFilter('high')">High Fit (60+)</button>
        <button class="btn" onclick="setFilter('contract')">Contract Only</button>
        <button class="btn" onclick="setFilter('contact')">Has Direct Contact</button>
      </div>
      <input type="text" class="search-input" id="search" placeholder="Search keywords, stack, author..." oninput="render()">
    </div>

    <div class="leads-grid" id="leadsGrid"></div>
  </div>

  <script>
    const leadsData = {leads_json};
    let currentFilter = 'all';

    function setFilter(filter) {{
      currentFilter = filter;
      document.querySelectorAll('.filter-group .btn').forEach(b => b.classList.remove('active'));
      event.target.classList.add('active');
      render();
    }}

    function copyToClipboard(text, btn) {{
      navigator.clipboard.writeText(text).then(() => {{
        const old = btn.innerText;
        btn.innerText = 'Copied!';
        setTimeout(() => btn.innerText = old, 1500);
      }});
    }}

    function render() {{
      const query = document.getElementById('search').value.toLowerCase();
      const filtered = leadsData.filter(lead => {{
        if (currentFilter === 'high' && lead.score < 60) return false;
        if (currentFilter === 'contract' && lead.intent_type !== 'contract_hiring') return false;
        if (currentFilter === 'contact' && !lead.other_contact && !lead.domain) return false;
        if (query) {{
          const hay = (lead.title_or_role + ' ' + lead.summary_snippet + ' ' + lead.company_or_author + ' ' + lead.source).toLowerCase();
          if (!hay.includes(query)) return false;
        }}
        return true;
      }});

      // Update stats
      const highFitCount = leadsData.filter(l => l.score >= 60).length;
      const contactCount = leadsData.filter(l => l.other_contact || l.domain).length;
      document.getElementById('statsBar').innerHTML = `
        <div class="stat-card"><div class="stat-val">${{leadsData.length}}</div><div class="stat-label">Total Leads</div></div>
        <div class="stat-card"><div class="stat-val" style="color: #34d399">${{highFitCount}}</div><div class="stat-label">High-Fit Gigs (60+)</div></div>
        <div class="stat-card"><div class="stat-val" style="color: #60a5fa">${{contactCount}}</div><div class="stat-label">With Direct Contact</div></div>
        <div class="stat-card"><div class="stat-val">${{filtered.length}}</div><div class="stat-label">Showing Now</div></div>
      `;

      const grid = document.getElementById('leadsGrid');
      if (filtered.length === 0) {{
        grid.innerHTML = '<div style="text-align: center; padding: 48px; color: #94a3b8;">No leads match your filter.</div>';
        return;
      }}

      grid.innerHTML = filtered.map(lead => {{
        let scoreClass = 'badge-score-low';
        if (lead.score >= 70) scoreClass = 'badge-score-high';
        else if (lead.score >= 50) scoreClass = 'badge-score-mid';

        const contact = lead.other_contact || lead.domain || '';
        const safePitch = (lead.tailored_pitch || '').replace(/'/g, "\\\\'");

        return `
          <div class="lead-card">
            <div class="card-header">
              <div>
                <span class="badge ${{scoreClass}}" title="${{lead.score_breakdown || ''}}">${{lead.score}} PTS</span>
                <span class="badge badge-source">${{lead.source}}</span>
                <span class="badge" style="background: rgba(255,255,255,0.06); color:#94a3b8;">${{lead.intent_type}}</span>
                <h2 class="card-title" style="margin-top: 8px;">${{lead.title_or_role}}</h2>
                <div class="card-meta">
                  <span>Author/Company: <strong>${{lead.company_or_author}}</strong></span>
                  <span>Posted: <strong>${{lead.posted_at || 'Recent'}}</strong></span>
                  <span>Found: <strong>${{lead.found_at}}</strong></span>
                </div>
              </div>
              ${{contact ? `<span class="contact-tag">📞 ${{contact.split(';')[0]}}</span>` : ''}}
            </div>

            <div class="snippet">${{lead.summary_snippet}}</div>

            <div class="pitch-box">
              <div class="pitch-header">
                <span>🎯 Tailored Cold Pitch Hook</span>
                <button class="btn btn-copy" style="padding: 2px 8px; font-size: 11px;" onclick="copyToClipboard('${{safePitch}}', this)">Copy Pitch</button>
              </div>
              <div class="pitch-text">"${{lead.tailored_pitch || ''}}"</div>
            </div>

            <div class="card-actions">
              <a href="${{lead.quick_action}}" target="_blank" class="btn-action btn-reachout">⚡ 1-Click Outreach</a>
              <a href="${{lead.article_link}}" target="_blank" class="btn-action btn-link">View Original Post ↗</a>
            </div>
          </div>
        `;
      }}).join('');
    }}

    render();
  </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scan for high-intent startup leads, freelance contracts, and automation gigs with 1-click outreach."
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
        "--html",
        type=str,
        default=DEFAULT_HTML_PATH,
        help=f"Interactive HTML dashboard output file (default: {DEFAULT_HTML_PATH})",
    )
    parser.add_argument(
        "--no-html",
        action="store_true",
        help="Disable automatic HTML dashboard export",
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

    new_saved, final_out = append_leads(args.out, all_leads, min_score=args.min_score)

    print("\n" + "=" * 60)
    print(f"Total leads retrieved across sources: {len(all_leads)}")
    print(f"Leads meeting min-score (>={args.min_score}) & newly saved: {len(new_saved)}")
    print(f"Output saved to CSV: {final_out}")

    if not args.no_html:
        dashboard_leads = []
        target_csv = final_out if os.path.exists(final_out) else args.out
        if os.path.exists(target_csv):
            with open(target_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    try:
                        r["score"] = int(r.get("score", 0))
                    except ValueError:
                        r["score"] = 0
                    dashboard_leads.append(r)
        export_html_dashboard(dashboard_leads, html_path=args.html)
        print(f"Interactive outreach dashboard generated: {args.html}")

    high_score = [l for l in new_saved if l["score"] >= 60]
    with_contact = [l for l in new_saved if l["domain"] or l["other_contact"]]
    print(f"High-fit leads (Score >= 60): {len(high_score)}")
    print(f"Leads with resolved contact/domain: {len(with_contact)}")

    if new_saved:
        print("\nTop 3 New Leads with 1-Click Outreach:")
        for idx, lead in enumerate(new_saved[:3], 1):
            contact_info = lead["other_contact"] or lead["domain"] or "No direct contact"
            print(f" {idx}. [{lead['score']} pts] {lead['company_or_author']} - {lead['title_or_role']}")
            print(f"    Posted: {lead.get('posted_at')} | Contact: {contact_info}")
            print(f"    Tailored Pitch: \"{lead.get('tailored_pitch', '')}\"")
            print(f"    Quick Action: {lead.get('quick_action', '')}")


if __name__ == "__main__":
    main()
