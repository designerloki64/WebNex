# Free Ecommerce ICP Lead Finder

A no-paid-API Python starter for researching ecommerce brands in the United States and Canada and collecting publicly listed business contact details.

## Important accuracy limits

This tool is a **candidate discovery and research assistant**, not a guarantee of 1,000 verified leads. Free public sources cannot reliably prove that a mailbox accepts mail, that a phone number is currently working, that a company has 51+ employees, or that it is actively running commercial ads. The script records source URLs and explicitly labels unverified facts. It does not invent personal emails or phone numbers.

## ICP

- Geography: United States and Canada
- Company type: ecommerce / online retail brands
- Employees: 51+ (must be confirmed from a reliable public source before qualification)
- Ads: currently active (must be confirmed in an ad library or other trusted public evidence)
- Decision makers: Founder, CEO, Owner, CMO, VP/Head of Marketing, Head/Director of Ecommerce

## Install (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Discover candidates

```powershell
python free_ecom_icp_lead_finder.py --target 1000
```

This performs public web searches and visits public company pages at a conservative rate. It creates:

- `candidate_companies.csv` — discovered domains and source URLs
- `contact_candidates.csv` — publicly listed emails/phone numbers and the page where each was found
- `review_queue.csv` — companies needing employee-count and advertising checks

Search providers and sites may rate-limit automated requests. Use modest targets first and obey each site's terms and robots guidance. The program includes delays and does not bypass logins, CAPTCHAs, paywalls, or access controls.

## Manual qualification workflow

For each company in `review_queue.csv`:

1. Confirm that it is an ecommerce brand and its headquarters are in the USA or Canada.
2. Confirm 51+ employees using a credible current public source. Record the source URL and date.
3. Check current ad activity in [Meta Ad Library](https://www.facebook.com/ads/library/) and [Google Ads Transparency Center](https://adstransparency.google.com/). Record the evidence URL and last-seen date.
4. Confirm the decision-maker and match the contact to a source that publicly lists their work contact information.
5. Verify email deliverability and phone status using an allowed verification method before marking them verified. DNS/MX checks and number-format checks alone are **not** verification.

The tool does not automatically promote a record to “qualified” based on guessed employee counts, guessed ad activity, email patterns, or a phone's format.

## Data fields

The output stores source URLs, discovery dates and review fields so you can audit the basis of each lead. Do not treat public availability alone as consent to send marketing messages. Follow applicable privacy, telemarketing and email laws, including CASL in Canada and CAN-SPAM in the US.
