# Startup Lead Tracker (V2)

An automated lead generation and scoring engine designed to discover high-intent contract, freelance, and automation opportunities for Python developers, scraping specialists, and indie builders.

Rather than scraping generic news articles, this engine directly monitors platforms where founders, startups, and engineering managers actively post paid work, request developer help, or launch early products.

---

## What Changed in V2? (The Strategic Shift)

- **V1 (Passive News Discovery):** Relied on tech news RSS feeds (e.g., Techpoint Africa, TechCabal) scanning for keywords like *"raises seed round"*. While interesting, funding news rarely translates to immediate freelance work: contact details are missing, and companies that just raised institutional rounds usually hire full-time senior staff through formal recruiters.
- **V2 (Active Hiring Intent & Scoring):** Prioritizes platforms where founders and technical leads explicitly ask for help right now—such as Hacker News monthly hiring threads, freelance seeker posts, Reddit hiring communities, and Show HN product launches. Every lead is evaluated by a multi-factor scoring engine (0–100) that ranks contract suitability, Python automation relevance, and budget plausibility.

---

## How It Works

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. PUBLIC DATA SOURCES                          │
│                                                                        │
│  • HN "Who is hiring?"        • HN "Seeking freelancer?"               │
│  • HN Targeted Comments       • Show HN Launches                       │
│  • Reddit (r/forhire, etc.)   • African Tech News (Optional)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  2. CONTACT & DOMAIN RESOLUTION                        │
│                                                                        │
│  • Direct Email Regex: Extracts job/founder emails from post bodies    │
│  • Domain Cleaning: Strips out generic hosts (GitHub, Vercel, etc.)   │
│  • Email Guesses: Generates plausible mailboxes (hello@, founders@)    │
│  • GitHub Profile API: Resolves owner blog/email if only repo linked   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    3. 4-FACTOR SCORING ENGINE (0-100)                  │
│                                                                        │
│  [Intent: 35 pts]  Contract/freelance > Full-time > Help-wanted        │
│  [Skill:  30 pts]  Python, scraping, automation, bots, AI/LLM          │
│  [Stage:  20 pts]  Solo founders, bootstrapped, seed > Enterprise      │
│  [Budget: 15 pts]  $100-$500 sweet spot, hourly > Unpaid/equity-only   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   4. SAFE PERSISTENCE & CSV OUTPUT                     │
│                                                                        │
│  • Schema Migration Guard: Automatically archives V1 leads safely      │
│  • Deduplication: Avoids duplicate rows across repeated runs           │
│  • Sorted Output: Ranked descending by score (leads.csv)               │
│  • Safe URLs: article_link strictly positioned as the last column      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## The 4-Factor Scoring Engine (0 to 100 Points)

Every item retrieved passes through a deterministic scoring model tailored for a Python automation/scraping developer:

| Factor | Max Pts | Criteria & Scoring Breakdown |
| :--- | :---: | :--- |
| **1. Intent Strength** | **35** | • **+35 pts**: Explicit contract/freelance intent (`[HIRING]`, `seeking freelancer`, `contract`, `part-time`, `gig`, `bounty`).<br>• **+20 pts**: Full-time hiring post on Hacker News.<br>• **+15 pts**: Collaborative/help-wanted post (`looking for developer`, `co-founder`, `need help`).<br>• **+5 pts**: General product launch or news. |
| **2. Skill Relevance** | **30** | • **+15 to +30 pts**: Direct match for Python/automation sweet spot (`python`, `scraping`, `bot`, `automation`, `fastapi`, `ai`, `llm`, `crawler`, `data extraction`, `playwright`, `etl`).<br>• **+5 to +10 pts**: General backend stack (`api`, `sqlite`, `postgres`, `docker`).<br>• **-10 pts penalty**: Explicitly disjoint stack with zero Python matches (e.g. `iOS Swift only`, `Rust kernel`). |
| **3. Stage & Team Fit** | **20** | • **+20 pts**: Small/early team (`solo founder`, `bootstrapped`, `seed`, `pre-seed`, `indie hacker`, `<10 people`).<br>• **+5 pts**: Neutral startup.<br>• **-20 pts penalty**: Large corporate/enterprise (`Series B-F`, `100+ employees`, `fortune 500`). |
| **4. Budget Plausibility** | **15** | • **+15 pts**: Sweet spot budget mentioned (`$100-$500`, `$20-$50/hr`, `bounty`, `stipend`, `200/month`).<br>• **+5 pts**: Funded startup or established hiring thread.<br>• **-15 pts penalty**: Explicitly unpaid (`unpaid`, `equity-only`, `volunteer`). |

Final scores are clamped between `0` and `100`. Each row includes a readable `score_breakdown` (e.g. `Intent:35|Skill:30|Stage:20|Budget:15`).

---

## Supported Sources

All sources are free, publicly accessible, and require no paid API keys or logins:

1. **Hacker News "Who is hiring?"**
   - Official monthly thread posted on the 1st of every month by `whoishiring`.
   - The script retrieves the active month's thread via the Algolia API, parses top-level comments, and identifies roles tagged with `Remote`, `Contract`, or `Part-time`.
2. **Hacker News "Seeking freelancer?"**
   - Monthly thread where clients and founders look for freelance help.
   - Filters out freelancers offering services and highlights clients looking to hire.
3. **Hacker News Targeted Hiring Comments**
   - Real-time comment searches across all of Hacker News for phrases like `"seeking freelancer"`, `"hiring python"`, and `"looking for a developer"`.
4. **Hacker News "Show HN"**
   - Real-time product launches from indie developers and early founders.
   - Extracts founder websites, GitHub repositories, and contact info.
5. **Reddit Public Hiring RSS**
   - Monitored feeds: `r/forhire` (filtered by `flair:Hiring python`), `r/jobbit`, and `r/SideProject`.
   - Captures client posts with explicit budget figures and task scopes.
6. **African Tech News (Optional, via `--include-news`)**
   - Techpoint Africa and TechCabal RSS feeds filtered for funding rounds and product launches.

---

## Output CSV Schema (`leads.csv`)

The output is formatted for easy import into Google Sheets, Notion, Airtable, or manual review:

| Column | Description |
| :--- | :--- |
| `score` | Numerical score from 0 to 100 based on the 4-factor scoring model. |
| `score_breakdown` | Transparent breakdown: `Intent:X\|Skill:Y\|Stage:Z\|Budget:W`. |
| `intent_type` | Category: `contract_hiring`, `fulltime_hiring`, `help_wanted`, or `discovery`. |
| `found_at` | Date when the lead was discovered (`YYYY-MM-DD`). |
| `source` | Source name (e.g., `HN Who is hiring`, `Reddit (r/forhire)`, `Show HN`). |
| `company_or_author` | Company name or post author. |
| `title_or_role` | Headline, job title, or role summary. |
| `domain` | Company's own website domain (cleaned; excluding generic hosts). |
| `guessed_emails` | Generated contact mailboxes (`hello@`, `team@`, `founders@`, `contact@`, etc.). |
| `other_contact` | Extracted direct emails, GitHub profiles, and Twitter/X handles. |
| `summary_snippet` | Clean, stripped excerpt of the post text explaining what they need. |
| `article_link` | Link to the original thread, post, or article (**strictly last column**). |

> [!NOTE]
> **Why `article_link` is strictly the last column:**
> Many modern terminal applications and text editors auto-detect hyperlinks. If a URL is followed by a comma and more fields on the same line, the terminal linkifier often swallows the remaining text into a broken URL. Placing `article_link` at the very end ensures the URL is cleanly isolated at the end of the line.

---

## Quickstart & Installation

### 1. Prerequisites
Python 3.8+ installed.

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Scanner

Run with default settings (scans the past 7 days, filters for leads with score >= 20):
```bash
python tracker.py
```

Search the past 14 days with a higher quality threshold:
```bash
python tracker.py --days 14 --min-score 40
```

Include African tech news feeds (Techpoint, TechCabal):
```bash
python tracker.py --include-news
```

Output to a custom file:
```bash
python tracker.py --out my_weekly_leads.csv
```

---

## CLI Options Reference

| Option | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `--days` | `int` | `7` | Number of days back to search across feeds and APIs. |
| `--min-score` | `int` | `20` | Minimum score threshold (0–100) required to save a lead to CSV. |
| `--out` | `str` | `leads.csv` | Path of the destination CSV file. |
| `--include-news` | `flag` | `False` | Also scan Techpoint and TechCabal RSS feeds. |

---

## Safe Migration & Deduplication

- **Deduplication:** The script loads all existing `article_link` entries in the output CSV before running. Re-running the script daily or weekly will only append brand-new, unseen leads.
- **V1 Archive Protection:** If the script detects an existing `leads.csv` written in the older V1 format, it automatically copies the existing file to `leads_v1_archive.csv` so no past data is lost, before generating the new V2 file.

---

## Recommended Outreach Workflow

1. **Sort & Scan:** Open `leads.csv` in Excel, Google Sheets, or VS Code. Focus on rows with `score >= 60`.
2. **Review Snippet & Link:** Read `summary_snippet` to understand their exact pain point (e.g. *"need a scraper for real estate data"*, *"looking for someone to build an automated sync bot"*).
3. **Check Contacts:** 
   - Check `other_contact` first: If the founder provided a direct email or GitHub handle, use that directly.
   - Check `guessed_emails` & `domain`: If only a domain is present, check their website's contact form or test `founders@<domain>` using a free email verifier.
4. **Send a Tailored, Low-Risk Pitch:**
   - Mention their specific post and problem.
   - Highlight your Python/automation expertise.
   - Offer a quick, low-cost proof-of-concept (e.g., *"I can build a working prototype script in 48 hours for $100-$200"*).
