# Startup Lead Tracker (V2)

An automated lead generation, scoring, and 1-click outreach engine designed to discover high-intent contract, freelance, and automation opportunities for Python developers, scraping specialists, and indie builders.

Rather than scraping generic news articles, this engine directly monitors platforms where founders, startups, and engineering managers actively post paid work, request developer help, or launch early products.

---

## What Changed in V2? (The Strategic Shift)

- **V1 (Passive News Discovery):** Relied on tech news RSS feeds (e.g., Techpoint Africa, TechCabal) scanning for keywords like *"raises seed round"*. While interesting, funding news rarely translates to immediate freelance work: contact details are missing, and companies that just raised institutional rounds usually hire full-time senior staff through formal recruiters.
- **V2 (Active Hiring Intent & 1-Click Outreach):** Prioritizes platforms where founders and technical leads explicitly ask for help right now—such as Hacker News monthly hiring threads, freelance seeker posts, Reddit hiring communities, and Show HN product launches. Every lead is evaluated by a multi-factor scoring engine (0–100), enriched with publishing date tracking, equipped with an auto-generated cold pitch hook, and exported both to CSV and an interactive HTML outreach dashboard.

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
│  • Date Tracking: Extracts exact 'posted_at' date across all feeds     │
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
│             4. 1-CLICK OUTREACH & MULTI-FORMAT EXPORT                  │
│                                                                        │
│  • Tailored Pitch Hook: Context-aware 2-3 sentence personalized pitch  │
│  • 1-Click Action Link: Pre-filled mailto: or Reddit compose URL       │
│  • Interactive Dashboard: 'leads.html' with filters & search           │
│  • Safe CSV Persistence: 'leads.csv' with deduplication & lock safety  │
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

Final scores are clamped between `0` and `100`. Each row includes a transparent `score_breakdown` (e.g. `Intent:35|Skill:30|Stage:20|Budget:15`).

---

## Innovations in V2

### 1. Date Job Was Posted (`posted_at`)
Distinguishes between when a lead was published (`posted_at`) and when our scanner scraped it (`found_at`). This lets you prioritize leads posted in the last 24–48 hours before other applicants flood the post.

### 2. The 1-Click Outreach Engine
Most cold outreach fails because of two friction points: crafting a personalized pitch and manually composing messages. 
- **`tailored_pitch`**: Inspects the post content and automatically drafts an icebreaker pitch referencing their exact requirements (e.g., Python scraping, AI workflow automation, vector database support) and proposes a rapid 48-hour prototype for $150–$200.
- **`quick_action`**: A pre-filled URL. Clicking it immediately opens your default mail client with `mailto:` or opens the Reddit message compose window with the author, subject, and tailored pitch already filled out!

### 3. Interactive HTML Dashboard (`leads.html`)
Alongside the CSV, the scanner automatically outputs a standalone, zero-dependency dark-mode visual board. You can filter by score (e.g., 60+), filter by contract type, search keywords in real time, copy pitches with one click, or trigger instant outreach.

### 4. File-Lock Resilience (Windows-Safe)
If `leads.csv` is currently open in Microsoft Excel or another viewer that locks the file exclusively, the script automatically catches the lock and saves to `leads_new.csv` with a helpful notice instead of crashing.

---

## Supported Sources

All sources are free, publicly accessible, and require no paid API keys or logins:

1. **Hacker News "Who is hiring?"**
   - Official monthly thread posted on the 1st of every month by `whoishiring`.
   - Parses top-level comments and identifies roles tagged with `Remote`, `Contract`, or `Part-time`.
2. **Hacker News "Seeking freelancer?"**
   - Monthly thread where clients and founders look for freelance contractors.
3. **Hacker News Targeted Hiring Comments**
   - Real-time comment searches across all of Hacker News for phrases like `"seeking freelancer"`, `"hiring python"`, and `"looking for a developer"`.
4. **Hacker News "Show HN"**
   - Real-time product launches from indie developers and early founders.
5. **Reddit Public Hiring RSS**
   - Monitored feeds: `r/forhire` (filtered by `flair:Hiring python`), `r/jobbit`, and `r/SideProject`.
6. **African Tech News (Optional, via `--include-news`)**
   - Techpoint Africa and TechCabal RSS feeds filtered for funding rounds and product launches.

---

## Output CSV Schema (`leads.csv`)

| Column | Description |
| :--- | :--- |
| `score` | Numerical score from 0 to 100 based on the 4-factor scoring model. |
| `score_breakdown` | Transparent breakdown: `Intent:X\|Skill:Y\|Stage:Z\|Budget:W`. |
| `intent_type` | Category: `contract_hiring`, `fulltime_hiring`, `help_wanted`, or `discovery`. |
| `posted_at` | Date when the job or post was actually published (`YYYY-MM-DD`). |
| `found_at` | Date when the scanner discovered the lead (`YYYY-MM-DD`). |
| `source` | Source platform (e.g., `HN Who is hiring`, `Reddit (r/forhire)`, `Show HN`). |
| `company_or_author` | Company name or Reddit/HN author handle. |
| `title_or_role` | Headline, job title, or role summary. |
| `domain` | Company's own website domain (cleaned; excluding generic hosts). |
| `guessed_emails` | Generated contact mailboxes (`hello@`, `team@`, `founders@`, `contact@`, etc.). |
| `other_contact` | Extracted direct emails, GitHub profiles, and Twitter/X handles. |
| `summary_snippet` | Clean, stripped excerpt of the post text explaining what they need. |
| `tailored_pitch` | Context-aware, pre-written personalized cold pitch hook. |
| `quick_action` | Direct 1-click outreach link (`mailto:` or Reddit compose with pitch prefilled). |
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

Run with default settings (scans the past 7 days, filters for leads with score >= 20, generates `leads.csv` and `leads.html`):
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
python tracker.py --out my_leads.csv --html my_dashboard.html
```

---

## CLI Options Reference

| Option | Type | Default | Description |
| :--- | :---: | :---: | :--- |
| `--days` | `int` | `7` | Number of days back to search across feeds and APIs. |
| `--min-score` | `int` | `20` | Minimum score threshold (0–100) required to save a lead to CSV. |
| `--out` | `str` | `leads.csv` | Path of the destination CSV file. |
| `--html` | `str` | `leads.html` | Path of the generated interactive HTML dashboard. |
| `--no-html` | `flag` | `False` | Disable HTML dashboard generation. |
| `--include-news` | `flag` | `False` | Also scan Techpoint and TechCabal RSS feeds. |

---

## Recommended Outreach Workflow

1. **Open the Dashboard:** Open `leads.html` in any web browser.
2. **Filter High-Fit Gigs:** Click the **"High Fit (60+)"** or **"Contract Only"** filter button.
3. **Review & Reach Out:**
   - Review the pre-written **Tailored Cold Pitch Hook**.
   - Click **"⚡ 1-Click Outreach"** to immediately open a pre-filled email or Reddit compose message.
   - Alternatively, click **"Copy Pitch"** to paste it into LinkedIn, Twitter/X, or an application form.
