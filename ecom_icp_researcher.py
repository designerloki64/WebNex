#!/usr/bin/env python3
"""Free public-source ecommerce ICP research helper.

It does not access Apollo, LinkedIn pages, login-gated sources, CAPTCHAs, paywalls,
or anti-bot controls. It searches public web results and crawls company-owned pages
only when robots.txt permits it.

Important: search snippets are clues, not proof. Email syntax/MX checks do not prove
a mailbox exists. The final export requires explicit evidence/review fields.
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import dns.resolver
import phonenumbers
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

ROOT = Path(".")
AGENT = "WebNexEcomResearch/1.0 (public business research; contact: site owner)"
HEADERS = {"User-Agent": AGENT, "Accept": "text/html,application/xhtml+xml"}
TIMEOUT = 10
DELAY = 1.0
NICHES = [
    "beauty brand", "skincare brand", "haircare brand", "apparel brand",
    "footwear brand", "jewelry brand", "home decor brand", "furniture brand",
    "pet products brand", "outdoor gear brand", "sports nutrition brand",
    "consumer electronics brand", "food beverage brand", "baby products brand",
    "wellness brand", "kitchenware brand", "supplements brand", "luggage brand",
    "accessories brand", "cleaning products brand", "mattress brand",
    "personal care brand", "toys brand", "hobby products brand",
]
EXCLUDE_DOMAINS = {
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "yelp.com",
    "yellowpages.com", "facebook.com", "instagram.com", "linkedin.com",
    "tiktok.com", "youtube.com", "pinterest.com", "x.com", "twitter.com",
    "reddit.com", "wikipedia.org", "amazon.com", "amazon.ca", "ebay.com",
    "walmart.com", "etsy.com", "shopify.com", "myshopify.com",
    "crunchbase.com", "zoominfo.com", "apollo.io", "hunter.io",
    "facebook.net", "googleusercontent.com", "medium.com", "forbes.com",
    "businesswire.com", "prnewswire.com", "globenewswire.com",
    "adstransparency.google.com",
}
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[\s().-]?)?(?:\(\s*\d{3}\s*\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?:x|ext\.?)\s*\d{1,6})?(?!\w)")
ROLE_TERMS = (
    "founder", "co-founder", "chief executive", " ceo", "owner", "president",
    "chief marketing", " cmo", "vp marketing", "vice president of marketing",
    "head of marketing", "head of ecommerce", "e-commerce director",
    "ecommerce director", "chief growth", "chief digital",
)
YES = {"yes", "y", "true", "1", "confirmed"}

COMPANY_FIELDS = [
    "company_name", "website", "country_guess", "discovery_query",
    "discovery_source_url", "discovered_at",
]
CONTACT_FIELDS = [
    "company_name", "website", "page_url", "public_email",
    "email_domain_mx", "email_status", "public_phone", "phone_status",
    "person_role_snippets", "linkedin_company_url", "collected_at",
]
RESEARCH_FIELDS = [
    "company_name", "website", "country_guess", "discovery_source_url",
    "public_email_candidates", "email_source_url", "email_domain_mx",
    "public_phone_candidates", "phone_source_url", "phone_status",
    "decision_maker_name", "decision_maker_title", "decision_maker_linkedin_url",
    "decision_maker_search_source_url", "decision_maker_search_snippet",
    "employee_count", "employees_51_plus_confirmed", "employee_evidence_url",
    "employee_evidence_snippet", "active_ads_confirmed", "ad_platform",
    "ad_evidence_url", "ad_last_seen_date", "confirmed_country",
    "decision_maker_email", "email_verification_status", "phone_live_verified",
    "decision_maker_phone", "decision_maker_source_url", "review_status",
]
MANUAL_FIELDS = RESEARCH_FIELDS[15:]


def unique(values):
    result, seen = [], set()
    for value in values:
        value = re.sub(r"\s+", " ", str(value or "")).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def root_domain(url: str) -> str:
    try:
        host = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower().strip(".")
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return ""
    # Common ccTLDs in ecommerce search results, plus ordinary .com/.ca domains.
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in {
        "co.uk", "org.uk", "com.au", "net.au", "co.nz", "com.br", "com.mx",
    }:
        result = ".".join(parts[-3:])
    else:
        result = ".".join(parts[-2:])
    if result in EXCLUDE_DOMAINS or any(result.endswith("." + x) for x in EXCLUDE_DOMAINS):
        return ""
    if parts[-1] in {"gov", "mil", "edu"}:
        return ""
    return result


def ddg_search(query: str, region: str, limit: int = 8) -> list[dict]:
    try:
        raw = DDGS().text(query, region=region, safesearch="moderate", max_results=limit)
        return list(raw or [])
    except Exception as exc:
        print(f"[search warning] {type(exc).__name__}: {exc}")
        return []


def search_plan():
    plan = []
    regions = [
        ("us-en", "USA", "United States"),
        ("ca-en", "Canada", "Canada"),
    ]
    templates = [
        'direct to consumer ecommerce {niche} {country} online store',
        'best {niche} brands selling online in {country}',
        'online retailer {niche} brand headquarters {country}',
        'Shopify ecommerce {niche} company {country}',
    ]
    for region, guess, country in regions:
        for niche in NICHES:
            for template in templates:
                plan.append((template.format(niche=niche, country=country), region, guess))
    return plan


def name_from_title(title: str, domain: str) -> str:
    value = str(title or "").strip()
    for separator in (" | ", " — ", " – ", " - ", " :: "):
        if separator in value:
            value = value.split(separator, 1)[0].strip()
            break
    value = re.sub(r"\b(official website|official site|home page)\b", "", value, flags=re.I).strip()
    return value[:140] or domain


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as stream:
            return list(csv.DictReader(stream))
    except (OSError, csv.Error):
        return []


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def discover(target: int, result_limit: int) -> int:
    output: dict[str, dict] = {}
    plan = search_plan()
    print(f"Searching public web results with {len(plan)} queries; target={target} candidate domains.")
    for idx, (query, region, country) in enumerate(plan, 1):
        if len(output) >= target:
            break
        results = ddg_search(query, region, result_limit)
        for result in results:
            url = str(result.get("href") or result.get("url") or "").strip()
            domain = root_domain(url)
            if not domain or urlparse(url).scheme not in {"http", "https"}:
                continue
            if re.search(r"\.(pdf|png|jpg|jpeg|gif|zip|docx?)(?:$|\?)", url, re.I):
                continue
            if domain not in output:
                title = str(result.get("title") or "")
                output[domain] = {
                    "company_name": name_from_title(title, domain),
                    "website": "https://" + domain,
                    "country_guess": country,
                    "discovery_query": query,
                    "discovery_source_url": url,
                    "discovered_at": date.today().isoformat(),
                }
        print(f"[discover] {idx}/{len(plan)} queries; {len(output)} unique domains")
        time.sleep(DELAY)
    rows = list(output.values())
    write_csv(ROOT / "ecom_companies.csv", rows, COMPANY_FIELDS)
    print(f"Saved {len(rows)} candidate companies to ecom_companies.csv.")
    if len(rows) < target:
        print("Public search yielded fewer candidates than requested; no records were fabricated.")
    return 0 if rows else 1


def robots_can_fetch(base_url: str, url: str, session: requests.Session, cache: dict) -> bool:
    if base_url not in cache:
        parser = RobotFileParser()
        robots_url = urljoin(base_url, "/robots.txt")
        try:
            response = session.get(robots_url, timeout=5)
            if response.status_code in {404, 410}:
                # A missing robots.txt has no crawl directives.
                cache[base_url] = "allow"
            elif response.status_code < 400 and "user-agent" in response.text.lower():
                parser.parse(response.text.splitlines())
                cache[base_url] = parser
            else:
                # Be conservative for denied, rate-limited, or ambiguous responses.
                cache[base_url] = None
        except requests.RequestException:
            cache[base_url] = None
    parser = cache[base_url]
    if parser == "allow":
        return True
    return parser.can_fetch(AGENT, url) if parser is not None else False


def mx_status(email: str) -> str:
    domain = email.rsplit("@", 1)[-1].lower().strip()
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=4)
        return "MX_PRESENT_MAILBOX_NOT_VERIFIED" if list(answers) else "NO_MX_FOUND"
    except Exception:
        return "MX_UNKNOWN"


def extract_contacts(company: dict, max_pages: int = 6) -> list[dict]:
    domain = root_domain(company.get("website", ""))
    if not domain:
        return []
    session = requests.Session()
    session.headers.update(HEADERS)
    base = company["website"].rstrip("/")
    urls = [base + p for p in (
        "", "/contact", "/contact-us", "/pages/contact-us", "/about",
        "/about-us", "/pages/about-us", "/team", "/leadership", "/our-story",
    )]
    robots_cache, seen, rows = {}, set(), []
    while urls and len(seen) < max_pages:
        url = urls.pop(0)
        url, _ = urldefrag(url)
        if url in seen or root_domain(url) != domain:
            continue
        seen.add(url)
        current_base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if not robots_can_fetch(current_base, url, session, robots_cache):
            continue
        try:
            response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code >= 400 or root_domain(response.url) != domain:
                continue
            ctype = response.headers.get("Content-Type", "").lower()
            if ctype and "html" not in ctype:
                continue
        except requests.RequestException:
            continue
        soup = BeautifulSoup(response.text[:1_500_000], "html.parser")
        visible_text = soup.get_text(" ", strip=True)
        raw_text = response.text + " " + visible_text
        emails = []
        for email in EMAIL_RE.findall(raw_text):
            email = email.strip(".,;:()[]{}<>").lower()
            if any(x in email for x in ("example.com", "yourdomain.com", "sentry.io", "wixpress.com")):
                continue
            if "noreply@" not in email and "no-reply@" not in email:
                emails.append(email)
        phones = []
        country = "CA" if company.get("country_guess") == "Canada" else "US"
        for match in PHONE_RE.findall(visible_text):
            try:
                parsed = phonenumbers.parse(match, country)
                if phonenumbers.is_valid_number(parsed):
                    phones.append(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL))
            except phonenumbers.NumberParseException:
                pass
        snippets = []
        for el in soup.select("h1,h2,h3,h4,p,li,address"):
            snippet = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()
            if 12 <= len(snippet) <= 240 and any(role in " " + snippet.lower() for role in ROLE_TERMS):
                snippets.append(snippet)
        linkedin_company = []
        for a in soup.find_all("a", href=True):
            href = urljoin(response.url, a["href"])
            if "linkedin.com/company/" in href.lower():
                linkedin_company.append(href.split("?")[0])
            anchor_text = (a.get_text(" ", strip=True) + " " + href).lower()
            if root_domain(href) == domain and any(k in anchor_text for k in ("contact", "about", "team", "leadership", "founder")):
                if href not in seen and href not in urls:
                    urls.append(href)
        for email in unique(emails):
            rows.append({
                "company_name": company.get("company_name", ""),
                "website": company.get("website", ""),
                "page_url": response.url,
                "public_email": email,
                "email_domain_mx": mx_status(email),
                "email_status": "PUBLICLY_LISTED_NOT_DELIVERABILITY_VERIFIED",
                "public_phone": "",
                "phone_status": "",
                "person_role_snippets": " | ".join(unique(snippets)[:10]),
                "linkedin_company_url": "; ".join(unique(linkedin_company)),
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        for phone in unique(phones):
            rows.append({
                "company_name": company.get("company_name", ""),
                "website": company.get("website", ""),
                "page_url": response.url,
                "public_email": "",
                "email_domain_mx": "",
                "email_status": "",
                "public_phone": phone,
                "phone_status": "NUMBER_FORMAT_VALID_PUBLIC_NUMBER_NOT_LIVE_VERIFIED",
                "person_role_snippets": " | ".join(unique(snippets)[:10]),
                "linkedin_company_url": "; ".join(unique(linkedin_company)),
                "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
        time.sleep(DELAY)
    return rows


def result_list(query: str, region: str, limit: int = 5) -> list[dict]:
    time.sleep(DELAY)
    return ddg_search(query, region, limit)


def research_companies(limit: int, offset: int) -> int:
    companies = read_csv(ROOT / "ecom_companies.csv")
    if not companies:
        print("ecom_companies.csv not found. Run the discover command first.")
        return 1
    existing = {row.get("website", "").lower(): row for row in read_csv(ROOT / "ecom_review_queue.csv")}
    selected = companies[offset:offset + limit]
    if not selected:
        print("No companies in this offset/limit range.")
        return 1
    contact_rows = read_csv(ROOT / "ecom_public_contacts.csv")
    contact_by_domain = {}
    for row in contact_rows:
        contact_by_domain.setdefault(row.get("website", "").lower(), []).append(row)
    review_rows = list(existing.values())
    for idx, company in enumerate(selected, 1):
        site = company.get("website", "")
        if site.lower() in existing and existing[site.lower()].get("research_completed") == "yes":
            print(f"[research] skipping already researched {site}")
            continue
        country = "ca-en" if company.get("country_guess") == "Canada" else "us-en"
        people_query = f'site:linkedin.com/in ("Founder" OR "CEO" OR "Owner" OR "CMO" OR "Head of Marketing" OR "VP Marketing" OR "Head of Ecommerce") "{company.get("company_name","")}"'
        employee_query = f'"{company.get("company_name","")}" employees company size headquarters'
        meta_query = f'site:facebook.com/ads/library "{company.get("company_name","")}"'
        google_ads_query = f'site:adstransparency.google.com "{company.get("company_name","")}"'
        people_results = result_list(people_query, country, 6)
        employee_results = result_list(employee_query, country, 5)
        meta_results = result_list(meta_query, country, 4)
        google_results = result_list(google_ads_query, country, 4)
        person_matches = []
        for item in people_results:
            url = str(item.get("href") or item.get("url") or "")
            if "linkedin.com/in/" in url.lower():
                person_matches.append({
                    "url": url.split("?")[0],
                    "title": str(item.get("title") or ""),
                    "snippet": str(item.get("body") or ""),
                })
        employee_matches = [
            {"url": str(x.get("href") or x.get("url") or ""),
             "title": str(x.get("title") or ""), "snippet": str(x.get("body") or "")}
            for x in employee_results
        ]
        ad_matches = []
        for platform, results in (("Meta", meta_results), ("Google", google_results)):
            for item in results:
                url = str(item.get("href") or item.get("url") or "")
                if url:
                    ad_matches.append({
                        "platform": platform, "url": url,
                        "title": str(item.get("title") or ""),
                        "snippet": str(item.get("body") or ""),
                    })
        site_contacts = extract_contacts(company)
        contact_rows.extend(site_contacts)
        contact_by_domain[site.lower()] = contact_by_domain.get(site.lower(), []) + site_contacts
        public_emails = unique([r.get("public_email", "") for r in contact_by_domain.get(site.lower(), [])])
        public_phones = unique([r.get("public_phone", "") for r in contact_by_domain.get(site.lower(), [])])
        email_source = next((r.get("page_url", "") for r in contact_by_domain.get(site.lower(), []) if r.get("public_email")), "")
        phone_source = next((r.get("page_url", "") for r in contact_by_domain.get(site.lower(), []) if r.get("public_phone")), "")
        current = {
            "company_name": company.get("company_name", ""),
            "website": site,
            "country_guess": company.get("country_guess", ""),
            "discovery_source_url": company.get("discovery_source_url", ""),
            "public_email_candidates": "; ".join(public_emails),
            "email_source_url": email_source,
            "email_domain_mx": "; ".join(unique([r.get("email_domain_mx", "") for r in contact_by_domain.get(site.lower(), []) if r.get("public_email")])),
            "public_phone_candidates": "; ".join(public_phones),
            "phone_source_url": phone_source,
            "phone_status": "FORMAT_CHECK_ONLY_NOT_LIVE_VERIFIED" if public_phones else "not_found",
            "decision_maker_name": "",
            "decision_maker_title": "",
            "decision_maker_linkedin_url": person_matches[0]["url"] if person_matches else "",
            "decision_maker_search_source_url": "https://duckduckgo.com/?q=" + requests.utils.quote(people_query),
            "decision_maker_search_snippet": " | ".join(p["title"] + " — " + p["snippet"] for p in person_matches[:3]),
            "employee_count": "",
            "employees_51_plus_confirmed": "",
            "employee_evidence_url": employee_matches[0]["url"] if employee_matches else "",
            "employee_evidence_snippet": " | ".join(x["title"] + " — " + x["snippet"] for x in employee_matches[:3]),
            "active_ads_confirmed": "",
            "ad_platform": "; ".join(unique([a["platform"] for a in ad_matches])),
            "ad_evidence_url": "; ".join(unique([a["url"] for a in ad_matches[:6]])),
            "ad_last_seen_date": "",
            "confirmed_country": "",
            "decision_maker_email": "",
            "email_verification_status": "NOT_VERIFIED",
            "phone_live_verified": "",
            "decision_maker_phone": "",
            "decision_maker_source_url": "",
            "review_status": "REQUIRES_MANUAL_REVIEW",
            "research_completed": "yes",
        }
        for old in review_rows:
            if old.get("website", "").lower() == site.lower():
                # Preserve human review decisions and verified fields across later batches.
                # Refresh only the raw public-contact candidates and fresh search snippets.
                refreshable = {
                    "public_email_candidates", "public_phone_candidates",
                    "employee_evidence_snippet", "decision_maker_search_source_url",
                    "decision_maker_search_snippet", "research_completed",
                }
                for key, value in old.items():
                    if value and key not in refreshable:
                        current[key] = value
                review_rows.remove(old)
                break
        review_rows.append(current)
        print(f"[research] {idx}/{len(selected)}: {company.get('company_name','')} | public emails={len(public_emails)} | profile candidates={len(person_matches)}")
        # De-duplicate contacts when a batch is rerun.
        seen_contact_rows = set()
        deduped_contacts = []
        for contact in contact_rows:
            key = (
                contact.get("website", "").lower(),
                contact.get("page_url", ""),
                contact.get("public_email", "").lower(),
                contact.get("public_phone", ""),
            )
            if key not in seen_contact_rows:
                seen_contact_rows.add(key)
                deduped_contacts.append(contact)
        contact_rows = deduped_contacts
        write_csv(ROOT / "ecom_public_contacts.csv", contact_rows, CONTACT_FIELDS)
        write_csv(ROOT / "ecom_review_queue.csv", review_rows, RESEARCH_FIELDS + ["research_completed"])
    print("Saved ecom_public_contacts.csv and ecom_review_queue.csv.")
    print("Search results are clues only; manually confirm employee count, current ads, identity and contact validity.")
    return 0


def qualify(max_ad_age_days: int) -> int:
    rows = read_csv(ROOT / "ecom_review_queue.csv")
    final = []
    for row in rows:
        try:
            employees = int(re.sub(r"[^0-9]", "", row.get("employee_count", "")))
        except ValueError:
            employees = 0
        country = re.sub(r"[^a-z]", "", row.get("confirmed_country", "").lower())
        email_status = row.get("email_verification_status", "").strip().lower()
        try:
            ad_date = date.fromisoformat(row.get("ad_last_seen_date", "").strip()[:10])
            age = (date.today() - ad_date).days
        except ValueError:
            age = 10_000
        checks = [
            country in {"usa", "unitedstates", "canada", "us", "ca"},
            employees > 50,
            row.get("employees_51_plus_confirmed", "").strip().lower() in YES,
            bool(row.get("employee_evidence_url", "").strip()),
            row.get("active_ads_confirmed", "").strip().lower() in YES,
            bool(row.get("ad_evidence_url", "").strip()),
            0 <= age <= max_ad_age_days,
            bool(row.get("decision_maker_name", "").strip()),
            bool(row.get("decision_maker_title", "").strip()),
            bool(row.get("decision_maker_linkedin_url", "").strip()),
            bool(row.get("decision_maker_email", "").strip()),
            email_status in {"verified", "deliverable_confirmed", "licensed_provider_verified", "delivery_confirmed"},
            bool(row.get("email_source_url", "").strip()),
            bool(row.get("decision_maker_phone", "").strip()),
            row.get("phone_live_verified", "").strip().lower() in YES,
            bool(row.get("decision_maker_source_url", "").strip()),
            bool(row.get("website", "").strip()),
        ]
        if all(checks):
            row["review_status"] = "QUALIFIED_REVIEWED"
            final.append(row)
    write_csv(ROOT / "qualified_ecommerce_leads.csv", final, RESEARCH_FIELDS)
    print(f"Wrote {len(final)} strictly reviewed leads to qualified_ecommerce_leads.csv.")
    if len(final) < 1000:
        print("No rows were invented to reach the target. Continue research and verification to grow the list.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="No-key public-source ecommerce ICP research")
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover", help="discover candidate ecommerce brand domains from public search")
    d.add_argument("--target", type=int, default=1000)
    d.add_argument("--results-per-query", type=int, default=15)
    r = sub.add_parser("research", help="collect public-site contacts and search clues for a batch")
    r.add_argument("--limit", type=int, default=50, help="companies to research in this batch")
    r.add_argument("--offset", type=int, default=0, help="start row in ecom_companies.csv (0-based)")
    q = sub.add_parser("qualify", help="write final CSV from manually reviewed records")
    q.add_argument("--max-ad-age-days", type=int, default=30)
    args = parser.parse_args()
    if args.command == "discover":
        if args.target < 1 or args.results_per_query < 1:
            parser.error("target and results-per-query must be positive")
        return discover(args.target, args.results_per_query)
    if args.command == "research":
        if args.limit < 1 or args.offset < 0:
            parser.error("limit must be positive and offset must be zero or greater")
        return research_companies(args.limit, args.offset)
    return qualify(args.max_ad_age_days)


if __name__ == "__main__":
    raise SystemExit(main())
