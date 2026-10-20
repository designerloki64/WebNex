# WebNex: Free Ecommerce ICP Research

A no-paid-API Python workflow for discovering ecommerce brand candidates in the United States and Canada, collecting contact information published on company-owned sites, finding decision-maker profile **links** via public search snippets, and building an evidence-backed review queue.

## What it does

- Searches public web results for ecommerce / direct-to-consumer brands.
- Visits company-owned pages only when the site's accessible robots.txt permits crawling.
- Extracts emails and phone numbers visibly published on those pages. It never generates guessed personal email addresses.
- Checks whether the email domain has MX records. MX is not mailbox verification; the particular mailbox may not exist.
- Searches public results for relevant LinkedIn profile links, but does not visit or scrape LinkedIn pages.
- Collects search-result clues and source URLs about employee size and public ad libraries.
- Produces CSV files with evidence columns.
- Exports a strict final CSV only after the reviewer confirms all ICP fields and email/phone verification.

## Important limitations

There is no legitimate one-click, completely free route that guarantees 1,000 currently advertising companies with 51+ employees and verified person-level email/phone data from the entire internet. Public search providers may rate-limit requests, and public evidence may be missing.

This tool **does not** scrape Apollo, LinkedIn, or login-gated pages; bypass CAPTCHAs, anti-bot systems, paywalls or usage caps; rotate proxies to evade blocks; or probe SMTP servers to guess mailbox existence. Apollo's terms prohibit automated scraping and attempts to circumvent platform limits. Use the company's supported exports and methods where authorized.

A record is not marked “qualified” because a search result suggested it might fit. Search clues require review.

## Requirements

- Windows 10/11
- Python 3.11+ recommended
- Internet access
- No paid APIs or API keys

## Install on Windows

Download the repository ZIP from GitHub and extract it, or clone the repository.

\`\`\`powershell
git clone https://github.com/designerloki64/WebNex.git
cd WebNex

py -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install --upgrade pip
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt
\`\`\`

If git is not installed, download the ZIP here:
https://github.com/designerloki64/WebNex/archive/refs/heads/main.zip

## Step 1 — Discover candidate brands

Test with 100 candidate domains first:

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py discover --target 100
\`\`\`

Then expand the discovery target:

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py discover --target 1000
\`\`\`

Output: ecom_companies.csv

The number is a candidate target, not a promise. The script stops if it exhausts its public queries or the search backend fails/rate-limits.

## Step 2 — Research the first 25 companies

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py research --limit 25 --offset 0
\`\`\`

Output files:

- ecom_public_contacts.csv — public site emails/phone numbers with the source page and status notes.
- ecom_review_queue.csv — company, profile, company-size and advertising evidence clues, plus human review columns.

Research the next batch:

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py research --limit 25 --offset 25
\`\`\`

Continue with offsets 50, 75, etc. The review queue preserves fields you've already filled in when you rerun later batches.

Each company requires a few independent public searches, so researching 1,000 companies may take a long time and may be throttled by free search providers. Start small and respect delays.

## Step 3 — Confirm the ICP facts

Open ecom_review_queue.csv in Excel. For every viable candidate:

1. Confirm that it sells products online and that its headquarters are in the United States or Canada.
2. Verify that employee count is 51 or higher using a credible source. Fill employee_count, set employees_51_plus_confirmed to yes, and keep employee_evidence_url.
3. Manually check active commercial ads in:
   - Meta Ad Library: https://www.facebook.com/ads/library/
   - Google Ads Transparency Center: https://adstransparency.google.com/
4. Record the actual ad evidence URL, platform, and date last observed. Set active_ads_confirmed to yes only when you actually confirm an active ad.
5. Confirm the decision-maker's identity/title from a credible public source. decision_maker_linkedin_url is only a candidate discovered in search results until you verify it.
6. Use public_email_candidates and public_phone_candidates as leads for review, not as verified contact fields. Only put the confirmed person's actual work contact into decision_maker_email and decision_maker_phone.
7. Set email_verification_status to verified / deliverable_confirmed only when you have real confirmation (for example, a reputable verifier you are authorized to use, actual delivery confirmation, or a valid reply). MX presence alone is not enough.
8. Set phone_live_verified to yes only after a reliable independent check. A valid number format does not prove that it is working or belongs to the decision-maker.
9. Add decision_maker_source_url that supports the name/title/contact association.

## Step 4 — Export only reviewed leads

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py qualify
\`\`\`

Output: qualified_ecommerce_leads.csv

The final export requires all of these: confirmed US/Canada location, more than 50 employees with evidence, active ads observed within the last 30 days, decision-maker name/title/LinkedIn URL, independently confirmed email and phone, and supporting source URLs. The script will not invent rows to reach 1,000.

To allow a different freshness window for advertising evidence:

\`\`\`powershell
.\\.venv\\Scripts\\python.exe ecom_icp_researcher.py qualify --max-ad-age-days 14
\`\`\`

## Output columns

The review sheet separates **raw clues** from **confirmed facts**. It includes the company website, public contact candidates and source pages, LinkedIn profile candidate/search result, employee evidence, ad-evidence candidates, confirmed decision-maker fields, and verification/review status.

## Troubleshooting

- If py is not recognized, install Python 3.11+ and reopen PowerShell.
- If package installation fails, run .\\.venv\\Scripts\\python.exe -m pip install --upgrade pip and retry.
- If there are few search results or search warnings, reduce the target, wait, and try later. Do not bypass a block or CAPTCHA.
- If contact CSVs are empty, the websites may not publish those details or may disallow automated crawling.
- If your output has fewer than 1,000 qualified leads, that's expected when evidence/contact verification is incomplete. The tool will not label unverified leads as qualified.

## Responsible use

Public availability does not mean consent for marketing outreach. Review applicable privacy, email and telemarketing law, including Canada's CASL and the US CAN-SPAM Act, before contacting prospects.
