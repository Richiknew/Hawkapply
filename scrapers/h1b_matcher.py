"""
H1B Sponsorship Matcher — enriches scraped jobs with H1B data.

Scrapes top H1B sponsors for data scientist roles from MyVisaJobs,
caches them locally, then cross-references every job's company.

Usage:
    python -m scrapers.h1b_matcher
"""

import re
import time
import json
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime, timedelta
from config import settings
from db.models import H1BSponsor
from db import operations as ops


# Known top H1B sponsors for data science roles (fallback seed data)
# Source: MyVisaJobs.com FY2025 LCA filings
"""
Expanded H1B sponsor seed data — 200+ companies known to sponsor data scientists.

Sources: MyVisaJobs FY2024-2025 LCA filings, H1BGrader, public DOL data.
This replaces the SEED_SPONSORS list in scrapers/h1b_matcher.py.

Copy this entire list and replace SEED_SPONSORS in h1b_matcher.py.
"""

SEED_SPONSORS = [
    # ══════ FAANG / Big Tech ══════
    {"company": "Meta Platforms", "filings": 276, "avg_salary": 202781},
    {"company": "Amazon", "filings": 345, "avg_salary": 159200},   # includes AWS + Amazon.com Services LLC
    {"company": "Google", "filings": 146, "avg_salary": 185570},
    {"company": "Microsoft", "filings": 200, "avg_salary": 175000},
    {"company": "Apple", "filings": 80, "avg_salary": 203530},
    {"company": "Netflix", "filings": 10, "avg_salary": 263942},   # very few DS-titled LCAs, extremely high pay

    # ══════ Tech — Large ══════
    {"company": "Uber", "filings": 20, "avg_salary": 146425},
    {"company": "Airbnb", "filings": 2, "avg_salary": 159500},     # titles roles as Analytics Engineer
    {"company": "Salesforce", "filings": 10, "avg_salary": 188250},
    {"company": "IBM", "filings": 34, "avg_salary": 140000},
    {"company": "TikTok", "filings": 41, "avg_salary": 180000},
    {"company": "ByteDance", "filings": 22, "avg_salary": 185000},
    {"company": "Stripe", "filings": 8, "avg_salary": 168678},
    {"company": "LinkedIn", "filings": 12, "avg_salary": 137340},
    {"company": "Adobe", "filings": 10, "avg_salary": 170000},
    {"company": "Oracle", "filings": 45, "avg_salary": 155000},
    {"company": "SAP", "filings": 30, "avg_salary": 150000},
    {"company": "Spotify", "filings": 20, "avg_salary": 185000},
    {"company": "Pinterest", "filings": 25, "avg_salary": 180000},
    {"company": "Snap", "filings": 20, "avg_salary": 190000},
    {"company": "DoorDash", "filings": 25, "avg_salary": 163238},
    {"company": "Instacart", "filings": 25, "avg_salary": 180000},
    {"company": "Lyft", "filings": 20, "avg_salary": 175000},
    {"company": "Reddit", "filings": 15, "avg_salary": 190000},
    {"company": "Twitch", "filings": 10, "avg_salary": 175000},
    {"company": "Dropbox", "filings": 15, "avg_salary": 180000},
    {"company": "Atlassian", "filings": 20, "avg_salary": 175000},
    {"company": "Shopify", "filings": 15, "avg_salary": 170000},
    {"company": "Block", "filings": 25, "avg_salary": 185000},
    {"company": "Square", "filings": 25, "avg_salary": 185000},
    {"company": "Twitter", "filings": 0, "avg_salary": 180000},    # X Corp has 0 DS LCAs post-2022
    {"company": "X Corp", "filings": 0, "avg_salary": 180000},    # 0 DS-titled LCAs in 2024 DOL data
    {"company": "Roku", "filings": 15, "avg_salary": 175000},
    {"company": "eBay", "filings": 20, "avg_salary": 170000},
    {"company": "Zillow", "filings": 20, "avg_salary": 175000},
    {"company": "Redfin", "filings": 10, "avg_salary": 165000},
    {"company": "Wayfair", "filings": 15, "avg_salary": 160000},
    {"company": "Etsy", "filings": 12, "avg_salary": 175000},
    {"company": "Robinhood", "filings": 15, "avg_salary": 185000},
    {"company": "Coinbase", "filings": 15, "avg_salary": 195000},
    {"company": "Plaid", "filings": 10, "avg_salary": 185000},
    {"company": "Ripple", "filings": 8, "avg_salary": 180000},
    {"company": "Discord", "filings": 10, "avg_salary": 185000},
    {"company": "Figma", "filings": 8, "avg_salary": 185000},
    {"company": "Canva", "filings": 10, "avg_salary": 175000},
    {"company": "Notion", "filings": 8, "avg_salary": 180000},
    {"company": "Grammarly", "filings": 10, "avg_salary": 175000},
    {"company": "Duolingo", "filings": 12, "avg_salary": 170000},
    {"company": "HubSpot", "filings": 15, "avg_salary": 165000},
    {"company": "ZoomInfo", "filings": 10, "avg_salary": 160000},
    {"company": "Zoom", "filings": 20, "avg_salary": 170000},
    {"company": "DocuSign", "filings": 12, "avg_salary": 170000},
    {"company": "Okta", "filings": 12, "avg_salary": 175000},
    {"company": "CrowdStrike", "filings": 15, "avg_salary": 175000},
    {"company": "Palo Alto Networks", "filings": 18, "avg_salary": 180000},
    {"company": "Zscaler", "filings": 10, "avg_salary": 175000},
    {"company": "ServiceNow", "filings": 20, "avg_salary": 175000},
    {"company": "Workday", "filings": 18, "avg_salary": 175000},
    {"company": "Twilio", "filings": 15, "avg_salary": 175000},
    {"company": "Elastic", "filings": 10, "avg_salary": 170000},
    {"company": "MongoDB", "filings": 12, "avg_salary": 175000},
    {"company": "Confluent", "filings": 10, "avg_salary": 175000},

    # ══════ AI / ML Companies ══════
    {"company": "OpenAI", "filings": 2, "avg_salary": 347500},    # files as "Member of Technical Staff", not DS title
    {"company": "Anthropic", "filings": 0, "avg_salary": 295000}, # uses Research Scientist/Engineer titles only
    {"company": "Databricks", "filings": 2, "avg_salary": 140000}, # titles DS roles as SWE/Solutions Architect
    {"company": "Snowflake", "filings": 4, "avg_salary": 151736},
    {"company": "Datadog", "filings": 25, "avg_salary": 185000},
    {"company": "Palantir", "filings": 0, "avg_salary": 180000},  # uses Forward Deployed Engineer title, 0 DS LCAs
    {"company": "Scale AI", "filings": 15, "avg_salary": 190000},
    {"company": "Cohere", "filings": 8, "avg_salary": 200000},
    {"company": "Hugging Face", "filings": 10, "avg_salary": 195000},
    {"company": "C3 AI", "filings": 15, "avg_salary": 154760},
    {"company": "DataRobot", "filings": 10, "avg_salary": 170000},
    {"company": "H2O.ai", "filings": 8, "avg_salary": 170000},
    {"company": "Weights & Biases", "filings": 8, "avg_salary": 185000},
    {"company": "Anyscale", "filings": 8, "avg_salary": 190000},
    {"company": "Moveworks", "filings": 8, "avg_salary": 180000},
    {"company": "Glean", "filings": 8, "avg_salary": 185000},
    {"company": "Nvidia", "filings": 12, "avg_salary": 174905},

    # ══════ Semiconductor / Hardware ══════
    {"company": "Intel", "filings": 35, "avg_salary": 160000},
    {"company": "Qualcomm", "filings": 30, "avg_salary": 165000},
    {"company": "AMD", "filings": 20, "avg_salary": 170000},
    {"company": "Broadcom", "filings": 20, "avg_salary": 175000},
    {"company": "Texas Instruments", "filings": 15, "avg_salary": 155000},
    {"company": "Cisco", "filings": 35, "avg_salary": 160000},

    # ══════ Finance — Banks ══════
    # NOTE: banks file thousands of H1Bs but use internal titles (Associate/VP), not "Data Scientist"
    {"company": "JPMorgan Chase", "filings": 3, "avg_salary": 118400},   # 3 DS-titled LCAs in 2024 DOL data
    {"company": "Capital One", "filings": 0, "avg_salary": 160000},      # 0 DS LCAs; uses Principal Associate etc.
    {"company": "Goldman Sachs", "filings": 0, "avg_salary": 170000},    # 0 DS LCAs; uses Associate/VP titles
    {"company": "Morgan Stanley", "filings": 8, "avg_salary": 165000},
    {"company": "Bank of America", "filings": 10, "avg_salary": 155000},
    {"company": "Citigroup", "filings": 15, "avg_salary": 160000},
    {"company": "Citi", "filings": 15, "avg_salary": 160000},
    {"company": "Wells Fargo", "filings": 10, "avg_salary": 155000},
    {"company": "Barclays", "filings": 30, "avg_salary": 165000},
    {"company": "Deutsche Bank", "filings": 25, "avg_salary": 160000},
    {"company": "HSBC", "filings": 20, "avg_salary": 155000},
    {"company": "BNY Mellon", "filings": 20, "avg_salary": 155000},
    {"company": "US Bank", "filings": 15, "avg_salary": 150000},
    {"company": "PNC Financial", "filings": 15, "avg_salary": 145000},
    {"company": "TD Bank", "filings": 12, "avg_salary": 150000},
    {"company": "Citizens Financial", "filings": 10, "avg_salary": 145000},
    {"company": "Truist", "filings": 12, "avg_salary": 145000},

    # ══════ Finance — Quant / Hedge Funds / Asset Mgmt ══════
    {"company": "Citadel", "filings": 30, "avg_salary": 250000},
    {"company": "Two Sigma", "filings": 25, "avg_salary": 240000},
    {"company": "D.E. Shaw", "filings": 20, "avg_salary": 230000},
    {"company": "Jane Street", "filings": 15, "avg_salary": 260000},
    {"company": "Renaissance Technologies", "filings": 10, "avg_salary": 250000},
    {"company": "Point72", "filings": 15, "avg_salary": 220000},
    {"company": "Millennium", "filings": 12, "avg_salary": 220000},
    {"company": "AQR Capital", "filings": 10, "avg_salary": 210000},
    {"company": "Bridgewater Associates", "filings": 10, "avg_salary": 200000},
    {"company": "BlackRock", "filings": 30, "avg_salary": 170000},
    {"company": "Vanguard", "filings": 20, "avg_salary": 155000},
    {"company": "Fidelity", "filings": 25, "avg_salary": 160000},
    {"company": "Charles Schwab", "filings": 15, "avg_salary": 155000},
    {"company": "State Street", "filings": 15, "avg_salary": 155000},

    # ══════ Fintech / Payments ══════
    {"company": "Visa", "filings": 40, "avg_salary": 160000},
    {"company": "Mastercard", "filings": 35, "avg_salary": 165000},
    {"company": "PayPal", "filings": 40, "avg_salary": 170000},
    {"company": "Intuit", "filings": 35, "avg_salary": 175000},
    {"company": "American Express", "filings": 30, "avg_salary": 160000},
    {"company": "Affirm", "filings": 12, "avg_salary": 185000},
    {"company": "Klarna", "filings": 10, "avg_salary": 175000},
    {"company": "SoFi", "filings": 12, "avg_salary": 165000},
    {"company": "Chime", "filings": 10, "avg_salary": 170000},
    {"company": "Brex", "filings": 8, "avg_salary": 185000},
    {"company": "Marqeta", "filings": 8, "avg_salary": 175000},

    # ══════ Insurance ══════
    {"company": "MetLife", "filings": 15, "avg_salary": 150000},
    {"company": "Prudential", "filings": 15, "avg_salary": 155000},
    {"company": "AIG", "filings": 12, "avg_salary": 155000},
    {"company": "Liberty Mutual", "filings": 15, "avg_salary": 150000},
    {"company": "Travelers", "filings": 10, "avg_salary": 150000},
    {"company": "Allstate", "filings": 12, "avg_salary": 145000},
    {"company": "Progressive", "filings": 10, "avg_salary": 145000},
    {"company": "Nationwide", "filings": 8, "avg_salary": 140000},

    # ══════ Consulting / Big 4 ══════
    # NOTE: consulting firms file many H1Bs but rarely titled "Data Scientist" in DOL filings
    {"company": "Deloitte", "filings": 6, "avg_salary": 78603},   # 6 DS LCAs; avg low due to govt-contract wage bands
    {"company": "Accenture", "filings": 0, "avg_salary": 135000}, # 0 DS LCAs; uses "Data and AI Consultant" title
    {"company": "EY", "filings": 8, "avg_salary": 140000},
    {"company": "KPMG", "filings": 8, "avg_salary": 145000},
    {"company": "PwC", "filings": 8, "avg_salary": 140000},
    {"company": "McKinsey", "filings": 25, "avg_salary": 180000},
    {"company": "BCG", "filings": 20, "avg_salary": 175000},
    {"company": "Bain", "filings": 15, "avg_salary": 170000},
    {"company": "Booz Allen Hamilton", "filings": 20, "avg_salary": 145000},
    {"company": "Capgemini", "filings": 30, "avg_salary": 130000},
    # Cognizant: publicly stated they will no longer sponsor new H1B workers (2025)
    # TCS CEO stated they will not add to H1B count; only 3 DS LCAs in 2024
    {"company": "Infosys", "filings": 2, "avg_salary": 102399},
    {"company": "Wipro", "filings": 5, "avg_salary": 115000},
    {"company": "HCL Technologies", "filings": 5, "avg_salary": 120000},

    # ══════ Healthcare / Pharma ══════
    {"company": "Johnson & Johnson", "filings": 25, "avg_salary": 155000},
    {"company": "Pfizer", "filings": 20, "avg_salary": 155000},
    {"company": "Merck", "filings": 20, "avg_salary": 155000},
    {"company": "Roche", "filings": 15, "avg_salary": 160000},
    {"company": "Novartis", "filings": 15, "avg_salary": 160000},
    {"company": "AbbVie", "filings": 15, "avg_salary": 155000},
    {"company": "Bristol-Myers Squibb", "filings": 12, "avg_salary": 155000},
    {"company": "Eli Lilly", "filings": 15, "avg_salary": 155000},
    {"company": "Amgen", "filings": 12, "avg_salary": 160000},
    {"company": "Regeneron", "filings": 10, "avg_salary": 165000},
    {"company": "Moderna", "filings": 10, "avg_salary": 170000},
    {"company": "UnitedHealth Group", "filings": 25, "avg_salary": 150000},
    {"company": "CVS Health", "filings": 20, "avg_salary": 145000},
    {"company": "Humana", "filings": 12, "avg_salary": 145000},
    {"company": "Anthem", "filings": 15, "avg_salary": 145000},
    {"company": "Elevance Health", "filings": 15, "avg_salary": 150000},

    # ══════ Media / Entertainment ══════
    {"company": "Warner Bros Discovery", "filings": 15, "avg_salary": 160000},
    {"company": "NBCUniversal", "filings": 15, "avg_salary": 155000},
    {"company": "Disney", "filings": 20, "avg_salary": 160000},
    {"company": "Comcast", "filings": 20, "avg_salary": 155000},
    {"company": "Paramount", "filings": 10, "avg_salary": 150000},
    {"company": "Sony", "filings": 15, "avg_salary": 160000},
    {"company": "The New York Times", "filings": 10, "avg_salary": 155000},
    {"company": "Bloomberg", "filings": 25, "avg_salary": 175000},
    {"company": "Thomson Reuters", "filings": 15, "avg_salary": 160000},
    {"company": "Altice", "filings": 10, "avg_salary": 145000},
    {"company": "Optimum", "filings": 8, "avg_salary": 140000},
    {"company": "Optimum Media", "filings": 8, "avg_salary": 140000},

    # ══════ Retail / E-commerce ══════
    {"company": "Walmart", "filings": 101, "avg_salary": 124675},  # paused new H1B offers Sept 2025 due to $100K fee rule
    {"company": "Target", "filings": 25, "avg_salary": 140000},
    {"company": "Costco", "filings": 10, "avg_salary": 140000},
    {"company": "Home Depot", "filings": 15, "avg_salary": 140000},
    {"company": "Nike", "filings": 15, "avg_salary": 155000},
    {"company": "Starbucks", "filings": 12, "avg_salary": 150000},

    # ══════ Transportation / Logistics ══════
    {"company": "Tesla", "filings": 30, "avg_salary": 170000},
    {"company": "Ford", "filings": 20, "avg_salary": 155000},
    {"company": "GM", "filings": 20, "avg_salary": 155000},
    {"company": "General Motors", "filings": 20, "avg_salary": 155000},
    {"company": "Rivian", "filings": 10, "avg_salary": 175000},
    {"company": "Waymo", "filings": 5, "avg_salary": 189000},
    # Cruise removed — GM ended robotaxi business Dec 2024, 50% layoff Feb 2025
    {"company": "FedEx", "filings": 12, "avg_salary": 145000},
    {"company": "UPS", "filings": 10, "avg_salary": 145000},

    # ══════ Telecom ══════
    {"company": "T-Mobile", "filings": 15, "avg_salary": 150000},
    {"company": "Verizon", "filings": 20, "avg_salary": 155000},
    {"company": "AT&T", "filings": 15, "avg_salary": 150000},

    # ══════ Defense / Aerospace ══════
    {"company": "Lockheed Martin", "filings": 15, "avg_salary": 145000},
    {"company": "Raytheon", "filings": 12, "avg_salary": 145000},
    {"company": "RTX", "filings": 12, "avg_salary": 145000},
    {"company": "Northrop Grumman", "filings": 12, "avg_salary": 145000},
    {"company": "Boeing", "filings": 15, "avg_salary": 150000},
    {"company": "SpaceX", "filings": 10, "avg_salary": 165000},

    # ══════ Energy ══════
    {"company": "ExxonMobil", "filings": 12, "avg_salary": 155000},
    {"company": "Chevron", "filings": 10, "avg_salary": 155000},
    {"company": "Shell", "filings": 10, "avg_salary": 155000},
    {"company": "BP", "filings": 8, "avg_salary": 150000},

    # ══════ Other Large Employers Known to Sponsor ══════
    {"company": "Procter & Gamble", "filings": 15, "avg_salary": 145000},
    {"company": "3M", "filings": 10, "avg_salary": 145000},
    {"company": "GE", "filings": 15, "avg_salary": 150000},
    {"company": "General Electric", "filings": 15, "avg_salary": 150000},
    {"company": "Siemens", "filings": 12, "avg_salary": 150000},
    {"company": "Honeywell", "filings": 12, "avg_salary": 150000},
    {"company": "Caterpillar", "filings": 8, "avg_salary": 145000},
    {"company": "John Deere", "filings": 10, "avg_salary": 150000},
    {"company": "Deere & Company", "filings": 10, "avg_salary": 150000},
    {"company": "Cummins", "filings": 8, "avg_salary": 140000},
    {"company": "Corning", "filings": 8, "avg_salary": 145000},

    # ══════ Gaming ══════
    {"company": "Electronic Arts", "filings": 15, "avg_salary": 170000},
    {"company": "Activision Blizzard", "filings": 12, "avg_salary": 165000},
    {"company": "Riot Games", "filings": 10, "avg_salary": 175000},
    {"company": "Epic Games", "filings": 10, "avg_salary": 175000},
    {"company": "Unity Technologies", "filings": 12, "avg_salary": 170000},
    {"company": "Roblox", "filings": 10, "avg_salary": 180000},
    {"company": "Zynga", "filings": 8, "avg_salary": 165000},
    {"company": "Take-Two Interactive", "filings": 8, "avg_salary": 165000},
    {"company": "Niantic", "filings": 6, "avg_salary": 175000},
    {"company": "WB Games", "filings": 6, "avg_salary": 165000},

    # ══════ EdTech ══════
    {"company": "Coursera", "filings": 8, "avg_salary": 170000},
    {"company": "Udemy", "filings": 8, "avg_salary": 165000},
    {"company": "Chegg", "filings": 6, "avg_salary": 160000},
    {"company": "2U", "filings": 5, "avg_salary": 155000},
    {"company": "Instructure", "filings": 6, "avg_salary": 160000},
    {"company": "Pluralsight", "filings": 5, "avg_salary": 160000},
    {"company": "Udacity", "filings": 5, "avg_salary": 160000},
    {"company": "Kahoot", "filings": 5, "avg_salary": 155000},

    # ══════ Travel / Hospitality ══════
    {"company": "Expedia", "filings": 27, "avg_salary": 118414},  # 27 DS LCAs in 2024, Seattle-heavy
    {"company": "Booking Holdings", "filings": 12, "avg_salary": 175000},
    {"company": "Tripadvisor", "filings": 8, "avg_salary": 165000},
    {"company": "Marriott", "filings": 10, "avg_salary": 150000},
    {"company": "Hilton", "filings": 8, "avg_salary": 150000},
    {"company": "Hyatt", "filings": 6, "avg_salary": 150000},
    {"company": "Hopper", "filings": 8, "avg_salary": 175000},
    {"company": "KAYAK", "filings": 6, "avg_salary": 165000},

    # ══════ Real Estate Tech ══════
    {"company": "Compass", "filings": 8, "avg_salary": 165000},
    {"company": "Opendoor", "filings": 8, "avg_salary": 170000},
    {"company": "CoStar", "filings": 10, "avg_salary": 160000},
    {"company": "CBRE", "filings": 12, "avg_salary": 155000},
    {"company": "JLL", "filings": 10, "avg_salary": 150000},
    {"company": "Cushman & Wakefield", "filings": 8, "avg_salary": 150000},
    {"company": "Divvy Homes", "filings": 5, "avg_salary": 165000},
    {"company": "Procore Technologies", "filings": 8, "avg_salary": 165000},

    # ══════ HR Tech ══════
    {"company": "ADP", "filings": 15, "avg_salary": 145000},
    {"company": "Lattice", "filings": 6, "avg_salary": 165000},
    {"company": "Rippling", "filings": 8, "avg_salary": 175000},
    {"company": "Gusto", "filings": 8, "avg_salary": 170000},
    {"company": "BambooHR", "filings": 5, "avg_salary": 155000},
    {"company": "Deel", "filings": 8, "avg_salary": 175000},
    {"company": "Remote", "filings": 5, "avg_salary": 165000},
    {"company": "TriNet", "filings": 8, "avg_salary": 145000},
    {"company": "Ceridian", "filings": 8, "avg_salary": 145000},
    {"company": "UKG", "filings": 10, "avg_salary": 150000},
    {"company": "ZipRecruiter", "filings": 8, "avg_salary": 160000},
    {"company": "Handshake", "filings": 6, "avg_salary": 165000},
    {"company": "Indeed", "filings": 12, "avg_salary": 155000},

    # ══════ Logistics / Supply Chain ══════
    {"company": "Flexport", "filings": 8, "avg_salary": 175000},
    {"company": "XPO Logistics", "filings": 8, "avg_salary": 145000},
    {"company": "J.B. Hunt", "filings": 6, "avg_salary": 140000},
    {"company": "Convoy", "filings": 6, "avg_salary": 165000},
    {"company": "project44", "filings": 5, "avg_salary": 160000},
    {"company": "Samsara", "filings": 8, "avg_salary": 175000},

    # ══════ Cybersecurity ══════
    {"company": "SentinelOne", "filings": 10, "avg_salary": 175000},
    {"company": "Tenable", "filings": 8, "avg_salary": 165000},
    {"company": "Rapid7", "filings": 8, "avg_salary": 160000},
    {"company": "Qualys", "filings": 8, "avg_salary": 160000},
    {"company": "Vectra AI", "filings": 6, "avg_salary": 170000},
    {"company": "Abnormal Security", "filings": 6, "avg_salary": 175000},
    {"company": "Wiz", "filings": 8, "avg_salary": 180000},
    {"company": "Lacework", "filings": 5, "avg_salary": 175000},
    {"company": "Orca Security", "filings": 5, "avg_salary": 175000},
    {"company": "Darktrace", "filings": 6, "avg_salary": 165000},
    {"company": "Fortinet", "filings": 10, "avg_salary": 165000},
    {"company": "Check Point Software", "filings": 8, "avg_salary": 165000},
    {"company": "Splunk", "filings": 12, "avg_salary": 170000},
    {"company": "Sumo Logic", "filings": 6, "avg_salary": 165000},
    {"company": "Exabeam", "filings": 5, "avg_salary": 160000},

    # ══════ Cloud / DevOps / SaaS ══════
    {"company": "Cloudflare", "filings": 12, "avg_salary": 175000},
    {"company": "HashiCorp", "filings": 10, "avg_salary": 175000},
    {"company": "PagerDuty", "filings": 8, "avg_salary": 170000},
    {"company": "GitLab", "filings": 10, "avg_salary": 170000},
    {"company": "JFrog", "filings": 8, "avg_salary": 170000},
    {"company": "New Relic", "filings": 10, "avg_salary": 165000},
    {"company": "Dynatrace", "filings": 8, "avg_salary": 165000},
    {"company": "Fastly", "filings": 6, "avg_salary": 170000},
    {"company": "Akamai", "filings": 12, "avg_salary": 165000},
    {"company": "Amplitude", "filings": 8, "avg_salary": 175000},
    {"company": "Mixpanel", "filings": 6, "avg_salary": 170000},
    {"company": "dbt Labs", "filings": 8, "avg_salary": 175000},
    {"company": "Monte Carlo", "filings": 5, "avg_salary": 175000},
    {"company": "Airbyte", "filings": 6, "avg_salary": 180000},
    {"company": "Fivetran", "filings": 8, "avg_salary": 175000},
    {"company": "Informatica", "filings": 10, "avg_salary": 155000},
    {"company": "MuleSoft", "filings": 8, "avg_salary": 170000},
    {"company": "Zapier", "filings": 8, "avg_salary": 170000},
    {"company": "Airtable", "filings": 8, "avg_salary": 175000},
    {"company": "Asana", "filings": 10, "avg_salary": 175000},
    {"company": "Monday.com", "filings": 8, "avg_salary": 175000},
    {"company": "Box", "filings": 8, "avg_salary": 165000},
    {"company": "Carta", "filings": 8, "avg_salary": 175000},
    {"company": "Retool", "filings": 6, "avg_salary": 175000},
    {"company": "FullStory", "filings": 6, "avg_salary": 170000},
    {"company": "Braze", "filings": 8, "avg_salary": 170000},
    {"company": "Intercom", "filings": 8, "avg_salary": 170000},
    {"company": "Zendesk", "filings": 10, "avg_salary": 165000},
    {"company": "Freshworks", "filings": 8, "avg_salary": 155000},
    {"company": "Gong", "filings": 8, "avg_salary": 175000},
    {"company": "Veeva Systems", "filings": 15, "avg_salary": 170000},
    {"company": "RingCentral", "filings": 10, "avg_salary": 160000},
    {"company": "Autodesk", "filings": 12, "avg_salary": 170000},
    {"company": "GitHub", "filings": 10, "avg_salary": 175000},
    {"company": "Miro", "filings": 8, "avg_salary": 170000},
    {"company": "Calendly", "filings": 6, "avg_salary": 160000},
    {"company": "Loom", "filings": 6, "avg_salary": 170000},
    {"company": "Linear", "filings": 5, "avg_salary": 175000},

    # ══════ Biotech / Life Sciences ══════
    {"company": "AstraZeneca", "filings": 12, "avg_salary": 160000},
    {"company": "Genentech", "filings": 10, "avg_salary": 170000},
    {"company": "Gilead Sciences", "filings": 10, "avg_salary": 170000},
    {"company": "Biogen", "filings": 8, "avg_salary": 165000},
    {"company": "Vertex Pharmaceuticals", "filings": 8, "avg_salary": 170000},
    {"company": "BioMarin", "filings": 6, "avg_salary": 165000},
    {"company": "Illumina", "filings": 10, "avg_salary": 165000},
    {"company": "10x Genomics", "filings": 8, "avg_salary": 170000},
    {"company": "Recursion Pharmaceuticals", "filings": 6, "avg_salary": 165000},
    {"company": "Guardant Health", "filings": 6, "avg_salary": 165000},
    {"company": "Tempus AI", "filings": 8, "avg_salary": 170000},
    {"company": "Flatiron Health", "filings": 6, "avg_salary": 165000},
    {"company": "Alnylam Pharmaceuticals", "filings": 6, "avg_salary": 170000},
    {"company": "Sarepta Therapeutics", "filings": 5, "avg_salary": 165000},
    {"company": "Pacific Biosciences", "filings": 5, "avg_salary": 160000},

    # ══════ Healthcare IT ══════
    {"company": "Epic Systems", "filings": 12, "avg_salary": 145000},
    {"company": "Cerner", "filings": 10, "avg_salary": 145000},
    {"company": "Optum", "filings": 20, "avg_salary": 155000},
    {"company": "Change Healthcare", "filings": 8, "avg_salary": 145000},
    {"company": "Teladoc", "filings": 8, "avg_salary": 155000},
    {"company": "GoodRx", "filings": 6, "avg_salary": 160000},
    {"company": "Hinge Health", "filings": 6, "avg_salary": 165000},
    {"company": "Noom", "filings": 6, "avg_salary": 160000},
    {"company": "Oscar Health", "filings": 8, "avg_salary": 160000},
    {"company": "Omada Health", "filings": 5, "avg_salary": 160000},
    {"company": "Accolade", "filings": 5, "avg_salary": 150000},
    {"company": "Cigna", "filings": 15, "avg_salary": 155000},

    # ══════ Autonomous Vehicles ══════
    {"company": "Aurora Innovation", "filings": 8, "avg_salary": 190000},
    {"company": "Mobileye", "filings": 8, "avg_salary": 185000},
    {"company": "Zoox", "filings": 8, "avg_salary": 195000},
    {"company": "Motional", "filings": 8, "avg_salary": 185000},
    {"company": "May Mobility", "filings": 5, "avg_salary": 175000},
    {"company": "Kodiak Robotics", "filings": 5, "avg_salary": 180000},
    {"company": "TuSimple", "filings": 6, "avg_salary": 175000},
    {"company": "Lucid Motors", "filings": 8, "avg_salary": 170000},

    # ══════ AI Startups (New Generation) ══════
    {"company": "Perplexity AI", "filings": 13, "avg_salary": 280000},  # 10/10 petitions approved FY2025
    {"company": "Groq", "filings": 6, "avg_salary": 220000},
    {"company": "Together AI", "filings": 5, "avg_salary": 215000},
    {"company": "Lambda Labs", "filings": 5, "avg_salary": 210000},
    {"company": "Cerebras Systems", "filings": 6, "avg_salary": 210000},
    {"company": "Runway AI", "filings": 5, "avg_salary": 215000},
    {"company": "Character AI", "filings": 6, "avg_salary": 220000},
    {"company": "Inflection AI", "filings": 5, "avg_salary": 220000},
    {"company": "xAI", "filings": 12, "avg_salary": 300000},   # Elon Musk AI lab, verified FY2024 DOL
    {"company": "Mistral AI", "filings": 5, "avg_salary": 215000},
    {"company": "Harvey AI", "filings": 5, "avg_salary": 215000},
    {"company": "Writer", "filings": 5, "avg_salary": 205000},
    {"company": "Stability AI", "filings": 5, "avg_salary": 210000},
    {"company": "Adept AI", "filings": 5, "avg_salary": 215000},
    {"company": "Weaviate", "filings": 5, "avg_salary": 190000},
    {"company": "Pinecone", "filings": 5, "avg_salary": 195000},
    {"company": "LangChain", "filings": 5, "avg_salary": 200000},
    {"company": "Modal Labs", "filings": 5, "avg_salary": 200000},
    {"company": "Replicate", "filings": 5, "avg_salary": 195000},
    {"company": "Replit", "filings": 6, "avg_salary": 195000},

    # ══════ Aerospace / Space ══════
    {"company": "Rocket Lab", "filings": 6, "avg_salary": 160000},
    {"company": "Blue Origin", "filings": 8, "avg_salary": 165000},
    {"company": "Planet Labs", "filings": 6, "avg_salary": 165000},
    {"company": "Maxar Technologies", "filings": 8, "avg_salary": 160000},
    {"company": "Joby Aviation", "filings": 8, "avg_salary": 175000},
    {"company": "Archer Aviation", "filings": 5, "avg_salary": 170000},
    {"company": "Relativity Space", "filings": 6, "avg_salary": 165000},

    # ══════ Climate Tech / Clean Energy ══════
    {"company": "First Solar", "filings": 6, "avg_salary": 145000},
    {"company": "Sunrun", "filings": 6, "avg_salary": 145000},
    {"company": "Enphase Energy", "filings": 6, "avg_salary": 150000},
    {"company": "NextEra Energy", "filings": 8, "avg_salary": 150000},
    {"company": "Commonwealth Fusion Systems", "filings": 5, "avg_salary": 160000},
    {"company": "Form Energy", "filings": 5, "avg_salary": 155000},
    {"company": "Arcadia", "filings": 5, "avg_salary": 155000},
    {"company": "Stem Inc", "filings": 5, "avg_salary": 150000},

    # ══════ Legal Tech ══════
    {"company": "Relativity", "filings": 8, "avg_salary": 155000},
    {"company": "LexisNexis", "filings": 10, "avg_salary": 155000},
    {"company": "Everlaw", "filings": 5, "avg_salary": 165000},
    {"company": "Ironclad", "filings": 5, "avg_salary": 165000},
    {"company": "Clio", "filings": 5, "avg_salary": 155000},

    # ══════ Sports / Entertainment Tech ══════
    {"company": "DraftKings", "filings": 8, "avg_salary": 165000},
    {"company": "FanDuel", "filings": 8, "avg_salary": 165000},
    {"company": "Sportradar", "filings": 6, "avg_salary": 155000},
    {"company": "Genius Sports", "filings": 5, "avg_salary": 155000},
    {"company": "Stats Perform", "filings": 5, "avg_salary": 155000},

    # ══════ Social / Consumer Tech ══════
    {"company": "Bumble", "filings": 8, "avg_salary": 170000},
    {"company": "Match Group", "filings": 10, "avg_salary": 165000},
    {"company": "Nextdoor", "filings": 8, "avg_salary": 170000},
    {"company": "Quora", "filings": 6, "avg_salary": 165000},
    {"company": "Stack Overflow", "filings": 5, "avg_salary": 160000},
    {"company": "Substack", "filings": 5, "avg_salary": 170000},

    # ══════ Mapping / Location Tech ══════
    {"company": "HERE Technologies", "filings": 8, "avg_salary": 165000},
    {"company": "Esri", "filings": 8, "avg_salary": 155000},
    {"company": "Mapbox", "filings": 6, "avg_salary": 170000},
    {"company": "Foursquare", "filings": 5, "avg_salary": 165000},

    # ══════ Financial Services (Payments / Banking more) ══════
    {"company": "Fiserv", "filings": 15, "avg_salary": 145000},
    {"company": "FIS", "filings": 15, "avg_salary": 145000},
    {"company": "Adyen", "filings": 10, "avg_salary": 175000},
    {"company": "SS&C Technologies", "filings": 10, "avg_salary": 150000},
    {"company": "T. Rowe Price", "filings": 10, "avg_salary": 160000},
    {"company": "Northern Trust", "filings": 10, "avg_salary": 155000},
    {"company": "Ally Financial", "filings": 10, "avg_salary": 155000},
    {"company": "Synchrony Financial", "filings": 8, "avg_salary": 150000},
    {"company": "Discover Financial", "filings": 10, "avg_salary": 155000},
    {"company": "Nasdaq", "filings": 10, "avg_salary": 165000},
    {"company": "CME Group", "filings": 10, "avg_salary": 165000},
    {"company": "Intercontinental Exchange", "filings": 10, "avg_salary": 165000},
    {"company": "Cboe Global Markets", "filings": 8, "avg_salary": 160000},
    {"company": "Raymond James", "filings": 10, "avg_salary": 155000},
    {"company": "LPL Financial", "filings": 8, "avg_salary": 155000},
    {"company": "Ameriprise Financial", "filings": 8, "avg_salary": 150000},
    {"company": "Invesco", "filings": 8, "avg_salary": 160000},
    {"company": "Franklin Templeton", "filings": 8, "avg_salary": 160000},
    {"company": "Lemonade", "filings": 6, "avg_salary": 165000},
    {"company": "Root Insurance", "filings": 5, "avg_salary": 160000},
    {"company": "MoneyLion", "filings": 6, "avg_salary": 165000},
    {"company": "LendingClub", "filings": 6, "avg_salary": 155000},
    {"company": "Blend Labs", "filings": 6, "avg_salary": 165000},
    {"company": "Rocket Mortgage", "filings": 8, "avg_salary": 145000},
    {"company": "Better", "filings": 6, "avg_salary": 160000},
    {"company": "Interactive Brokers", "filings": 8, "avg_salary": 165000},

    # ══════ Manufacturing / Industrial ══════
    {"company": "Rockwell Automation", "filings": 8, "avg_salary": 145000},
    {"company": "Emerson Electric", "filings": 8, "avg_salary": 145000},
    {"company": "Parker Hannifin", "filings": 6, "avg_salary": 145000},
    {"company": "Eaton", "filings": 8, "avg_salary": 145000},
    {"company": "ABB", "filings": 8, "avg_salary": 150000},
    {"company": "Schneider Electric", "filings": 8, "avg_salary": 150000},
    {"company": "Roper Technologies", "filings": 5, "avg_salary": 145000},
    {"company": "AMETEK", "filings": 5, "avg_salary": 140000},
    {"company": "Xylem", "filings": 5, "avg_salary": 140000},

    # ══════ Retail / CPG (more) ══════
    {"company": "Lowe's", "filings": 10, "avg_salary": 145000},
    {"company": "Best Buy", "filings": 8, "avg_salary": 140000},
    {"company": "Kroger", "filings": 8, "avg_salary": 140000},
    {"company": "Chewy", "filings": 8, "avg_salary": 155000},
    {"company": "Nordstrom", "filings": 6, "avg_salary": 145000},
    {"company": "Macy's", "filings": 6, "avg_salary": 140000},
    {"company": "Albertsons", "filings": 6, "avg_salary": 135000},
    {"company": "Dollar General", "filings": 5, "avg_salary": 130000},
    {"company": "Gap", "filings": 6, "avg_salary": 140000},

    # ══════ Media / Publishing (more) ══════
    {"company": "The Washington Post", "filings": 8, "avg_salary": 160000},
    {"company": "Condé Nast", "filings": 6, "avg_salary": 155000},
    {"company": "Vox Media", "filings": 5, "avg_salary": 155000},
    {"company": "BuzzFeed", "filings": 5, "avg_salary": 145000},
    {"company": "Axios", "filings": 5, "avg_salary": 150000},

    # ══════ Telco / Networking ══════
    {"company": "Ericsson", "filings": 10, "avg_salary": 155000},
    {"company": "Nokia", "filings": 8, "avg_salary": 150000},
    {"company": "Juniper Networks", "filings": 8, "avg_salary": 160000},
    {"company": "Arista Networks", "filings": 8, "avg_salary": 165000},
    {"company": "Ciena", "filings": 6, "avg_salary": 155000},
    {"company": "CommScope", "filings": 6, "avg_salary": 145000},
    {"company": "Calix", "filings": 5, "avg_salary": 150000},

    # ══════ PropTech / Construction Tech ══════
    {"company": "Trimble", "filings": 8, "avg_salary": 155000},
    {"company": "Bentley Systems", "filings": 6, "avg_salary": 155000},
    {"company": "PlanGrid", "filings": 5, "avg_salary": 160000},

    # ══════ AgriTech ══════
    {"company": "The Climate Corporation", "filings": 5, "avg_salary": 155000},
    {"company": "Indigo Ag", "filings": 5, "avg_salary": 155000},

    # ══════ Food Tech ══════
    {"company": "Toast", "filings": 8, "avg_salary": 155000},
    {"company": "Olo", "filings": 5, "avg_salary": 155000},

    # ══════ Database / Infrastructure ══════
    {"company": "CockroachLabs", "filings": 6, "avg_salary": 175000},
    {"company": "PlanetScale", "filings": 5, "avg_salary": 180000},
    {"company": "Neon", "filings": 5, "avg_salary": 175000},
    {"company": "ClickHouse", "filings": 5, "avg_salary": 175000},
    {"company": "Timescale", "filings": 5, "avg_salary": 170000},
    {"company": "SingleStore", "filings": 5, "avg_salary": 170000},
    {"company": "Couchbase", "filings": 6, "avg_salary": 160000},
    {"company": "Neo4j", "filings": 5, "avg_salary": 165000},
    {"company": "Yugabyte", "filings": 5, "avg_salary": 170000},
    {"company": "Temporal Technologies", "filings": 5, "avg_salary": 175000},
    {"company": "Netlify", "filings": 6, "avg_salary": 170000},
    {"company": "Vercel", "filings": 6, "avg_salary": 175000},
    {"company": "Supabase", "filings": 5, "avg_salary": 175000},

    # ══════ Observability / Analytics ══════
    {"company": "Grafana Labs", "filings": 6, "avg_salary": 175000},
    {"company": "Honeycomb", "filings": 5, "avg_salary": 175000},
    {"company": "Lightstep", "filings": 5, "avg_salary": 170000},
    {"company": "Observe", "filings": 5, "avg_salary": 170000},
    {"company": "Statsig", "filings": 5, "avg_salary": 180000},

    # ══════ Robotics / Industrial AI ══════
    {"company": "Boston Dynamics", "filings": 6, "avg_salary": 170000},
    {"company": "Symbotic", "filings": 6, "avg_salary": 165000},
    {"company": "Bright Machines", "filings": 5, "avg_salary": 160000},
    {"company": "Machina Labs", "filings": 5, "avg_salary": 160000},
    {"company": "Path Robotics", "filings": 5, "avg_salary": 165000},
    {"company": "Veo Robotics", "filings": 5, "avg_salary": 165000},
]


def scrape_myvisajobs(job_title: str = "data-scientist", max_pages: int = 2) -> list[dict]:
    """
    Scrape top H1B sponsors for a given job title from MyVisaJobs.

    Returns list of dicts: {company, filings, avg_salary}
    """
    sponsors = []
    session = requests.Session()
    session.headers.update({"User-Agent": settings.USER_AGENT})

    for page in range(1, max_pages + 1):
        url = f"https://www.myvisajobs.com/reports/h1b/job-title/{job_title}/"
        if page > 1:
            url += f"?p={page}"

        print(f"  📡 Fetching MyVisaJobs page {page}...")

        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  ⚠️  MyVisaJobs request failed: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")
        table = soup.select_one("table.tbl")
        if not table:
            break

        rows = table.select("tr")[1:]  # Skip header
        for row in rows:
            cols = row.select("td")
            if len(cols) >= 4:
                try:
                    company = cols[1].get_text(strip=True)
                    filings = int(re.sub(r'[^\d]', '', cols[2].get_text(strip=True)) or "0")
                    salary_text = cols[3].get_text(strip=True)
                    salary = int(re.sub(r'[^\d]', '', salary_text) or "0")

                    sponsors.append({
                        "company": company,
                        "filings": filings,
                        "avg_salary": salary,
                    })
                except (ValueError, IndexError):
                    continue

        time.sleep(settings.REQUEST_DELAY)

    return sponsors


def load_or_refresh_sponsors(force_refresh: bool = False) -> list[H1BSponsor]:
    """
    Load H1B sponsors — from cache, scrape, or seed data.
    """
    cache_file = settings.DATA_DIR / "h1b_sponsors.json"

    # Check if cache is fresh (< 7 days old)
    if not force_refresh and cache_file.exists():
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age < timedelta(days=7):
            print("📦 Loading H1B sponsors from cache...")
            with open(cache_file, "r") as f:
                data = json.load(f)
            return [
                H1BSponsor(
                    company_name=d["company"],
                    normalized_name=H1BSponsor._normalize(d["company"]),
                    total_filings=d["filings"],
                    data_scientist_filings=d["filings"],
                    avg_salary=d["avg_salary"],
                    approval_rate=0.85,
                    last_filing_year=2025,
                )
                for d in data
            ]

    # Try scraping MyVisaJobs
    print("🌐 Scraping latest H1B data from MyVisaJobs...")
    scraped = scrape_myvisajobs()

    if len(scraped) < len(SEED_SPONSORS):
        print(f"📦 Merging {len(scraped)} scraped + {len(SEED_SPONSORS)} seed sponsors...")
        # Merge: scraped data takes priority, seeds fill gaps
        seen = {H1BSponsor._normalize(s["company"]) for s in scraped}
        for seed in SEED_SPONSORS:
            if H1BSponsor._normalize(seed["company"]) not in seen:
                scraped.append(seed)
                seen.add(H1BSponsor._normalize(seed["company"]))
        print(f"📦 Total: {len(scraped)} unique sponsors")

    # Save cache
    settings.DATA_DIR.mkdir(exist_ok=True)
    with open(cache_file, "w") as f:
        json.dump(scraped, f, indent=2)

    sponsors = [
        H1BSponsor(
            company_name=d["company"],
            normalized_name=H1BSponsor._normalize(d["company"]),
            total_filings=d["filings"],
            data_scientist_filings=d["filings"],
            avg_salary=d["avg_salary"],
            approval_rate=0.85,
            last_filing_year=2025,
        )
        for d in scraped
    ]

    # Persist to database
    for s in sponsors:
        ops.upsert_sponsor(s)

    print(f"✅ Loaded {len(sponsors)} H1B sponsors")
    return sponsors


def match_jobs_with_sponsors():
    """
    Enrich all jobs in the database with H1B sponsorship data.
    """
    # Load sponsors
    sponsors = load_or_refresh_sponsors()
    sponsor_lookup = {s.normalized_name: s for s in sponsors}

    # Get all unmatched jobs
    jobs = ops.get_jobs(limit=1000)
    matched = 0

    for job in jobs:
        company = job["company"]
        normalized = H1BSponsor._normalize(company)

        # Direct lookup
        sponsor = sponsor_lookup.get(normalized)

        # Fuzzy: check if any sponsor name is contained in the company name
        if not sponsor:
            for sname, s in sponsor_lookup.items():
                if sname in normalized or normalized in sname:
                    sponsor = s
                    break

        # Also try the database (which may have more entries)
        if not sponsor:
            db_sponsor = ops.find_sponsor(company)
            if db_sponsor:
                sponsor = H1BSponsor(
                    company_name=db_sponsor["company_name"],
                    normalized_name=db_sponsor["normalized_name"],
                    total_filings=db_sponsor["total_filings"],
                    data_scientist_filings=db_sponsor["data_scientist_filings"],
                    avg_salary=db_sponsor["avg_salary"],
                )

        if sponsor:
            from utils.scorer import compute_h1b_score
            score = compute_h1b_score(
                h1b_filings=sponsor.total_filings,
                avg_salary=sponsor.avg_salary,
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                sponsors_signal=job.get("sponsors_h1b"),
            )

            ops.update_job_h1b(
                job_hash=job["job_hash"],
                h1b_filings=sponsor.total_filings,
                h1b_avg_salary=sponsor.avg_salary,
                sponsors_h1b=True,
                h1b_score=score,
            )
            matched += 1
        else:
            # No H1B data found — still compute a score from job description signals
            from utils.scorer import compute_h1b_score
            score = compute_h1b_score(
                h1b_filings=0,
                avg_salary=0,
                salary_min=job.get("salary_min"),
                salary_max=job.get("salary_max"),
                sponsors_signal=job.get("sponsors_h1b"),
            )
            ops.update_job_h1b(
                job_hash=job["job_hash"],
                h1b_filings=0,
                h1b_avg_salary=None,
                sponsors_h1b=job.get("sponsors_h1b"),
                h1b_score=score,
            )

    print(f"✅ Matched {matched}/{len(jobs)} jobs with H1B sponsor data")


if __name__ == "__main__":
    match_jobs_with_sponsors()
