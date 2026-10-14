#!/usr/bin/env python3
"""
Startup Lead Tracker (V3 - Student-Focused Internship & Freelance Gig Finder)

Scans public sources for startups, founders, and hiring managers with active
intent for contract, freelance, internship, and junior/automation work (tailored
for Python, scraping, bot, and LLM/automation gigs). Favours junior/internship
roles and penalises senior-level positions to surface student-friendly opportunities.

FEATURES & INNOVATIONS:
  1. Multi-Source Active Intent: HN "Who is hiring?", "Seeking freelancer",
     real-time hiring comments, Show HN launches, Reddit freelance RSS, and
     intern-list.com (SWE, Data Analysis, AI/ML internships via Airtable embed).
  2. Student-Aware Scoring Engine (0-100 pts): Intent, Python Skill fit, Stage,
     Budget, Seniority Penalty (-30 for Senior/Staff/Lead roles), and
     Junior/Intern Boost (+25 for Intern/Junior/Entry-Level roles).
  3. Lead Date Tracking: Captures 'posted_at' (when the post was published)
     alongside 'found_at'.
  4. 1-Click Outreach Engine: Automatically crafts a tailored cold pitch /
     student cover letter intro for each lead and generates a pre-filled
     'quick_action' URL (mailto:, direct apply link, or Reddit compose).
  5. Interactive HTML Dashboard: Dark-mode 'leads.html' with multi-column
     sorting (Score, Posted Date, Found Date), filter tabs (Internships,
     Contract, High Fit, Contact), Hide Senior Roles toggle, and expandable
     score breakdown chips.
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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
DEFAULT_JSON_PATH = "leads.json"
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}
REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Live verified intern-list.com Airtable shared-view embeds by track
INTERN_LIST_SOURCES = [
    {
        "category": "InternList (SWE)",
        "embed_url": "https://airtable.com/embed/app17F0kkWQZhC6HB/shrOTtndhc6HSgnYb?viewControls=on",
    },
    {
        "category": "InternList (Data)",
        "embed_url": "https://airtable.com/embed/appbsiP1flCoaXCSm/shreRS1cFLbduwBaU?viewControls=on",
    },
    {
        "category": "InternList (AI/ML)",
        "embed_url": "https://airtable.com/embed/appjSXAWiVF4d1HoZ/shrf04yGbrK3IebAl?viewControls=on",
    },
]

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


_GITHUB_CACHE = {}
_GITHUB_CALL_COUNT = 0
_GITHUB_MAX_CALLS = 10
_GITHUB_RATE_LIMITED = False


def resolve_github_owner_contact(url):
    global _GITHUB_CALL_COUNT, _GITHUB_RATE_LIMITED
    match = re.search(r"github\.com/([^/]+)/?", url)
    if not match:
        return {}
    owner = match.group(1).strip()
    if not owner or owner.lower() in ["topics", "features", "explore", "site", "orgs", "about"]:
        return {}

    if owner in _GITHUB_CACHE:
        return _GITHUB_CACHE[owner]

    result = {"github_profile": f"https://github.com/{owner}"}
    if _GITHUB_RATE_LIMITED or _GITHUB_CALL_COUNT >= _GITHUB_MAX_CALLS:
        _GITHUB_CACHE[owner] = result
        return result

    try:
        _GITHUB_CALL_COUNT += 1
        resp = requests.get(
            GITHUB_API_BASE + owner,
            headers={
                "User-Agent": "StartupLeadTracker/3.0",
                "Accept": "application/vnd.github+json",
            },
            timeout=2.0,
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
        elif resp.status_code in (403, 429):
            _GITHUB_RATE_LIMITED = True
    except Exception:
        pass

    _GITHUB_CACHE[owner] = result
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

# Keywords that signal a seniority mismatch for a student (penalty applied)
SENIORITY_PENALTY_KEYWORDS = [
    r"\bsenior\b", r"\bsr\.\b", r"\bstaff\b", r"\bprincipal\b",
    r"\blead engineer\b", r"\blead developer\b", r"\bdirector\b",
    r"\bvp of\b", r"\bvice president\b", r"\bhead of engineering\b",
    r"\bhead of product\b", r"\barchitect\b",
    r"\b5\+\s*years\b", r"\b7\+\s*years\b", r"\b10\+\s*years\b",
    r"\bminimum 5 years\b", r"\bat least 5 years\b",
]

# Keywords that signal student / junior friendliness (boost applied)
JUNIOR_BOOST_KEYWORDS = [
    r"\bintern\b", r"\binternship\b", r"\bjunior\b", r"\bjr\.\b",
    r"\bentry.?level\b", r"\bentry level\b", r"\bstudent\b",
    r"\bnew grad\b", r"\bnewgrad\b", r"\bapprentice\b",
    r"\bpart.?time\b", r"\bfresh graduate\b", r"\bno experience\b",
    r"\bopen to grads\b",
]


def calculate_lead_score(lead):
    title = lead.get("title_or_role", "")
    snippet = lead.get("summary_snippet", "")
    intent_type = lead.get("intent_type", "discovery")
    source = lead.get("source", "").lower()
    full_text = f"{title} {snippet}".lower()

    breakdown_parts = []

    # 1. Intent Score (Max 35 pts)
    contract_intent_patterns = [
        r"\bseeking freelancer\b", r"\[hiring\]", r"\bcontract\b", r"\bfreelance\b",
        r"\bpart-time\b", r"\bpart time\b", r"\blooking to hire\b",
        r"\bneed a freelancer\b", r"\bhiring a contractor\b", r"\bgig\b", r"\bbounty\b",
    ]
    if intent_type in ("contract_hiring", "internship") or any(
        re.search(p, full_text) for p in contract_intent_patterns
    ):
        intent_score = 35
    elif intent_type == "fulltime_hiring" or "who is hiring" in source:
        intent_score = 20
    elif intent_type == "help_wanted" or any(
        p in full_text
        for p in ["looking for help", "need help", "collaborator", "co-founder", "looking for developer"]
    ):
        intent_score = 15
    else:
        intent_score = 5
    breakdown_parts.append(f"Intent:+{intent_score}")

    # 2. Skill & Stack Relevance (Max 30 pts, Min -10 pts)
    tier1_keywords = [
        "python", "scraping", "scraper", "scrape", "crawler", "crawl",
        "automation", "automate", "bot", "ai", "llm", "gemini", "openai",
        "gpt", "fastapi", "flask", "django", "data extraction", "pipeline",
        "etl", "playwright", "selenium", "beautifulsoup", "bs4", "scripting",
        "script", "data analysis", "machine learning", "ml",
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

    if tier1_hits == 0 and any(
        re.search(r"\b" + re.escape(kw) + r"\b", full_text) for kw in disjoint_keywords
    ):
        skill_score = -10
    breakdown_parts.append(f"Skill:{'+' if skill_score >= 0 else ''}{skill_score}")

    # 3. Stage & Team Size Fit (Max 20 pts, Min -20 pts)
    small_stage_patterns = [
        r"\bsolo founder\b", r"\bbootstrapped\b", r"\bpre-seed\b", r"\bseed\b",
        r"\bsmall team\b", r"\bindie hacker\b", r"<10 people", r"1-5 people",
        r"\bside project\b", r"\bearly stage\b", r"\bmvp\b", r"\bstealth\b",
    ]
    enterprise_patterns = [
        r"\bseries [b-f]\b", r"\b100\+\s*employees\b", r"\b50\+\s*employees\b",
        r"\benterprise\b", r"\bfortune 500\b",
    ]
    stage_score = 5
    if any(re.search(p, full_text) for p in small_stage_patterns):
        stage_score = 20
    elif any(re.search(p, full_text) for p in enterprise_patterns):
        stage_score = -20
    breakdown_parts.append(f"Stage:{'+' if stage_score >= 0 else ''}{stage_score}")

    # 4. Budget Plausibility (Max 15 pts, Min -15 pts)
    unpaid_patterns = [
        r"\bunpaid\b", r"\bequity-only\b", r"\bequity only\b", r"\bfree internship\b",
        r"\bno pay\b", r"\bvolunteer\b", r"\bno salary\b",
    ]
    sweet_budget_patterns = [
        r"\$[1-9][0-9]{2}\b", r"\$[1-5][0-9]\s*/\s*hr",
        r"\bhourly rate\b", r"\bstipend\b", r"\bfixed price\b", r"\bbounty\b",
        r"\b200/month\b", r"\b200/mo\b", r"\b250\b",
    ]
    budget_score = 0
    if any(re.search(p, full_text) for p in unpaid_patterns):
        budget_score = -15
    elif any(re.search(p, full_text) for p in sweet_budget_patterns):
        budget_score = 15
    elif "who is hiring" in source or "funding" in full_text:
        budget_score = 5
    breakdown_parts.append(f"Budget:{'+' if budget_score >= 0 else ''}{budget_score}")

    # 5. Seniority Penalty (-30 for senior/staff/lead/director/architect roles)
    seniority_penalty = 0
    if any(re.search(p, full_text) for p in SENIORITY_PENALTY_KEYWORDS):
        seniority_penalty = -30
        breakdown_parts.append("Senior:-30")

    # 6. Junior / Intern Boost (+25 for intern/junior/entry-level/student roles)
    junior_boost = 0
    if intent_type == "internship" or any(
        re.search(p, full_text) for p in JUNIOR_BOOST_KEYWORDS
    ):
        junior_boost = 25
        breakdown_parts.append("Junior/Intern:+25")

    raw = intent_score + skill_score + stage_score + budget_score + seniority_penalty + junior_boost
    total_score = max(0, min(100, raw))
    breakdown = "|".join(breakdown_parts)
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
        greeting = f"Hi {clean_author} team,"
    else:
        greeting = "Hi there,"

    short_title = title[:60].strip().rstrip("-:| ")

    # Student-specific: internship cover letter intro
    if intent == "internship" or any(
        re.search(p, full_text) for p in JUNIOR_BOOST_KEYWORDS
    ):
        if any(w in full_text for w in ["data", "analyst", "analysis", "sql", "excel", "dashboard"]):
            focus = "data analysis, SQL querying, and Python-based pipeline automation"
        elif any(w in full_text for w in ["ai", "ml", "machine learning", "llm", "nlp"]):
            focus = "Python, machine learning workflows, and LLM integration"
        else:
            focus = "Python development, web scraping, and automation tooling"
        return (
            f"{greeting} I'm a self-taught developer currently studying and I'm excited to apply for the "
            f"{short_title} role. I have hands-on experience in {focus}, and I'm eager to contribute "
            f"from day one. I learn extremely fast, am comfortable working autonomously, and would love "
            f"the chance to bring real value to your team this term. Looking forward to hearing from you!"
        )

    # Freelance / contract pitch
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
            "url": "https://www.reddit.com/r/SideProject/search.rss?q=python+OR+developer+OR+scraper&restrict_sr=on&sort=new&t=all",
            "intent": "discovery",
        },
    ]

    session = requests.Session()
    session.headers.update(REDDIT_HEADERS)

    for i, feed_info in enumerate(feeds):
        try:
            if i > 0:
                time.sleep(1.2)
            resp = session.get(feed_info["url"], timeout=HTTP_TIMEOUT)
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

def _find_first(d, *candidate_keys):
    """Case-insensitive lookup of the first present key in a row dict."""
    lower_map = {k.lower(): v for k, v in d.items()}
    for key in candidate_keys:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    return None


def _scrape_airtable_category(session, category_info, cutoff_dt):
    """
    Scrapes an individual Airtable embed for a specific category track.
    Hydrates view parameters and fetches nested shared view records with column mapping.
    """
    leads = []
    category_name = category_info["category"]
    embed_url = category_info["embed_url"]

    try:
        embed_resp = session.get(embed_url, timeout=HTTP_TIMEOUT)
        embed_resp.raise_for_status()
    except Exception as e:
        print(f"  [{category_name}] Could not load embed page ({e}). Skipping.")
        return leads

    match = re.search(r"window\.initData\s*=\s*(\{.*?\});\s*(?:window|\n|<|performance)", embed_resp.text, re.DOTALL)
    if not match:
        print(f"  [{category_name}] Could not extract initData from embed HTML. Skipping.")
        return leads

    try:
        init_data = json.loads(match.group(1))
    except Exception as e:
        print(f"  [{category_name}] Failed to parse embed JSON ({e}). Skipping.")
        return leads

    app_id = init_data.get("singleApplicationId") or list(init_data.get("rawApplications", {}).keys())[0]
    view_id = init_data.get("sharedViewId")
    access_policy = init_data.get("accessPolicy")

    if not view_id:
        print(f"  [{category_name}] Missing sharedViewId in payload. Skipping.")
        return leads

    api_url = f"https://airtable.com/v0.3/view/{view_id}/readSharedViewData"
    params = {
        "stringifiedObjectParams": json.dumps({"shouldUseNestedResponseFormat": True}),
        "requestId": "req_leadtracker",
        "accessPolicy": access_policy if isinstance(access_policy, str) else json.dumps(access_policy),
    }
    api_headers = {
        "X-Airtable-Application-Id": app_id,
        "X-Time-Zone": "America/New_York",
        "X-User-Locale": "en",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": embed_url,
    }

    try:
        api_resp = session.get(api_url, params=params, headers=api_headers, timeout=HTTP_TIMEOUT)
        api_resp.raise_for_status()
        payload = api_resp.json()
    except Exception as e:
        print(f"  [{category_name}] readSharedViewData failed ({e}). Skipping.")
        return leads

    table = payload.get("data", {}).get("table", {})
    cols_by_id = {c["id"]: c.get("name", "") for c in table.get("columns", [])}
    rows = table.get("rows", [])

    for row in rows:
        cell_values = row.get("cellValuesByColumnId", {})
        named_cells = {cols_by_id.get(cid, cid): val for cid, val in cell_values.items()}

        title = _find_first(named_cells, "Position Title", "Title", "Role", "Job Title") or ""
        company = _find_first(named_cells, "Company", "Company Name", "Employer") or "Unknown Company"
        date_added = _find_first(named_cells, "Date", "Date Added", "Date Posted", "Posted", "Created")
        work_model = _find_first(named_cells, "Work Model", "Remote/Hybrid/In-Person", "Location Type") or ""
        location = _find_first(named_cells, "Location", "City", "State") or ""
        salary = _find_first(named_cells, "Salary", "Compensation", "Pay") or ""
        qualifications = _find_first(named_cells, "Qualifications", "Requirements", "Description") or ""
        apply_raw = _find_first(named_cells, "Apply", "Application URL", "Apply Link", "URL", "Link") or ""
        apply_url = apply_raw.get("url") if isinstance(apply_raw, dict) else str(apply_raw or "")

        if not title:
            continue

        posted_date = format_date(date_added) if date_added else None
        if posted_date:
            try:
                if datetime.strptime(posted_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) < cutoff_dt:
                    continue
            except ValueError:
                pass

        snippet_bits = [b for b in [work_model, location, salary, qualifications] if b]
        summary_snippet = " | ".join(str(b) for b in snippet_bits)[:350]

        lead = {
            "intent_type": "internship",
            "posted_at": posted_date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "found_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "source": category_name,
            "company_or_author": str(company),
            "title_or_role": str(title)[:150],
            "domain": "",
            "guessed_emails": "",
            "other_contact": "",
            "summary_snippet": summary_snippet,
            "article_link": str(apply_url) or embed_url,
        }
        score, breakdown = calculate_lead_score(lead)
        lead["score"] = score
        lead["score_breakdown"] = breakdown
        pitch = generate_tailored_pitch(lead)
        lead["tailored_pitch"] = pitch
        lead["quick_action"] = apply_url or generate_quick_action_link(lead, pitch)
        leads.append(lead)

    return leads


def scan_intern_list(days_back=30):
    """
    Scrapes verified category tracks (SWE, Data Analysis, AI/ML) from intern-list.com.
    """
    leads = []
    cutoff_dt = cutoff_datetime(days_back)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    for cat_info in INTERN_LIST_SOURCES:
        cat_leads = _scrape_airtable_category(session, cat_info, cutoff_dt)
        leads.extend(cat_leads)

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
      --bg: #080c17;
      --card-bg: rgba(16, 22, 38, 0.9);
      --card-border: rgba(255, 255, 255, 0.07);
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --accent: #3b82f6;
      --accent-hover: #2563eb;
      --green: #10b981;
      --purple: #8b5cf6;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --teal: #14b8a6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      background-image: radial-gradient(ellipse at 20% 50%, rgba(59,130,246,0.04) 0%, transparent 60%),
                        radial-gradient(ellipse at 80% 20%, rgba(139,92,246,0.04) 0%, transparent 60%);
      color: var(--text);
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, sans-serif;
      padding: 32px 20px;
      min-height: 100vh;
    }}
    .container {{ max-width: 1240px; margin: 0 auto; }}
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
    .title h1 {{ font-size: 26px; font-weight: 700; color: #fff; letter-spacing: -0.5px; }}
    .title h1 span {{ background: linear-gradient(135deg,#3b82f6,#8b5cf6); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }}
    .title p {{ color: var(--text-muted); font-size: 13px; margin-top: 4px; }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .stat-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 14px 18px;
      backdrop-filter: blur(8px);
    }}
    .stat-val {{ font-size: 24px; font-weight: 700; color: #fff; }}
    .stat-label {{ font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.6px; margin-top: 2px; }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 20px;
      align-items: center;
    }}
    .filter-group {{ display: flex; gap: 6px; flex-wrap: wrap; flex: 1; }}
    .sort-group {{ display: flex; align-items: center; gap: 8px; }}
    .toggle-group {{ display: flex; align-items: center; gap: 8px; }}
    .btn {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 7px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 500;
      transition: all 0.18s;
      font-family: 'Outfit', sans-serif;
    }}
    .btn:hover {{ background: rgba(59,130,246,0.12); border-color: rgba(59,130,246,0.4); color: #93c5fd; }}
    .btn.active {{ background: rgba(59,130,246,0.2); border-color: var(--accent); color: #60a5fa; font-weight: 600; }}
    .btn.active-green {{ background: rgba(16,185,129,0.15); border-color: #10b981; color: #34d399; font-weight: 600; }}
    select.sort-select {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-family: 'Outfit', sans-serif;
      outline: none;
      cursor: pointer;
      appearance: none;
      -webkit-appearance: none;
      padding-right: 28px;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2394a3b8' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      background-position: right 10px center;
    }}
    select.sort-select:focus {{ border-color: var(--accent); }}
    .search-input {{
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid var(--card-border);
      color: #fff;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-family: 'Outfit', sans-serif;
      min-width: 240px;
      flex: 1;
      max-width: 320px;
      outline: none;
    }}
    .search-input::placeholder {{ color: #475569; }}
    .search-input:focus {{ border-color: var(--accent); background: rgba(59,130,246,0.05); }}
    /* Toggle switch */
    .toggle-label {{ font-size: 13px; color: var(--text-muted); white-space: nowrap; }}
    .toggle-switch {{ position: relative; width: 40px; height: 22px; }}
    .toggle-switch input {{ opacity: 0; width: 0; height: 0; }}
    .slider {{
      position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(255,255,255,0.1); border-radius: 22px; transition: 0.2s;
      border: 1px solid var(--card-border);
    }}
    .slider:before {{
      position: absolute; content: ''; height: 16px; width: 16px; left: 2px; bottom: 2px;
      background: #94a3b8; border-radius: 50%; transition: 0.2s;
    }}
    .toggle-switch input:checked + .slider {{ background: rgba(16,185,129,0.3); border-color: #10b981; }}
    .toggle-switch input:checked + .slider:before {{ transform: translateX(18px); background: #10b981; }}
    /* Lead cards */
    .leads-grid {{ display: flex; flex-direction: column; gap: 14px; }}
    .lead-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px 24px;
      backdrop-filter: blur(12px);
      transition: transform 0.15s, border-color 0.2s, box-shadow 0.2s;
    }}
    .lead-card:hover {{
      border-color: rgba(59, 130, 246, 0.3);
      transform: translateY(-1px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }}
    .lead-card.internship {{ border-left: 3px solid #14b8a6; }}
    .lead-card.senior-role {{ opacity: 0.6; }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .badges-row {{ display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 3px 9px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
      white-space: nowrap;
    }}
    .badge-score-high {{ background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .badge-score-mid {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
    .badge-score-low {{ background: rgba(245, 158, 11, 0.12); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.25); }}
    .badge-source {{ background: rgba(139, 92, 246, 0.12); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.25); }}
    .badge-internship {{ background: rgba(20, 184, 166, 0.12); color: #2dd4bf; border: 1px solid rgba(20,184,166,0.25); }}
    .badge-senior {{ background: rgba(244, 63, 94, 0.1); color: #fb7185; border: 1px solid rgba(244,63,94,0.2); }}
    /* Score breakdown chips */
    .score-breakdown {{
      display: flex;
      gap: 5px;
      flex-wrap: wrap;
      margin-top: 6px;
    }}
    .chip {{
      font-size: 10px;
      padding: 2px 7px;
      border-radius: 4px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }}
    .chip-pos {{ background: rgba(16,185,129,0.12); color: #6ee7b7; border: 1px solid rgba(16,185,129,0.2); }}
    .chip-neg {{ background: rgba(244,63,94,0.1); color: #fca5a5; border: 1px solid rgba(244,63,94,0.2); }}
    .chip-neutral {{ background: rgba(148,163,184,0.08); color: #94a3b8; border: 1px solid rgba(148,163,184,0.15); }}
    .card-title {{ font-size: 16px; font-weight: 600; color: #fff; line-height: 1.4; }}
    .card-meta {{
      display: flex;
      gap: 14px;
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
      flex-wrap: wrap;
    }}
    .snippet {{
      font-size: 13px;
      color: #cbd5e1;
      line-height: 1.6;
      margin: 12px 0;
      background: rgba(0, 0, 0, 0.25);
      padding: 10px 13px;
      border-radius: 8px;
    }}
    .pitch-box {{
      background: rgba(59, 130, 246, 0.06);
      border: 1px dashed rgba(59, 130, 246, 0.3);
      border-radius: 10px;
      padding: 12px 14px;
      margin: 12px 0;
    }}
    .pitch-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 7px;
      font-size: 11px;
      font-weight: 600;
      color: #60a5fa;
      text-transform: uppercase;
      letter-spacing: 0.6px;
    }}
    .pitch-text {{ font-size: 13px; color: #e2e8f0; line-height: 1.5; font-style: italic; }}
    .card-actions {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .btn-action {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.2s;
      font-family: 'Outfit', sans-serif;
    }}
    .btn-reachout {{ background: linear-gradient(135deg,#2563eb,#1d4ed8); color: #fff; }}
    .btn-reachout:hover {{ background: linear-gradient(135deg,#1d4ed8,#1e40af); transform: translateY(-1px); }}
    .btn-apply {{ background: linear-gradient(135deg,#0d9488,#0f766e); color: #fff; }}
    .btn-apply:hover {{ background: linear-gradient(135deg,#0f766e,#115e59); transform: translateY(-1px); }}
    .btn-copy {{
      background: rgba(255, 255, 255, 0.06);
      color: #e2e8f0;
      border: 1px solid var(--card-border);
      cursor: pointer;
      font-family: 'Outfit', sans-serif;
    }}
    .btn-copy:hover {{ background: rgba(255, 255, 255, 0.12); }}
    .btn-link {{ background: transparent; color: var(--text-muted); border: 1px solid var(--card-border); }}
    .btn-link:hover {{ color: #fff; border-color: rgba(255, 255, 255, 0.25); }}
    .contact-tag {{
      display: inline-flex;
      font-size: 12px;
      color: #34d399;
      background: rgba(16, 185, 129, 0.08);
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid rgba(16,185,129,0.2);
      white-space: nowrap;
    }}
    .no-results {{
      text-align: center; padding: 60px; color: #475569;
      font-size: 15px;
    }}
    .result-count {{
      font-size: 12px; color: var(--text-muted);
      padding: 0 4px 12px;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="title">
        <h1>Lead Tracker <span>V3</span></h1>
        <p>Student-focused gig finder &mdash; internships, contracts &amp; junior roles surfaced first</p>
      </div>
    </header>

    <div class="stats-bar" id="statsBar"></div>

    <div class="toolbar">
      <div class="filter-group">
        <button id="f-all" class="btn active" onclick="setFilter('all')">🌐 All</button>
        <button id="f-internship" class="btn" onclick="setFilter('internship')">🎓 Internships</button>
        <button id="f-contract" class="btn" onclick="setFilter('contract')">💼 Contract</button>
        <button id="f-high" class="btn" onclick="setFilter('high')">⭐ High Fit</button>
        <button id="f-contact" class="btn" onclick="setFilter('contact')">📞 Direct Contact</button>
      </div>
      <div class="sort-group">
        <span style="font-size:12px;color:var(--text-muted);">Sort:</span>
        <select class="sort-select" id="sortSelect" onchange="render()">
          <option value="score">Highest Score</option>
          <option value="posted">Newest Posted</option>
          <option value="found">Newest Found</option>
          <option value="score_asc">Lowest Score</option>
        </select>
      </div>
    </div>

    <div class="toolbar" style="gap:12px;margin-top:-8px;margin-bottom:16px;">
      <input type="text" class="search-input" id="search" placeholder="🔍  Search roles, companies, stack..." oninput="render()">
      <div class="toggle-group">
        <span class="toggle-label">Hide Senior Roles</span>
        <label class="toggle-switch">
          <input type="checkbox" id="hideSenior" onchange="render()">
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <div class="result-count" id="resultCount"></div>
    <div class="leads-grid" id="leadsGrid"></div>
  </div>

  <script>
    const leadsData = {leads_json};
    let currentFilter = 'all';
    const SENIOR_RE = /\\b(senior|sr\\.|staff|principal|lead engineer|lead developer|director|vp of|vice president|head of engineering|head of product|architect|5\\+\\s*years|7\\+\\s*years|10\\+\\s*years)\\b/i;
    const JUNIOR_RE = /\\b(intern|internship|junior|jr\\.|entry.?level|student|new grad|apprentice|part.?time|fresh graduate)\\b/i;

    function isSenior(lead) {{
      return SENIOR_RE.test(lead.title_or_role + ' ' + lead.summary_snippet);
    }}

    function setFilter(filter) {{
      currentFilter = filter;
      document.querySelectorAll('.filter-group .btn').forEach(b => b.classList.remove('active'));
      const btn = document.getElementById('f-' + filter);
      if (btn) btn.classList.add('active');
      render();
    }}

    function copyToClipboard(text, btn) {{
      navigator.clipboard.writeText(text).then(() => {{
        const old = btn.innerText;
        btn.innerText = '✓ Copied!';
        setTimeout(() => btn.innerText = old, 1600);
      }});
    }}

    function sortData(data) {{
      const mode = document.getElementById('sortSelect').value;
      const copy = [...data];
      if (mode === 'score') return copy.sort((a,b) => (b.score||0)-(a.score||0));
      if (mode === 'score_asc') return copy.sort((a,b) => (a.score||0)-(b.score||0));
      if (mode === 'posted') return copy.sort((a,b) => (b.posted_at||'').localeCompare(a.posted_at||''));
      if (mode === 'found') return copy.sort((a,b) => (b.found_at||'').localeCompare(a.found_at||''));
      return copy;
    }}

    function buildChips(breakdown) {{
      if (!breakdown) return '';
      return breakdown.split('|').map(part => {{
        const isPos = part.includes('+') && !part.startsWith('-');
        const isNeg = part.includes('-') && !part.startsWith('Int');
        const cls = isNeg ? 'chip-neg' : (isPos ? 'chip-pos' : 'chip-neutral');
        return `<span class="chip ${{cls}}">${{part}}</span>`;
      }}).join('');
    }}

    function render() {{
      const query = document.getElementById('search').value.toLowerCase();
      const hideSenior = document.getElementById('hideSenior').checked;

      let filtered = leadsData.filter(lead => {{
        if (hideSenior && isSenior(lead)) return false;
        if (currentFilter === 'high' && lead.score < 60) return false;
        if (currentFilter === 'contract' && lead.intent_type !== 'contract_hiring') return false;
        if (currentFilter === 'internship' && lead.intent_type !== 'internship') return false;
        if (currentFilter === 'contact' && !lead.other_contact && !lead.domain) return false;
        if (query) {{
          const hay = (lead.title_or_role+' '+lead.summary_snippet+' '+lead.company_or_author+' '+lead.source).toLowerCase();
          if (!hay.includes(query)) return false;
        }}
        return true;
      }});

      filtered = sortData(filtered);

      // Stats bar
      const highFit = leadsData.filter(l => l.score >= 60).length;
      const internCount = leadsData.filter(l => l.intent_type === 'internship').length;
      const contactCount = leadsData.filter(l => l.other_contact || l.domain).length;
      const contractCount = leadsData.filter(l => l.intent_type === 'contract_hiring').length;
      document.getElementById('statsBar').innerHTML = `
        <div class="stat-card"><div class="stat-val">${{leadsData.length}}</div><div class="stat-label">Total Leads</div></div>
        <div class="stat-card"><div class="stat-val" style="color:#2dd4bf">${{internCount}}</div><div class="stat-label">🎓 Internships</div></div>
        <div class="stat-card"><div class="stat-val" style="color:#34d399">${{highFit}}</div><div class="stat-label">⭐ High Fit (60+)</div></div>
        <div class="stat-card"><div class="stat-val" style="color:#60a5fa">${{contractCount}}</div><div class="stat-label">💼 Contracts</div></div>
        <div class="stat-card"><div class="stat-val" style="color:#c084fc">${{contactCount}}</div><div class="stat-label">📞 Direct Contact</div></div>
        <div class="stat-card"><div class="stat-val">${{filtered.length}}</div><div class="stat-label">Showing</div></div>
      `;

      document.getElementById('resultCount').textContent = `Showing ${{filtered.length}} of ${{leadsData.length}} leads`;

      const grid = document.getElementById('leadsGrid');
      if (filtered.length === 0) {{
        grid.innerHTML = '<div class="no-results">🔍 No leads match your filter. Try adjusting the search or filter tabs.</div>';
        return;
      }}

      grid.innerHTML = filtered.map(lead => {{
        let scoreClass = 'badge-score-low';
        if (lead.score >= 70) scoreClass = 'badge-score-high';
        else if (lead.score >= 50) scoreClass = 'badge-score-mid';

        const isIntern = lead.intent_type === 'internship';
        const isSeniorRole = isSenior(lead);
        const cardClass = isIntern ? 'lead-card internship' : (isSeniorRole ? 'lead-card senior-role' : 'lead-card');

        const contact = lead.other_contact || lead.domain || '';
        const safePitch = (lead.tailored_pitch || '').replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'").replace(/\\n/g,'\\\\n');
        const chips = buildChips(lead.score_breakdown);

        const actionBtn = isIntern
          ? `<a href="${{lead.quick_action}}" target="_blank" class="btn-action btn-apply">🎓 Apply Now</a>`
          : `<a href="${{lead.quick_action}}" target="_blank" class="btn-action btn-reachout">⚡ 1-Click Outreach</a>`;

        return `
          <div class="${{cardClass}}">
            <div class="card-header">
              <div style="flex:1">
                <div class="badges-row">
                  <span class="badge ${{scoreClass}}">${{lead.score}} PTS</span>
                  <span class="badge badge-source">${{lead.source}}</span>
                  ${{isIntern ? '<span class="badge badge-internship">🎓 INTERN</span>' : ''}}
                  ${{isSeniorRole ? '<span class="badge badge-senior">⚠ SENIOR</span>' : ''}}
                  <span class="badge" style="background:rgba(255,255,255,0.05);color:#64748b;border:1px solid rgba(255,255,255,0.07);">${{lead.intent_type}}</span>
                </div>
                <div class="score-breakdown">${{chips}}</div>
                <h2 class="card-title" style="margin-top:8px">${{lead.title_or_role}}</h2>
                <div class="card-meta">
                  <span>🏢 <strong>${{lead.company_or_author}}</strong></span>
                  <span>📅 Posted: <strong>${{lead.posted_at || 'Recent'}}</strong></span>
                  <span>🔍 Found: <strong>${{lead.found_at}}</strong></span>
                </div>
              </div>
              ${{contact ? `<span class="contact-tag">📞 ${{contact.split(';')[0]}}</span>` : ''}}
            </div>

            <div class="snippet">${{lead.summary_snippet}}</div>

            <div class="pitch-box">
              <div class="pitch-header">
                <span>${{isIntern ? '✉️ Student Cover Letter Intro' : '🎯 Tailored Pitch Hook'}}</span>
                <button class="btn-action btn-copy" style="padding:3px 10px;font-size:11px;" onclick="copyLeadPitch(${{idx}}, this)">Copy</button>
              </div>
              <div class="pitch-text">&ldquo;${{escapeHtml(lead.tailored_pitch || '')}}&rdquo;</div>
            </div>

            <div class="card-actions">
              ${{actionBtn}}
              <a href="${{lead.article_link}}" target="_blank" class="btn-action btn-link">View Post ↗</a>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function escapeHtml(str) {{
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function copyLeadPitch(idx, btn) {{
      const lead = filteredLeadsCache[idx];
      const pitch = (lead && lead.tailored_pitch) || '';
      if (!pitch) return;
      navigator.clipboard.writeText(pitch).then(() => {{
        const oldText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.borderColor = '#10b981';
        btn.style.color = '#34d399';
        setTimeout(() => {{
          btn.textContent = oldText;
          btn.style.borderColor = '';
          btn.style.color = '';
        }}, 1800);
      }}).catch(err => {{
        prompt('Copy pitch manually:', pitch);
      }});
    }}

    let filteredLeadsCache = [];
    const origRender = render;
    render = function() {{
      const sortVal = document.getElementById('sortSelect').value;
      const seniorToggle = document.getElementById('hideSeniorToggle').checked;
      const search = document.getElementById('searchInput').value.toLowerCase().trim();

      filteredLeadsCache = leadsData.filter(lead => {{
        if (seniorToggle && isSenior(lead)) return false;
        if (currentFilter === 'high' && lead.score < 70) return false;
        if (currentFilter === 'contract' && lead.intent_type !== 'contract_hiring') return false;
        if (currentFilter === 'intern' && lead.intent_type !== 'internship') return false;
        if (currentFilter === 'contact' && !lead.domain && !lead.other_contact) return false;
        if (search) {{
          const hay = `${{lead.company_or_author}} ${{lead.title_or_role}} ${{lead.domain}} ${{lead.summary_snippet}} ${{lead.source}}`.toLowerCase();
          if (!hay.includes(search)) return false;
        }}
        return true;
      }});

      origRender();
    }};

    render();
  </script>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)


def export_json_leads(leads, json_path=DEFAULT_JSON_PATH):
    """
    Exports structured leads to JSON for modern web dashboards.
    Also syncs to dashboard/public/leads.json if available.
    """
    sorted_leads = sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(sorted_leads, f, indent=2, ensure_ascii=False)

    for sub in ["public", "dist"]:
        dashboard_dir = os.path.join("dashboard", sub)
        if os.path.exists(dashboard_dir):
            target = os.path.join(dashboard_dir, "leads.json")
            try:
                shutil.copyfile(json_path, target)
            except Exception:
                pass

    return json_path


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
        "--json",
        type=str,
        default=DEFAULT_JSON_PATH,
        help=f"JSON file to export leads to (default: {DEFAULT_JSON_PATH})",
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
    parser.add_argument(
        "--no-internships",
        action="store_true",
        help="Disable intern-list.com scraping",
    )
    parser.add_argument(
        "--sequential",
        action="store_true",
        help="Run scrapers sequentially instead of concurrently",
    )
    args = parser.parse_args()

    print(f"=== Startup Lead Tracker V3 (Lookback: {args.days} days, Min Score: {args.min_score}) ===")

    all_leads = []

    tasks = [
        ("HN 'Who is hiring?'", lambda: scan_hn_who_is_hiring(args.days)),
        ("HN 'Seeking freelancer?'", lambda: scan_hn_seeking_freelancer(args.days)),
        ("Targeted HN Comments", lambda: scan_hn_hiring_queries(args.days)),
        ("Reddit Hiring Feeds", lambda: scan_reddit_hiring(args.days)),
        ("Show HN Launches", lambda: scan_show_hn(args.days)),
    ]
    if args.include_news:
        tasks.append(("African Tech News", lambda: scan_news_sources(args.days)))
    if not args.no_internships:
        tasks.append(("InternList (SWE/Data/AI)", lambda: scan_intern_list(args.days)))

    if args.sequential:
        print("\n[Running sequentially]")
        for name, fn in tasks:
            print(f"  Scanning {name}...")
            res = fn()
            print(f"  -> Found {len(res)} items.")
            all_leads.extend(res)
    else:
        print(f"\n[Running {len(tasks)} scrapers concurrently]")
        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_to_name = {executor.submit(fn): name for name, fn in tasks}
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    res = future.result()
                    print(f"  [DONE] {name}: {len(res)} leads found.")
                    all_leads.extend(res)
                except Exception as e:
                    print(f"  [ERROR] {name}: {e}")

    new_saved, final_out = append_leads(args.out, all_leads, min_score=args.min_score)

    # Read all aggregated leads from CSV for JSON & HTML export
    aggregated_leads = []
    target_csv = final_out if os.path.exists(final_out) else args.out
    if os.path.exists(target_csv):
        with open(target_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                try:
                    r["score"] = int(r.get("score", 0))
                except ValueError:
                    r["score"] = 0
                aggregated_leads.append(r)

    # Export JSON
    final_json = export_json_leads(aggregated_leads, json_path=args.json)

    # Export HTML
    if not args.no_html:
        export_html_dashboard(aggregated_leads, html_path=args.html)
        print(f"Interactive outreach dashboard generated: {args.html}")

    print("\n" + "=" * 60)
    print(f"Total leads retrieved across sources: {len(all_leads)}")
    print(f"Leads meeting min-score (>={args.min_score}) & newly saved: {len(new_saved)}")
    print(f"Output saved to CSV:  {final_out}")
    print(f"Output saved to JSON: {final_json}")

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