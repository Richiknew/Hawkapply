"""
Universal Career Page Scraper — auto-detects ATS and scrapes any company.

Covers 100+ H1B sponsor companies across 5 ATS platforms:
  - Greenhouse (~40% of tech) — Netflix, Airbnb, Stripe, Palantir, etc.
  - Lever (~20%) — Spotify, Reddit, Instacart, etc.
  - Ashby (~10%) — OpenAI, Anthropic, Cohere, etc.
  - SmartRecruiters (~5%) — Visa, KPMG, etc.
  - Workday (~25% of enterprise) — Capital One, JPMorgan, Goldman, Adobe, etc.

All APIs are public, free, no auth needed.
Every job is auto-marked sponsors_h1b=True since these are known sponsors.

Usage:
    python -m scrapers.career_scraper_v2
"""

import re
import time
import requests
from datetime import datetime
from typing import Optional
from config import settings
from db.models import Job
from scrapers.indeed_scraper import parse_salary


DS_KEYWORDS = [
    "data scientist", "data science", "machine learning",
    "ml engineer", "deep learning", "ai engineer",
    "applied scientist", "research scientist", "mlops",
    "analytics engineer", "nlp", "computer vision",
    "marketing scien", "ad tech", "risk model",
    "forecasting", "supply chain", "quant",
    "data engineer", "pricing", "attribution",
    "data analy",
]


def _is_ds_role(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in DS_KEYWORDS)


def _is_us(location: str) -> bool:
    loc = location.lower()
    reject = [
        "india", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad", "pune", "chennai",
        "china", "shenzhen", "guangzhou", "beijing", "shanghai",
        "canada", "toronto", "vancouver", "montreal",
        "united kingdom", "london", "germany", "berlin", "france", "paris",
        "netherlands", "amsterdam", "australia", "sydney", "melbourne",
        "singapore", "hong kong", "japan", "tokyo", "brazil", "argentina",
        "spain", "madrid", "italy", "milan", "poland", "warsaw", "romania",
        "apac", "latam", "emea",
    ]
    if any(s in loc for s in reject):
        return False

    signals = [
        "united states", ", us", "usa", "u.s.", "remote",
        "new york", "san francisco", "seattle", "boston",
        "chicago", "austin", "los angeles", "denver",
        "washington", "philadelphia", "atlanta", "dallas",
        "houston", "miami", "portland", "phoenix",
        "san jose", "san diego", "raleigh", "charlotte",
        "pittsburgh", "baltimore", "minneapolis", "detroit",
        "salt lake", "tampa", "jersey city", "newark",
        ", ny", ", ca", ", wa", ", ma", ", il", ", tx",
        ", co", ", ga", ", pa", ", va", ", md", ", nc",
        ", nj", ", ct", ", fl", ", az", ", ut", ", mn",
        ", mi", ", oh", ", or", ", mo",
    ]
    return any(s in loc for s in signals)


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(s[:26], fmt)
        except ValueError:
            continue
    return None


HDR = {"User-Agent": settings.USER_AGENT}


# ═══════════════ GREENHOUSE ═══════════════

GREENHOUSE = {
    # Original
    "Netflix": "netflix", "Airbnb": "airbnb", "DoorDash": "doordash",
    "Stripe": "stripe", "Coinbase": "coinbase", "Plaid": "plaid",
    "Robinhood": "robinhood", "Figma": "figma", "Notion": "notion",
    "Discord": "discord", "Duolingo": "duolingo", "HubSpot": "hubspot",
    "Datadog": "datadog", "Twilio": "twilio", "Affirm": "affirm",
    "Brex": "brex", "Scale AI": "scaleai", "Weights & Biases": "wandb",
    "Databricks": "databricks", "Pinterest": "pinterest", "Etsy": "etsy",
    "Snap": "snapchat", "Roku": "roku", "MongoDB": "mongodb",
    "Elastic": "elastic", "Confluent": "confluent",
    "Palantir": "palantirtechnologies", "Two Sigma": "twosigma",
    "D.E. Shaw": "deshaw", "Jane Street": "janestreet",
    "Point72": "point72", "Citadel": "citadel",
    "AQR Capital": "aqr", "Bridgewater Associates": "bridgewaterassociates",
    "Rivian": "rivian", "Waymo": "waymo", "Moderna": "modernatx",
    "Regeneron": "regeneron", "Block": "block", "Okta": "okta",
    "Palo Alto Networks": "paloaltonetworks", "ServiceNow": "servicenow",
    "DocuSign": "docusign", "Zillow": "zillowgroup", "Redfin": "redfin",
    "Wayfair": "wayfair", "Starbucks": "starbucks", "Nike": "nike",
    "Bloomberg": "bloomberg", "Thomson Reuters": "thomsonreuters",
    "Uber": "uber", "Tesla": "tesla", "Lyft": "lyft",
    # Expanded — Cloud / SaaS / DevTools
    "Atlassian": "atlassian", "Asana": "asana", "Box": "box",
    "Cloudflare": "cloudflare", "HashiCorp": "hashicorp",
    "Amplitude": "amplitude", "Carta": "carta", "Gusto": "gusto",
    "Retool": "retool", "Airtable": "airtable", "Samsara": "samsara",
    "PagerDuty": "pagerduty", "New Relic": "newrelic",
    "JFrog": "jfrog", "Braze": "braze", "FullStory": "fullstory",
    "Intercom": "intercom", "Gong": "gong", "Procore": "procore",
    "GitHub": "github", "Miro": "miro", "Calendly": "calendly",
    "Monday.com": "mondaydotcom", "Zendesk": "zendesk",
    # Cybersecurity
    "SentinelOne": "sentinelone", "Wiz": "wizsecurity",
    "Snyk": "snyk", "Lacework": "lacework",
    # Fintech / Payments
    "Adyen": "adyen", "Lattice": "lattice", "Rippling": "rippling",
    # Healthcare / Biotech
    "Illumina": "illumina", "10x Genomics": "10xgenomics",
    "Guardant Health": "guardanthealth", "Recursion": "recursionpharmaceuticals",
    "Flatiron Health": "flatiron", "Tempus AI": "tempus",
    # Real Estate / Proptech
    "Compass": "compass", "Opendoor": "opendoor",
    # Data / Analytics
    "dbt Labs": "dbtlabs", "Fivetran": "fivetran",
    # Gaming
    "Epic Games": "epicgames", "Riot Games": "riotgames",
    "Roblox": "roblox", "Unity": "unity",
    # Travel / EdTech
    "Coursera": "coursera", "Tripadvisor": "tripadvisor", "Expedia": "expedia",
    # Sports
    "DraftKings": "draftkings",
    # HR Tech
    "Handshake": "handshake",
    # Logistics
    "Flexport": "flexport",
    # Veeva
    "Veeva Systems": "veeva",
}

def _gh(company: str, slug: str) -> list[Job]:
    try:
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                        params={"content": "true"}, timeout=15, headers=HDR)
        if r.status_code != 200: return []
        data = r.json()
    except Exception: return []

    jobs = []
    for item in data.get("jobs", []):
        title = item.get("title", "")
        if not _is_ds_role(title): continue
        loc = item.get("location", {}).get("name", "")
        if not _is_us(loc): continue
        desc = re.sub(r'<[^>]+>', ' ', item.get("content", ""))[:2000]
        smin, smax = None, None
        for f in (item.get("metadata") or []):
            if "salary" in f.get("name", "").lower():
                smin, smax = parse_salary(str(f.get("value", "")))
        jobs.append(Job(title=title, company=company, location=loc,
            source="career_page", url=item.get("absolute_url", ""),
            description=desc, salary_min=smin, salary_max=smax,
            posted_date=_parse_date(item.get("updated_at")), sponsors_h1b=True))
    return jobs


# ═══════════════ LEVER ═══════════════

LEVER = {
    # Original
    "Spotify": "spotify", "Reddit": "reddit", "Instacart": "instacart",
    "Grammarly": "grammarly", "Dropbox": "dropbox", "Chime": "chime",
    "SoFi": "sofi", "Marqeta": "marqeta", "Canva": "canva",
    "Zscaler": "zscaler",
    # Expanded
    "Faire": "faire", "Snyk": "snyk", "Netlify": "netlify",
    "CockroachLabs": "cockroachlabs", "Deel": "deel",
    "DigitalOcean": "digitalocean", "Contentful": "contentful",
    "Airbyte": "airbyte", "Monte Carlo": "montecarlodata",
    "Nextdoor": "nextdoor", "Quora": "quora",
    "ZipRecruiter": "ziprecruiter", "Verkada": "verkada",
    "Superhuman": "superhuman", "Loom": "loopio",
    "Hims": "hims", "Oscar Health": "oscarhealth",
    "Devoted Health": "devoted", "GoodRx": "goodrx",
    "Noom": "noom",
}

def _lv(company: str, slug: str) -> list[Job]:
    try:
        r = requests.get(f"https://api.lever.co/v0/postings/{slug}",
                        params={"mode": "json"}, timeout=15, headers=HDR)
        if r.status_code != 200: return []
        data = r.json()
    except Exception: return []

    jobs = []
    for item in data:
        title = item.get("text", "")
        if not _is_ds_role(title): continue
        loc = item.get("categories", {}).get("location", "")
        if not _is_us(loc): continue
        desc = re.sub(r'<[^>]+>', ' ', item.get("additional", ""))[:2000]
        ts = item.get("createdAt")
        posted = datetime.fromtimestamp(int(ts)/1000) if ts else None
        jobs.append(Job(title=title, company=company, location=loc,
            source="career_page", url=item.get("hostedUrl", ""),
            description=desc, posted_date=posted, sponsors_h1b=True))
    return jobs


# ═══════════════ ASHBY ═══════════════

ASHBY = {
    # Original
    "OpenAI": "openai", "Anthropic": "anthropic",
    "Cohere": "cohere", "Ramp": "ramp", "Anyscale": "anyscale",
    # Expanded — AI-native & modern startups predominately use Ashby
    "Perplexity AI": "perplexityai", "Groq": "groq",
    "Together AI": "togetherai", "Cerebras": "cerebras",
    "Runway": "runwayml", "Harvey": "harvey",
    "Writer": "writer", "Weaviate": "weaviate",
    "Pinecone": "pinecone", "LangChain": "langchain",
    "Modal": "modal", "Replit": "replit",
    "Adept": "adept", "Glean": "glean",
    "Mapbox": "mapbox", "Linear": "linear",
    "Coda": "coda", "Notion Calendar": "notionhq",
    "dbt Labs Ashby": "dbtlabs",
    "Stability AI": "stabilityai",
}

def _ab(company: str, slug: str) -> list[Job]:
    try:
        r = requests.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                        timeout=15, headers=HDR)
        if r.status_code != 200: return []
        data = r.json()
    except Exception: return []

    jobs = []
    for item in data.get("jobs", []):
        title = item.get("title", "")
        if not _is_ds_role(title): continue
        loc = item.get("location", "")
        if not _is_us(loc): continue
        jobs.append(Job(title=title, company=company, location=loc,
            source="career_page", url=item.get("jobUrl", ""),
            description=item.get("descriptionPlain", "")[:2000],
            posted_date=_parse_date(item.get("publishedAt")), sponsors_h1b=True))
    return jobs


# ═══════════════ SMARTRECRUITERS ═══════════════

SMARTRECRUITERS = {
    # Original
    "Visa": "Visa", "KPMG": "KPMG",
    "Booz Allen Hamilton": "BoozAllenHamilton",
    "Siemens": "Siemens", "Honeywell": "Honeywell",
    # Expanded
    "Cognizant": "Cognizant", "Capgemini": "Capgemini",
    "NTT Data": "NTTData", "L3Harris": "L3Harris",
    "Hitachi": "Hitachi",
}

def _sr(company: str, slug: str) -> list[Job]:
    try:
        r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                        params={"q": "data scientist", "limit": 50},
                        timeout=15, headers=HDR)
        if r.status_code != 200: return []
        data = r.json()
    except Exception: return []

    jobs = []
    for item in data.get("content", []):
        title = item.get("name", "")
        if not _is_ds_role(title): continue
        l = item.get("location", {})
        loc = f"{l.get('city','')}, {l.get('region','')}".strip(", ")
        if l.get("country", "").upper() not in ("US", ""): continue
        desc = item.get("jobAd", {}).get("sections", {}).get(
            "jobDescription", {}).get("text", "")
        clean = re.sub(r'<[^>]+>', ' ', desc)[:2000]
        jobs.append(Job(title=title, company=company, location=loc,
            source="career_page", url=item.get("ref", ""),
            description=clean, posted_date=_parse_date(item.get("releasedDate")),
            sponsors_h1b=True))
    return jobs


# ═══════════════ WORKDAY ═══════════════

WORKDAY = {
    # ── Original ──────────────────────────────────────────────────────────────
    "Capital One": "https://capitalone.wd1.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs",
    "Walmart": "https://walmart.wd5.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs",
    "Deloitte": "https://apply.deloitte.com/wday/cxs/deloitte/Deloitte_Experienced/jobs",
    "Accenture": "https://accenture.wd3.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs",
    "EY": "https://eyglobal.wd1.myworkdayjobs.com/wday/cxs/eyglobal/EY_Experienced/jobs",
    "PwC": "https://pwc.wd3.myworkdayjobs.com/wday/cxs/pwc/Global_Experienced_Careers/jobs",
    "IBM": "https://ibm.wd1.myworkdayjobs.com/wday/cxs/ibm/IBM_Careers/jobs",
    "Cisco": "https://cisco.wd1.myworkdayjobs.com/wday/cxs/cisco/Cisco_Careers/jobs",
    "Intel": "https://intel.wd1.myworkdayjobs.com/wday/cxs/intel/External/jobs",
    "Qualcomm": "https://qualcomm.wd5.myworkdayjobs.com/wday/cxs/qualcomm/External/jobs",
    "Adobe": "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs",
    "Mastercard": "https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/CorporateCareers/jobs",
    "American Express": "https://aexp.wd5.myworkdayjobs.com/wday/cxs/aexp/Search/jobs",
    "PayPal": "https://paypal.wd1.myworkdayjobs.com/wday/cxs/paypal/jobs/jobs",
    "Goldman Sachs": "https://goldmansachs.wd1.myworkdayjobs.com/wday/cxs/goldmansachs/GS_Careers/jobs",
    "Morgan Stanley": "https://morganstanley.wd5.myworkdayjobs.com/wday/cxs/morganstanley/Morgan_Stanley_Careers/jobs",
    "Bank of America": "https://bankofamerica.wd1.myworkdayjobs.com/wday/cxs/bankofamerica/Campus_Experienced/jobs",
    "Citigroup": "https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs",
    "Wells Fargo": "https://wellsfargo.wd1.myworkdayjobs.com/wday/cxs/wellsfargo/WellsFargoJobs/jobs",
    "BlackRock": "https://blackrock.wd1.myworkdayjobs.com/wday/cxs/blackrock/BlackRock_Careers/jobs",
    "Fidelity": "https://fidelity.wd5.myworkdayjobs.com/wday/cxs/fidelity/FidelityCareers/jobs",
    "Vanguard": "https://vanguard.wd5.myworkdayjobs.com/wday/cxs/vanguard/Vanguard_Careers/jobs",
    "Target": "https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs",
    "Home Depot": "https://homedepot.wd1.myworkdayjobs.com/wday/cxs/homedepot/HomeDepot/jobs",
    "Johnson & Johnson": "https://jnj.wd5.myworkdayjobs.com/wday/cxs/jnj/JNJ_Careers/jobs",
    "Pfizer": "https://pfizer.wd1.myworkdayjobs.com/wday/cxs/pfizer/PfizerCareers/jobs",
    "Merck": "https://merck.wd5.myworkdayjobs.com/wday/cxs/merck/Merck_Careers/jobs",
    "UnitedHealth Group": "https://uhg.wd1.myworkdayjobs.com/wday/cxs/uhg/UHGCareers/jobs",
    "Procter & Gamble": "https://pg.wd1.myworkdayjobs.com/wday/cxs/pg/PG_Experienced/jobs",
    "General Electric": "https://ge.wd5.myworkdayjobs.com/wday/cxs/ge/GE_Careers/jobs",
    "Ford": "https://ford.wd1.myworkdayjobs.com/wday/cxs/ford/FordCareers/jobs",
    "GM": "https://gm.wd5.myworkdayjobs.com/wday/cxs/gm/Careers_for_Experienced/jobs",
    "Boeing": "https://boeing.wd1.myworkdayjobs.com/wday/cxs/boeing/EXTERNAL/jobs",
    "Lockheed Martin": "https://lockheedmartin.wd1.myworkdayjobs.com/wday/cxs/lockheedmartin/search/jobs",
    "Raytheon": "https://rtx.wd1.myworkdayjobs.com/wday/cxs/rtx/RTX_Careers/jobs",
    "Northrop Grumman": "https://northropgrumman.wd1.myworkdayjobs.com/wday/cxs/northropgrumman/Northrop_Grumman_Careers/jobs",
    "T-Mobile": "https://tmobile.wd1.myworkdayjobs.com/wday/cxs/tmobile/External/jobs",
    "Verizon": "https://verizon.wd5.myworkdayjobs.com/wday/cxs/verizon/Verizon_Careers/jobs",
    "Comcast": "https://comcast.wd5.myworkdayjobs.com/wday/cxs/comcast/Comcast_Careers/jobs",
    "Disney": "https://disney.wd5.myworkdayjobs.com/wday/cxs/disney/DisneyCareerSite/jobs",
    "NBCUniversal": "https://nbcunicareers.wd5.myworkdayjobs.com/wday/cxs/nbcunicareers/NBCU_Careers/jobs",
    "JPMorgan Chase": "https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions",
    # ── Expanded ──────────────────────────────────────────────────────────────
    "Salesforce": "https://salesforce.wd12.myworkdayjobs.com/wday/cxs/salesforce/External/jobs",
    "Nvidia": "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs",
    "Snowflake": "https://snowflake.wd5.myworkdayjobs.com/wday/cxs/snowflake/SnowflakeCareers/jobs",
    "AbbVie": "https://abbvie.wd1.myworkdayjobs.com/wday/cxs/abbvie/External/jobs",
    "Eli Lilly": "https://lilly.wd1.myworkdayjobs.com/wday/cxs/lilly/LillyCareers/jobs",
    "Amgen": "https://amgen.wd1.myworkdayjobs.com/wday/cxs/amgen/External/jobs",
    "AstraZeneca": "https://astrazeneca.wd3.myworkdayjobs.com/wday/cxs/astrazeneca/AstraZenecaExternalCareers/jobs",
    "Bristol-Myers Squibb": "https://bms.wd5.myworkdayjobs.com/wday/cxs/bms/External/jobs",
    "CVS Health": "https://cvshealth.wd1.myworkdayjobs.com/wday/cxs/cvshealth/CVSHealth_External/jobs",
    "Elevance Health": "https://elevancehealth.wd1.myworkdayjobs.com/wday/cxs/elevancehealth/External/jobs",
    "Cigna": "https://cigna.wd5.myworkdayjobs.com/wday/cxs/cigna/Cigna_External/jobs",
    "AT&T": "https://att.wd1.myworkdayjobs.com/wday/cxs/att/External/jobs",
    "BNY Mellon": "https://bnymellon.wd5.myworkdayjobs.com/wday/cxs/bnymellon/External/jobs",
    "Charles Schwab": "https://schwab.wd5.myworkdayjobs.com/wday/cxs/schwab/CareerSite/jobs",
    "Fiserv": "https://fiserv.wd5.myworkdayjobs.com/wday/cxs/fiserv/FiservExternal/jobs",
}

WORKDAY_QUERIES = ["data scientist", "machine learning", "AI engineer", "applied scientist"]

def _wd(company: str, api_url: str) -> list[Job]:
    jobs = []
    base = api_url.rsplit("/jobs", 1)[0]

    for query in WORKDAY_QUERIES:
        payload = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": query}
        try:
            r = requests.post(api_url, json=payload, timeout=15,
                             headers={**HDR, "Content-Type": "application/json"})
            if r.status_code != 200: continue
            data = r.json()
        except Exception: continue

        for item in data.get("jobPostings", []):
            title = item.get("title", "")
            if not _is_ds_role(title): continue
            loc = item.get("locationsText", "")
            if not _is_us(loc): continue
            ext = item.get("externalPath", "")
            url = f"{base}{ext}" if ext else ""
            jobs.append(Job(title=title, company=company, location=loc,
                source="career_page", url=url,
                posted_date=_parse_date(item.get("postedOn")), sponsors_h1b=True))

    return jobs


# ═══════════════ ORCHESTRATOR ═══════════════

def scrape_all_career_pages() -> list[Job]:
    all_jobs: list[Job] = []
    total = len(GREENHOUSE) + len(LEVER) + len(ASHBY) + len(SMARTRECRUITERS) + len(WORKDAY)

    print(f"  🏢 Scraping {total} company career pages...\n")

    for label, mapping, fn in [
        ("Greenhouse", GREENHOUSE, _gh),
        ("Lever", LEVER, _lv),
        ("Ashby", ASHBY, _ab),
        ("SmartRecruiters", SMARTRECRUITERS, _sr),
    ]:
        print(f"    {label} ({len(mapping)} companies)...")
        for company, slug in mapping.items():
            jobs = fn(company, slug)
            all_jobs.extend(jobs)
            if jobs:
                print(f"      ✅ {company}: {len(jobs)} DS roles")
            time.sleep(0.3)

    print(f"\n    Workday ({len(WORKDAY)} companies)...")
    for company, url in WORKDAY.items():
        jobs = _wd(company, url)
        all_jobs.extend(jobs)
        if jobs:
            print(f"      ✅ {company}: {len(jobs)} DS roles")
        time.sleep(0.3)

    # Deduplicate
    seen = set()
    unique = []
    for j in all_jobs:
        if j.job_hash not in seen:
            seen.add(j.job_hash)
            unique.append(j)

    print(f"\n  📊 Career pages: {len(unique)} unique DS jobs from {total} sponsor companies")
    return unique


if __name__ == "__main__":
    jobs = scrape_all_career_pages()
    print(f"\n{'='*60}")
    print(f"Found {len(jobs)} DS jobs:\n")
    for j in jobs:
        print(f"  {j.title} @ {j.company} — {j.location}")
        print(f"    🔗 {j.url[:80]}")
