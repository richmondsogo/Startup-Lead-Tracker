# Startup Lead Tracker (V3) 🚀

An automated lead generation, scoring, and 1-click outreach engine designed to discover high-intent contract, freelance, internship, and automation opportunities for developers, scraping specialists, students, and indie builders.

Rather than scraping generic news articles, this engine directly monitors platforms where founders, startups, and engineering managers actively post paid work, request developer help, or launch early products.

---

## ⚡ What's New in V3?

- **Concurrent Multi-Source Scraping**: Powered by Python's `ThreadPoolExecutor`, scraping all 7 public sources in parallel in under 15 seconds instead of sequential minutes.
- **Active Internship Scraping (`intern-list.com`)**: Scrapes live verified Airtable shared views for Software Engineering, Data Analysis, and AI/ML internships, complete with direct company application portal links.
- **Student-Focused Scoring Engine**: Boosts junior/entry-level/student opportunities (+25 pts) and filters out or penalizes senior/staff/director positions (-30 pts).
- **Modern shadcn/ui Dashboard**: A dedicated, responsive React + Tailwind CSS + shadcn/ui application (`dashboard/`) providing rich filtering, score sliders, search, table/grid views, and 1-click outreach.
- **Multi-Format Export**: Automatically saves to `leads.csv`, `leads.json`, and zero-dependency standalone `leads.html`.
- **API & Network Resilience**: Rate-limit protected GitHub domain resolver, smart browser headers for Reddit RSS, and automatic fallback file-lock handling for Excel users.

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. PUBLIC DATA SOURCES                          │
│                                                                        │
│  • HN "Who is hiring?"        • HN "Seeking freelancer?"               │
│  • HN Targeted Comments       • Show HN Launches                       │
│  • Reddit (r/forhire, etc.)   • intern-list.com (SWE, Data, AI/ML)     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ (Concurrent Scraping)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  2. CONTACT & DOMAIN RESOLUTION                        │
│                                                                        │
│  • Direct Email Regex: Extracts job/founder emails from post bodies    │
│  • Domain Cleaning: Strips out generic hosts (GitHub, Vercel, etc.)   │
│  • Email Guesses: Generates plausible mailboxes (hello@, founders@)    │
│  • Cached GitHub Profile API: Resolves owner blog/email with safety    │
│  • Date Tracking: Distinguishes 'posted_at' from 'found_at'           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    3. 6-FACTOR SCORING ENGINE (0-100)                  │
│                                                                        │
│  [Intent:  35 pts] Contract/freelance/intern > Full-time > Discovery   │
│  [Skill:   30 pts] Python, scraping, automation, bots, AI/LLM          │
│  [Stage:   20 pts] Solo founders, bootstrapped, seed > Enterprise      │
│  [Budget:  15 pts] Hourly, stipend, sweet-spot bounty > Unpaid         │
│  [Senior: -30 pts] Senior / Staff / Lead / Architect penalty           │
│  [Junior: +25 pts] Student / Intern / Junior / Entry-level boost       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             4. 1-CLICK OUTREACH & MULTI-FORMAT EXPORT                  │
│                                                                        │
│  • Tailored Pitch / Cover Letter: Context-aware personalized intro     │
│  • 1-Click Action Link: Pre-filled mailto:, apply link, or Reddit URL  │
│  • Modern shadcn Dashboard: React + Tailwind interactive visual center │
│  • Standalone HTML Dashboard: Zero-dependency 'leads.html'             │
│  • Safe CSV & JSON Persistence: 'leads.csv' and 'leads.json'           │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Getting Started

### 1. Requirements & Python Setup

```bash
# Install Python dependencies
pip install -r requirements.txt
```

### 2. Run the Lead Tracker

```bash
# Scan the last 7 days of opportunities (default)
python tracker.py

# Custom lookback window and minimum score filter
python tracker.py --days 3 --min-score 30

# Also include African tech news funding rounds
python tracker.py --include-news
```

CLI Options:
- `--days INT`: How many days back to search (default: 7)
- `--min-score INT`: Minimum score threshold 0-100 (default: 20)
- `--out PATH`: CSV output path (default: `leads.csv`)
- `--json PATH`: JSON output path (default: `leads.json`)
- `--html PATH`: HTML output path (default: `leads.html`)
- `--no-html`: Disable standalone HTML dashboard generation
- `--no-internships`: Disable intern-list.com scraping
- `--include-news`: Enable African tech funding/launch news feeds
- `--sequential`: Run scrapers sequentially instead of concurrently

---

## Modern shadcn/ui Dashboard

In addition to `leads.html`, the project includes a full-featured modern dashboard built with **React**, **Vite**, **Tailwind CSS**, and **shadcn/ui** components located in `dashboard/`.

### Run the Dashboard Locally:

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### Build Production Bundle:

```bash
cd dashboard
npm run build
```

The production static files are built to `dashboard/dist/` and can be served with any static web host or opened directly.

---

## 4-Factor & Student Scoring Engine

Every retrieved lead passes through a deterministic scoring model tailored for Python developers, automation builders, and students:

| Factor | Points | Heuristic |
| :--- | :---: | :--- |
| **Intent Strength** | **35** | Explicit contract, freelance, or internship intent (+35); full-time hiring (+20); collaboration/help wanted (+15); general discovery (+5). |
| **Skill Relevance** | **30** | Direct match for Python, scraping, crawling, automation, bots, AI/LLM, Playwright, FastAPI (+15 to +30); general backend stack (+5 to +10); disjoint stack penalty (-10). |
| **Stage & Team Fit** | **20** | Solo founder, bootstrapped, seed, indie hacker (+20); neutral startup (+5); large corporate/enterprise (-20). |
| **Budget Plausibility** | **15** | Sweet-spot hourly rate or stipend (+15); funded/established (+5); explicitly unpaid (-15). |
| **Seniority Penalty** | **-30** | Applied to roles specifying Senior, Staff, Principal, Lead, Architect, or 5+ years experience. |
| **Junior / Intern Boost** | **+25** | Applied to Internship, Junior, Entry-Level, Student, and New Grad opportunities. |

Final scores are normalized between `0` and `100`.

---

## Data Schema (`leads.csv` and `leads.json`)

| Field | Type | Description |
| :--- | :---: | :--- |
| `score` | integer | Total score (0–100) |
| `score_breakdown` | string | Transparent breakdown e.g. `Intent:+35\|Skill:+30\|Stage:+20\|Budget:+15` |
| `intent_type` | string | `internship`, `contract_hiring`, `fulltime_hiring`, `help_wanted`, `discovery` |
| `posted_at` | string | Date when the lead was originally published (YYYY-MM-DD) |
| `found_at` | string | Date when our engine scraped the lead |
| `source` | string | Source name (e.g. `HN Who is hiring`, `InternList (SWE)`, `Show HN`) |
| `company_or_author` | string | Company name or poster username |
| `title_or_role` | string | Position title or opportunity headline |
| `domain` | string | Cleaned root domain of company (excluding generic hosts) |
| `guessed_emails` | string | Plausible founder mailboxes (`hello@`, `jobs@`, `team@`) |
| `other_contact` | string | Direct contact emails, GitHub profile, or Twitter link |
| `summary_snippet` | string | Cleaned snippet summarizing the opportunity |
| `tailored_pitch` | string | Context-aware pitch hook or student cover letter intro |
| `quick_action` | string | Pre-filled URL (`mailto:`, apply link, or Reddit compose) |
| `article_link` | string | Canonical link to original post |

---

## License

MIT License. Free for developers, students, and indie hackers to track and win gigs!
