#!/usr/bin/env python3
"""
Free Ecommerce ICP Lead Finder
- No paid API keys or subscriptions.
- Discovers candidate company domains via DDGS metasearch.
- Collects only business contact details visibly published on public pages.
- Never guesses person-specific email addresses or marks contacts verified automatically.
- Employee size, active ads, mailbox delivery and live phone status require independent review.
Requires Python 3.10+.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import phonenumbers
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

OUT = Path(".")
USER_AGENT = "FreeEcommerceResearchBot/1.0 (public business research; respectful crawl)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
TIMEOUT = 7
PRODUCT_NICHES = [
    "beauty", "skincare", "haircare", "apparel", "footwear", "jewelry",
    "home decor", "furniture", "pet supplies", "outdoor gear", "sports goods",
    "consumer electronics", "food and beverage", "baby products", "wellness products",
    "kitchenware",
]
COUNTRIES = [("United States", "us-en", "USA"), ("Canada", "ca-en", "Canada")]
SEARCH_HOSTS = {
    "google.com", "bing.com", "duckduckgo.com", "yahoo.com", "brave.com",
    "wikipedia.org", "linkedin.com", "facebook.com", "instagram.com", "tiktok.com",
    "youtube.com", "pinterest.com", "reddit.com", "x.com", "twitter.com",
    "amazon.com", "amazon.ca", "ebay.com", "walmart.com", "etsy.com",
    "shopify.com", "myshopify.com", "bigcommerce.com", "woocommerce.com",
    "forbes.com", "businessinsider.com", "inc.com", "crunchbase.com",
    "yelp.com", "yellowpages.com", "bbb.org", "trustpilot.com", "g2.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com", "medium.com",
}
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?1[\s().-]?)?(?:\(\s*\d{3}\s*\)|\d{3})[\s.-]?\d{3}[\s.-]?\d{4}(?:\s*(?:x|ext\.?)\s*\d{1,6})?(?!\w)")
LEADERSHIP_TERMS = (
    "founder", "co-founder", "chief executive", " ceo", "chief marketing",
    " cmo", "vp marketing", "vice president of marketing", "head of marketing",
    "head of ecommerce", "e-commerce director", "ecommerce director",
    "chief growth", "owner", "president",
)
COMPANY_FIELDS = [
    "company_domain", "company_name", "country_guess", "search_queries",
    "search_evidence_urls", "discovered_at",
]
CONTACT_FIELDS = [
    "company_domain", "company_name", "country_guess", "page_url",
    "public_email_candidates", "public_phone_candidates", "leadership_snippets",
    "email_status", "phone_status", "crawled_at",
]
REVIEW_FIELDS = [
    "company_domain", "company_name", "country_guess", "search_evidence_urls",
    "contact_source_urls", "public_email_candidates", "public_phone_candidates",
    "leadership_evidence", "confirmed_country", "employee_count",
    "employee_evidence_url", "employees_51_plus_confirmed", "active_ads_confirmed",
    "ad_platform", "ad_evidence_url", "ad_last_seen_date", "decision_maker_name",
    "decision_maker_title", "decision_maker_email", "email_deliverability_verified",
    "decision_maker_phone", "phone_live_verified", "decision_maker_source_url",
    "review_status",
]
MANUAL_FIELDS = REVIEW_FIELDS[8:]
YES = {"yes", "y", "true", "1", "confirmed"}

def unique(items):
    output, seen = [], set()
    for item in items:
        item = str(item or "").strip()
        if item and item not in seen:
            seen.add(item)
            output.append(item)
    return output

def registrable_domain(url_or_host: str) -> str:
    parsed = urlparse(url_or_host if "://" in url_or_host else "//" + url_or_host)
    host = (parsed.hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host or re.fullmatch(r"\d+(?:\.\d+){3}", host):
        return ""
    parts = host.split(".")
    common_two_part_suffixes = {
        ("co", "uk"), ("org", "uk"), ("ac", "uk"), ("com", "uk"),
        ("com", "au"), ("net", "au"), ("org", "au"), ("co", "nz"),
        ("com", "sg"), ("co", "jp"), ("com", "br"), ("com", "mx"),
    }
    if len(parts) >= 3 and tuple(parts[-2:]) in common_two_part_suffixes:
        domain = ".".join(parts[-3:])
    else:
        domain = ".".join(parts[-2:])
    if any(domain == blocked or domain.endswith("." + blocked) for blocked in SEARCH_HOSTS):
        return ""
    if any(domain.endswith(ext) for ext in (".gov", ".edu", ".mil")):
        return ""
    return domain

def result_country_guess(region_label: str) -> str:
    return region_label or "Needs confirmation"

def search_queries():
    queries = []
    for country, region, guess in COUNTRIES:
        for niche in PRODUCT_NICHES:
            queries.append((f'ecommerce brand "{niche}" "{country}" online store', region, guess))
            queries.append((f'online retailer "{niche}" "{country}" company', region, guess))
    return queries

def discover(target: int, max_results_per_query: int, delay: float):
    companies = {}
    queries = search_queries()
    print(f"[search] {len(queries)} public search queries; target={target} candidate domains")
    for index, (query, region, country_guess) in enumerate(queries, start=1):
        if len(companies) >= target:
            break
        try:
            results = DDGS().text(query, region=region, safesearch="moderate",
                                  max_results=max_results_per_query, backend="auto")
        except Exception as exc:
            print(f"[search warning] query {index}/{len(queries)} failed: {type(exc).__name__}: {exc}")
            time.sleep(max(delay, 1.0))
            continue
        for result in results or []:
            href = str(result.get("href") or result.get("url") or "").strip()
            domain = registrable_domain(href)
            if not domain:
                continue
            parsed = urlparse(href)
            if parsed.scheme not in ("http", "https"):
                continue
            if re.search(r"\.(pdf|jpg|jpeg|png|gif|zip|docx?)(?:$|\?)", parsed.path, re.I):
                continue
            title = str(result.get("title") or "").strip()
            body = str(result.get("body") or result.get("snippet") or "").strip()
            item = companies.setdefault(domain, {
                "company_domain": domain,
                "company_name": title_to_name(title, domain),
                "country_guess": country_guess,
                "search_queries": [],
                "search_evidence_urls": [],
                "discovered_at": datetime.now(timezone.utc).date().isoformat(),
            })
            item["search_queries"] = unique(item["search_queries"] + [query])
            item["search_evidence_urls"] = unique(item["search_evidence_urls"] + [href])
            # Replace a generic domain-derived name when a better title is found.
            if item["company_name"] == domain and title:
                item["company_name"] = title_to_name(title, domain)
        print(f"[search] {index}/{len(queries)} — {len(companies)} unique candidate domains")
        time.sleep(delay)
    return list(companies.values())

def title_to_name(title: str, domain: str) -> str:
    name = title.strip()
    for separator in (" | ", " — ", " – ", " - ", " :: "):
        if separator in name:
            name = name.split(separator, 1)[0].strip()
            break
    name = re.sub(r"\s+(official website|official site|home page)$", "", name, flags=re.I).strip()
    return name[:140] or domain

def robots_allowed(base_url: str, url: str, session: requests.Session) -> bool:
    # Missing/unavailable robots.txt is not treated as evidence that all crawling is allowed;
    # this conservative crawler checks explicit rules whenever robots.txt is accessible.
    from urllib.robotparser import RobotFileParser
    robots_url = urljoin(base_url, "/robots.txt")
    try:
        response = session.get(robots_url, timeout=5)
        if response.status_code < 400 and "user-agent" in response.text.lower():
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(response.text.splitlines())
            return parser.can_fetch(USER_AGENT, url)
    except requests.RequestException:
        pass
    return True

def valid_public_phone_candidates(text: str, country_guess: str) -> list[str]:
    default_region = "CA" if country_guess == "Canada" else "US"
    found = []
    for raw in PHONE_RE.findall(text or ""):
        candidate = re.sub(r"\s*(?:x|ext\.?)\s*\d{1,6}$", "", raw, flags=re.I).strip()
        valid = None
        for region in (default_region, "US" if default_region == "CA" else "CA"):
            try:
                parsed = phonenumbers.parse(candidate, region)
                if phonenumbers.is_valid_number(parsed):
                    valid = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
                    break
            except phonenumbers.NumberParseException:
                continue
        if valid:
            found.append(valid)
    return unique(found)

def extract_page(url: str, domain: str, company_name: str, country_guess: str,
                 session: requests.Session, base_url: str):
    if registrable_domain(url) != domain:
        return None, None
    if not robots_allowed(base_url, url, session):
        return None, None
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400 or registrable_domain(response.url) != domain:
            return None, None
        content_type = response.headers.get("Content-Type", "").lower()
        if "html" not in content_type and content_type:
            return None, None
    except requests.RequestException:
        return None, None
    soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    emails = []
    for email in EMAIL_RE.findall(response.text + " " + text):
        email = email.strip(".,;:()[]{}<>").lower()
        if email.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            continue
        if any(token in email for token in ("example.com", "yourdomain.com", "sentry.io", "wixpress.com")):
            continue
        if "noreply@" not in email and "no-reply@" not in email:
            emails.append(email)
    phones = valid_public_phone_candidates(text, country_guess)
    snippets = []
    for element in soup.select("h1, h2, h3, h4, p, li, address"):
        snippet = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
        low = " " + snippet.lower()
        if 12 <= len(snippet) <= 220 and any(term in low for term in LEADERSHIP_TERMS):
            snippets.append(snippet)
    links = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(response.url, anchor["href"])
        href, _ = urldefrag(href)
        if registrable_domain(href) != domain or urlparse(href).scheme not in ("http", "https"):
            continue
        anchor_text = (anchor.get_text(" ", strip=True) + " " + href).lower()
        if any(word in anchor_text for word in ("contact", "about", "our-story", "our story",
                                                 "leadership", "team", "founder", "company")):
            links.append(href)
    row = {
        "company_domain": domain,
        "company_name": company_name,
        "country_guess": country_guess,
        "page_url": response.url,
        "public_email_candidates": "; ".join(unique(emails)),
        "public_phone_candidates": "; ".join(unique(phones)),
        "leadership_snippets": " | ".join(unique(snippets)[:12]),
        "email_status": "PUBLICLY_LISTED_NOT_DELIVERABILITY_VERIFIED" if emails else "not_found",
        "phone_status": "FORMAT_PLAUSIBLE_NOT_LIVE_VERIFIED" if phones else "not_found",
        "crawled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return row, unique(links)

def crawl_company(company: dict, delay: float, pages_per_site: int):
    domain = company["company_domain"]
    session = requests.Session()
    session.headers.update(HEADERS)
    base_url = "https://" + domain
    try:
        response = session.get(base_url, timeout=TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            raise requests.RequestException(f"HTTP {response.status_code}")
        if registrable_domain(response.url) != domain:
            raise requests.RequestException("redirected outside candidate domain")
        base_url = f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}"
    except requests.RequestException:
        base_url = "http://" + domain
        try:
            response = session.get(base_url, timeout=TIMEOUT, allow_redirects=True)
            if response.status_code >= 400 or registrable_domain(response.url) != domain:
                return []
            base_url = f"{urlparse(response.url).scheme}://{urlparse(response.url).netloc}"
        except requests.RequestException:
            return []
    urls = [base_url + "/"]
    urls += [
        urljoin(base_url, path) for path in
        ("/contact", "/contact-us", "/pages/contact-us", "/about", "/about-us",
         "/pages/about-us", "/pages/our-story", "/our-story", "/team", "/leadership")
    ]
    initial_links = []
    output, seen = [], set()
    while urls and len(output) < pages_per_site:
        url = urls.pop(0)
        url, _ = urldefrag(url)
        if url in seen or registrable_domain(url) != domain:
            continue
        seen.add(url)
        row, links = extract_page(url, domain, company["company_name"],
                                  company["country_guess"], session, base_url)
        time.sleep(delay)
        if row:
            output.append(row)
            for link in links or []:
                if link not in seen:
                    initial_links.append(link)
        # Add relevant homepage-discovered links after standard contact/about paths.
        if not urls and initial_links:
            urls.extend(initial_links)
            initial_links = []
    return output

def read_csv(path: Path):
    if not path.exists():
        return []
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []

def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})

def merge_old_review(new_rows: list[dict], old_rows: list[dict]):
    old_by_domain = {r.get("company_domain", "").lower(): r for r in old_rows}
    for row in new_rows:
        old = old_by_domain.get(row.get("company_domain", "").lower(), {})
        for field in MANUAL_FIELDS:
            if old.get(field, ""):
                row[field] = old[field]
    return new_rows

def scrape(args):
    companies = discover(args.target, args.max_results_per_query, args.delay)
    if not companies:
        print("No candidate domains found. Search backends may be unavailable or rate-limited.")
        return 2
    write_csv(OUT / "company_candidates.csv", companies, COMPANY_FIELDS)
    print(f"[crawl] Crawling up to {min(args.max_sites, len(companies))} company sites; this may take time.")
    crawl_rows = []
    chosen = companies[:args.max_sites]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(crawl_company, c, args.delay, args.pages_per_site): c for c in chosen}
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                crawl_rows.extend(future.result())
            except Exception as exc:
                company = futures[future]
                print(f"[crawl warning] {company['company_domain']}: {type(exc).__name__}")
            if completed % 10 == 0 or completed == len(futures):
                print(f"[crawl] {completed}/{len(futures)} company sites finished; {len(crawl_rows)} public pages collected")
    write_csv(OUT / "contact_candidates.csv", crawl_rows, CONTACT_FIELDS)

    by_domain = {c["company_domain"]: dict(c) for c in companies}
    for domain, company in by_domain.items():
        pages = [r for r in crawl_rows if r["company_domain"] == domain]
        company["contact_source_urls"] = "; ".join(unique([r["page_url"] for r in pages]))
        company["public_email_candidates"] = "; ".join(unique(
            email for r in pages for email in r["public_email_candidates"].split(";") if email.strip()
        ))
        company["public_phone_candidates"] = "; ".join(unique(
            phone for r in pages for phone in r["public_phone_candidates"].split(";") if phone.strip()
        ))
        company["leadership_evidence"] = " | ".join(unique(
            snippet for r in pages for snippet in r["leadership_snippets"].split(" | ") if snippet.strip()
        )[:20])
        for field in MANUAL_FIELDS:
            company.setdefault(field, "")
    existing = read_csv(OUT / "review_queue.csv")
    review_rows = merge_old_review(list(by_domain.values()), existing)
    write_csv(OUT / "review_queue.csv", review_rows, REVIEW_FIELDS)
    print("\nFinished. Files created:")
    print("  company_candidates.csv  — candidate companies; size and ads are not automatically confirmed")
    print("  contact_candidates.csv  — source-linked public contact clues; not guaranteed deliverable/live")
    print("  review_queue.csv        — review/edit this file, then run --qualify-reviewed")
    print(f"Discovered {len(companies)} candidate domains and collected {len(crawl_rows)} public pages.")
    return 0

def truthy(value: str) -> bool:
    return str(value or "").strip().lower() in YES

def recent_ad_date(value: str, max_days: int) -> bool:
    try:
        seen = date.fromisoformat(str(value).strip()[:10])
        age = (date.today() - seen).days
        return 0 <= age <= max_days
    except (ValueError, TypeError):
        return False

def country_is_supported(value: str) -> bool:
    norm = re.sub(r"[^a-z]", "", str(value or "").lower())
    return norm in {"us", "usa", "unitedstates", "canada", "ca"}

def qualify_reviewed(max_ad_age_days: int):
    rows = read_csv(OUT / "review_queue.csv")
    if not rows:
        print("review_queue.csv not found or empty. Run the discovery step first.")
        return 2
    qualified = []
    for row in rows:
        try:
            employee_count = int(re.sub(r"[^\d]", "", row.get("employee_count", "")))
        except (TypeError, ValueError):
            employee_count = 0
        checks = [
            country_is_supported(row.get("confirmed_country", "")),
            employee_count > 50,
            truthy(row.get("employees_51_plus_confirmed", "")),
            truthy(row.get("active_ads_confirmed", "")),
            recent_ad_date(row.get("ad_last_seen_date", ""), max_ad_age_days),
            truthy(row.get("email_deliverability_verified", "")),
            truthy(row.get("phone_live_verified", "")),
            bool(row.get("decision_maker_name", "").strip()),
            bool(row.get("decision_maker_title", "").strip()),
            bool(row.get("decision_maker_email", "").strip()),
            bool(row.get("decision_maker_phone", "").strip()),
            bool(row.get("employee_evidence_url", "").strip()),
            bool(row.get("ad_evidence_url", "").strip()),
            bool(row.get("decision_maker_source_url", "").strip()),
        ]
        if all(checks):
            row["review_status"] = "QUALIFIED_MANUALLY_REVIEWED"
            qualified.append(row)
    write_csv(OUT / "qualified_leads.csv", qualified, REVIEW_FIELDS)
    print(f"Wrote {len(qualified)} manually reviewed leads to qualified_leads.csv.")
    if len(qualified) < 1000:
        print("The tool will not fabricate missing records to reach 1,000. Review more valid candidates or gather more candidates.")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Free public-source ecommerce ICP candidate finder")
    parser.add_argument("--target", type=int, default=1000, help="target number of unique candidate domains (default: 1000)")
    parser.add_argument("--max-sites", type=int, default=200, help="maximum company websites to crawl (default: 200; raise carefully)")
    parser.add_argument("--max-results-per-query", type=int, default=35, help="max search results per query (default: 35)")
    parser.add_argument("--pages-per-site", type=int, default=5, help="maximum public pages to inspect per site (default: 5)")
    parser.add_argument("--delay", type=float, default=0.6, help="delay between page requests and search queries (default: 0.6 seconds)")
    parser.add_argument("--workers", type=int, default=5, help="concurrent website workers (default: 5)")
    parser.add_argument("--qualify-reviewed", action="store_true", help="create strict final CSV from manually reviewed review_queue.csv")
    parser.add_argument("--max-ad-age-days", type=int, default=30, help="maximum age of ad evidence allowed for qualification")
    args = parser.parse_args()
    if args.qualify_reviewed:
        return qualify_reviewed(args.max_ad_age_days)
    if args.target < 1 or args.max_sites < 1 or args.pages_per_site < 1 or args.workers < 1:
        parser.error("target, max-sites, pages-per-site and workers must be positive")
    return scrape(args)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped by user. CSV files written before interruption should remain available.")
        raise SystemExit(130)
