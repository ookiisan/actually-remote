import json
import os
import re
from datetime import datetime

import requests
import yaml
from dotenv import load_dotenv
from google import genai
from google.genai import types

from scraper.scraper import load_companies

load_dotenv()


def load_config():
    """Load config.yaml and .env like main.py."""
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    return config


def build_queries(config):
    """Build search queries from config. Limit to 6 total."""
    titles = config.get('target_titles', [])[:6]
    locations = config.get('location_keywords', ['Remote', 'EMEA', 'Europe'])

    # Filter out single country codes (CH, DE) — too specific for discovery
    # Keep broader terms only (Remote, EMEA, Europe, Global, Worldwide)
    broad_locations = [l for l in locations if len(l) > 2][:3]
    if not broad_locations:
        broad_locations = ['Remote', 'EMEA', 'Europe']

    queries = []
    for i, title in enumerate(titles):
        location = broad_locations[i % len(broad_locations)]
        queries.append(
            f'site:boards.greenhouse.io OR site:jobs.lever.co '
            f'OR site:jobs.ashbyhq.com "{title}" {location}'
        )

    return queries[:6]


def parse_json_response(response_text):
    """Parse JSON from model response, stripping markdown fences if present."""
    text = response_text.strip()
    if text.startswith('```'):
        parts = text.split('```')
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith('json'):
                text = text[4:]
    return json.loads(text)


def is_job_listing_url(url):
    """Return True if URL looks like a specific job listing, not a careers page."""
    url_lower = url.lower()
    # /jobs/12345 or /jobs/job-title (specific job), not /jobs at root
    if re.search(r'/jobs/[^/]+', url_lower):
        return True
    if '/opening/' in url_lower or '/position/' in url_lower:
        return True
    # Job ID patterns (e.g. greenhouse/12345, lever/abc-123)
    if re.search(r'/\d{5,}', url_lower):
        return True
    if re.search(r'/[a-z0-9-]{20,}(?:/|$)', url_lower):
        return True
    return False


def run_discovery_query(client, ai_model, query, use_google_search):
    """Run a single discovery query. Returns list of companies or empty list on error."""
    prompt = f"""Search for tech companies hiring for: {query}

For each company you find, extract:
- Company name
- Direct careers page URL (not a job listing URL, the main careers/jobs page)
- Which job platform they use (Ashby/Greenhouse/Lever/own)

Return ONLY a JSON array, no other text:
[
  {{
    "name": "Company Name",
    "url": "https://company.com/careers",
    "platform": "ashby"
  }}
]

Rules:
- Only include companies with direct careers page URLs
- Do not include LinkedIn, Indeed, or job board URLs
- Only include companies that hire remotely in Europe/EMEA
- Return empty array [] if no relevant results found"""

    try:
        if use_google_search:
            response = client.models.generate_content(
                model=ai_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
        else:
            response = client.models.generate_content(
                model=ai_model,
                contents=prompt,
            )
        response_text = response.text.strip()
        companies = parse_json_response(response_text)
        if isinstance(companies, list):
            return companies
        return []
    except json.JSONDecodeError as e:
        print(f"    ⚠️ JSON parse error: {e}")
        return []
    except Exception as e:
        print(f"    ⚠️ Query failed: {e}")
        return []


def is_url_accessible(url, timeout=8):
    """Check if a URL returns a valid page (not 404 or error)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers,
                                timeout=timeout, allow_redirects=True)
        return response.status_code < 400
    except Exception:
        return False


def filter_new_companies(companies, known_urls, known_names):
    """Filter to only new companies not already in our list.
    Validates each URL is accessible before including."""
    new_companies = []
    seen_urls = set()

    for c in companies:
        if not isinstance(c, dict):
            continue
        name = c.get('name', '').strip()
        url = c.get('url', '').strip()

        if not name or not url:
            continue
        if not url.startswith('https://'):
            continue
        if name.lower() in known_names:
            continue

        url_normalized = url.rstrip('/').lower()
        if url_normalized in known_urls:
            continue
        if url_normalized in seen_urls:
            continue
        if is_job_listing_url(url):
            continue

        # Validate URL is actually accessible
        if not is_url_accessible(url):
            print(f"    ⚠️ Skipping inaccessible URL: {url}")
            continue

        seen_urls.add(url_normalized)
        new_companies.append({
            'name': name,
            'url': url,
            'platform': c.get('platform', ''),
        })

    return new_companies


def send_discord_discovery(new_companies, config):
    """Send discovery results to Discord as single message."""
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return False

    notification_channels = config.get('notification_channels', [])
    if 'discord' not in notification_channels:
        return False

    title = "🔍 Actually Remote — Discovery Run"
    body = f"Found {len(new_companies)} new companies to consider:\n\n"
    for c in new_companies:
        body += f"• {c['name']} — {c['url']}"
        if c.get('platform'):
            body += f" ({c['platform']})"
        body += "\n"
    body += "\nAdd them to companies.csv to start tracking."

    message = f"**{title}**\n\n{body}"

    try:
        requests.post(webhook_url, json={"content": message}, timeout=10)
        return True
    except Exception as e:
        print(f"    ⚠️ Discord notification failed: {e}")
        return False


def send_email_discovery(new_companies, config):
    """Send discovery results via email."""
    import resend

    notification_channels = config.get('notification_channels', [])
    if 'email' not in notification_channels:
        return False

    resend.api_key = os.getenv('RESEND_API_KEY')
    email_from = os.getenv('EMAIL_FROM', 'onboarding@resend.dev')
    email_to = os.getenv('EMAIL_TO')
    if not email_to:
        return False

    title = "🔍 Actually Remote — Discovery Run"
    body = f"Found {len(new_companies)} new companies to consider:\n\n"
    for c in new_companies:
        body += f"• {c['name']} — {c['url']}"
        if c.get('platform'):
            body += f" ({c['platform']})"
        body += "\n"
    body += "\nAdd them to companies.csv to start tracking."

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Actually Remote — Discovery</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
  <h2>{title}</h2>
  <p>Found {len(new_companies)} new companies to consider:</p>
  <ul>
"""
    for c in new_companies:
        platform = f" ({c['platform']})" if c.get('platform') else ""
        html += f'    <li><a href="{c["url"]}">{c["name"]}</a>{platform}</li>\n'
    html += """  </ul>
  <p>Add them to companies.csv to start tracking.</p>
</body>
</html>
"""

    try:
        resend.Emails.send({
            "from": email_from,
            "to": [email_to],
            "subject": f"Actually Remote — {len(new_companies)} new companies discovered",
            "html": html,
        })
        return True
    except Exception as e:
        print(f"    ⚠️ Email notification failed: {e}")
        return False


def send_telegram_discovery(new_companies, config):
    """Send discovery results to Telegram as single message."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        return False

    notification_channels = config.get('notification_channels', [])
    if 'telegram' not in notification_channels:
        return False

    title = "🔍 Actually Remote — Discovery Run"
    body = f"Found {len(new_companies)} new companies to consider:\n\n"
    for c in new_companies:
        body += f"• {c['name']} — {c['url']}"
        if c.get('platform'):
            body += f" ({c['platform']})"
        body += "\n"
    body += "\nAdd them to companies.csv to start tracking."

    message = f"**{title}**\n\n{body}"

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }, timeout=10)
        return True
    except Exception as e:
        print(f"    ⚠️ Telegram notification failed: {e}")
        return False


def main():
    print("🔍 Actually Remote — Company Discovery")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    config = load_config()
    companies = load_companies('companies.csv')
    known_urls = {c['url'].rstrip('/').lower() for c in companies}
    known_names = {c['name'].lower() for c in companies}

    print(f"Loaded {len(companies)} known companies")

    client = genai.Client()

    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    ai_model = config.get('ai_model', 'gemini-2.5-flash')

    queries = build_queries(config)
    print(f"Running {len(queries)} search queries...\n")

    use_google_search = True
    all_discoveries = []
    for i, query in enumerate(queries, 1):
        display_query = query[:60] + "..." if len(query) > 60 else query
        print(f"Query {i}/{len(queries)}: {display_query}")
        try:
            raw_companies = run_discovery_query(client, ai_model, query, use_google_search)
        except (TypeError, AttributeError):
            if use_google_search:
                use_google_search = False
                print("    (Google Search grounding not available, using standard generation)")
            raw_companies = run_discovery_query(client, ai_model, query, use_google_search)
        new_companies = filter_new_companies(raw_companies, known_urls, known_names)
        all_discoveries.extend(new_companies)
        print(f"  ✅ Found {len(new_companies)} new companies")

        # Update known sets to avoid duplicates across queries
        for c in new_companies:
            known_urls.add(c['url'].rstrip('/').lower())
            known_names.add(c['name'].lower())

    # Deduplicate by URL (same company might appear in multiple queries)
    seen = set()
    new_companies = []
    for c in all_discoveries:
        key = c['url'].rstrip('/').lower()
        if key not in seen:
            seen.add(key)
            new_companies.append(c)

    print(f"\n🎯 Total new discoveries: {len(new_companies)}")

    if not new_companies:
        print("No new companies discovered.")
        with open('discovery_results.txt', 'w', encoding='utf-8') as f:
            f.write(f"Discovery run: {datetime.now()}\n\n")
            f.write("No new companies found.\n")
        print("✅ Results saved to discovery_results.txt")
        return

    # Always print full list to terminal
    print("\nNew companies:")
    for c in new_companies:
        platform = f" ({c['platform']})" if c.get('platform') else ""
        print(f"  • {c['name']} — {c['url']}{platform}")

    print("\nSending notifications...")
    if send_discord_discovery(new_companies, config):
        print("✅ Discord notification sent")
    if send_email_discovery(new_companies, config):
        print("✅ Email notification sent")
    if send_telegram_discovery(new_companies, config):
        print("✅ Telegram notification sent")

    # Save to file
    with open('discovery_results.txt', 'w', encoding='utf-8') as f:
        f.write(f"Discovery run: {datetime.now()}\n\n")
        for c in new_companies:
            f.write(f"{c['name']},{c['url']}\n")

    print("\n✅ Results saved to discovery_results.txt")


if __name__ == "__main__":
    main()
