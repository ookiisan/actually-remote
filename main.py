"""
Actually Remote — Entry point.
Handles --dry-run, --test, and normal scheduled run modes.
"""
import json
import os
import time
from datetime import datetime

import yaml
from dotenv import load_dotenv
import google.generativeai as genai
import requests

from ai.provider import analyze_job_fit, mock_analyze_job_fit
from scraper.scraper import (
    load_companies,
    validate_urls,
    scrape_careers_page,
    fetch_job_description,
    matches_any,
)
from scraper.scheduler import get_todays_companies

load_dotenv()

# Config and secrets loaded in main() when needed (not for --dry-run)
MIN_FIT_SCORE = 7
PRIORITY_MIN_FIT_SCORE = 6
TARGET_TITLES = []
LOCATION_KEYWORDS = []
GEMINI_API_KEY = None
DISCORD_WEBHOOK_URL = None
model = None


def _load_config():
    """Load config.yaml and .env secrets. Called when running full pipeline."""
    global MIN_FIT_SCORE, PRIORITY_MIN_FIT_SCORE, TARGET_TITLES, LOCATION_KEYWORDS
    global GEMINI_API_KEY, DISCORD_WEBHOOK_URL, model

    with open('config.yaml', 'r', encoding='utf-8') as f:
        _config = yaml.safe_load(f)

    MIN_FIT_SCORE = _config.get('min_fit_score', 7)
    PRIORITY_MIN_FIT_SCORE = _config.get('priority_min_fit_score', 6)
    TARGET_TITLES = _config.get('target_titles', ['Backend Engineer', 'Frontend Engineer'])
    LOCATION_KEYWORDS = _config.get('location_keywords', ['Remote', 'EMEA', 'Europe', 'Global', 'Worldwide'])

    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK_URL')

    genai.configure(api_key=GEMINI_API_KEY)
    ai_model = _config.get('ai_model', 'models/gemini-flash-latest')
    model = genai.GenerativeModel(f'models/{ai_model}')


def load_json(filepath):
    """Load JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {} if filepath == 'seen_jobs.json' else []


def save_json(filepath, data):
    """Save JSON file"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_cv():
    """Load CV text from cv.txt"""
    with open('cv.txt', 'r', encoding='utf-8') as f:
        return f.read()


def send_discord_alert(job, fit_analysis, is_priority):
    """Send simplified alert to Discord"""
    if not DISCORD_WEBHOOK_URL:
        print(f"    ⚠️ Discord webhook not configured, skipping alert")
        return

    fit_score = fit_analysis['fit_score']
    if fit_score >= 8:
        color = 3066993  # Green
        emoji = "🔥"
    elif fit_score >= 7:
        color = 15844367  # Gold
        emoji = "✨"
    else:
        color = 10181046  # Purple
        emoji = "💡"

    priority_tag = " [PRIORITY]" if is_priority else ""
    reasons_for = "\n".join([f"• {r}" for r in fit_analysis['reasons_for'][:2]])
    reasons_against = fit_analysis['reasons_against'][0] if fit_analysis['reasons_against'] else "None"

    message = {
        "content": f"{emoji} **{fit_score}/10{priority_tag}** - {fit_analysis['recommendation']}",
        "embeds": [{
            "title": job['title'],
            "url": job['url'],
            "description": f"**{job['company']}**",
            "color": color,
            "fields": [
                {"name": "✅ Good Fit", "value": reasons_for[:500], "inline": False},
                {"name": "⚠️ Gap", "value": reasons_against[:200], "inline": False}
            ]
        }]
    }

    try:
        requests.post(DISCORD_WEBHOOK_URL, json=message, timeout=10)
        print(f"    ✅ Discord alert sent for {job['company']}")
    except Exception as e:
        print(f"    ❌ Failed to send Discord alert: {str(e)}")


def run_pipeline(companies_to_run, cv_text, dry_run=False):
    """Run the full job scraping and analysis pipeline."""
    seen_jobs = load_json('seen_jobs.json')
    new_jobs_found = 0
    alerts_sent = 0
    max_alerts = 5 if dry_run else None

    for company in companies_to_run:
        name, url = company['name'], company['url']
        is_priority = company.get('priority', False)
        jobs = scrape_careers_page(url, name)

        for job in jobs:
            job_url = job['url']
            if job_url in seen_jobs:
                continue

            if not matches_any(job['title'], TARGET_TITLES):
                continue

            new_jobs_found += 1
            print(f"\n    🆕 Potential Match: {job['title']}")

            job_description = fetch_job_description(job_url)
            if not job_description:
                seen_jobs[job_url] = {'status': 'failed_jd_fetch', 'title': job['title']}
                continue

            loc_in_title = matches_any(job['title'], LOCATION_KEYWORDS)
            loc_in_desc = matches_any(job_description, LOCATION_KEYWORDS)

            if not (loc_in_title or loc_in_desc):
                print(f"    ⏩ Skipping: Location mismatch")
                seen_jobs[job_url] = {'status': 'skipped_location', 'title': job['title']}
                continue

            try:
                print(f"    🤔 Analyzing fit with AI...")
                if dry_run:
                    fit_analysis = mock_analyze_job_fit(job['title'], job_description, cv_text)
                else:
                    fit_analysis = analyze_job_fit(model, job['title'], job_description, cv_text)

                if not fit_analysis:
                    seen_jobs[job_url] = {'status': 'ai_failed', 'title': job['title']}
                    continue

                fit_score = fit_analysis['fit_score']
                threshold = PRIORITY_MIN_FIT_SCORE if is_priority else MIN_FIT_SCORE
                should_alert = fit_score >= threshold

                seen_jobs[job_url] = {
                    'first_seen': datetime.now().isoformat(),
                    'company': name,
                    'title': job['title'],
                    'fit_score': fit_score,
                    'alerted': should_alert
                }

                if should_alert:
                    if max_alerts and alerts_sent >= max_alerts:
                        print(f"    ⏭️ Reached max alerts ({max_alerts}). Stopping.")
                        break
                    send_discord_alert(job, fit_analysis, is_priority)
                    alerts_sent += 1
                else:
                    print(f"    ⏭️  Skipped (Score {fit_score} < {threshold})")

            except Exception as e:
                error_msg = str(e).lower()
                print(f"    ⚠️ AI Analysis failed for {job['title']}: {str(e)}")

                if "429" in error_msg or "quota" in error_msg or "limit" in error_msg:
                    print("    🛑 API Quota reached. Saving progress and stopping for today.")
                    break
                continue

            time.sleep(2 if dry_run else 5)

    summary_msg = (
        f"📊 **Daily Scraper Report**\n"
        f"✅ Companies checked: {len(companies_to_run)}\n"
        f"✨ Matches found: {new_jobs_found}\n"
        f"🔔 Alerts sent: {alerts_sent}"
    )

    if alerts_sent == 0 and DISCORD_WEBHOOK_URL:
        try:
            requests.post(DISCORD_WEBHOOK_URL, json={
                "content": summary_msg + "\n☕ *No matches today.*"
            })
        except Exception as e:
            print(f"Could not send summary: {e}")
    else:
        print(summary_msg)

    save_json('seen_jobs.json', seen_jobs)
    print("\n" + "=" * 60)
    print(f"✅ COMPLETE | New Found: {new_jobs_found} | Alerts Sent: {alerts_sent}")
    print("=" * 60)


def main():
    import sys

    all_companies = load_companies('companies.csv')
    day_of_week = datetime.now().weekday()
    priority_companies = [c for c in all_companies if c.get('priority')]

    if '--dry-run' in sys.argv:
        validate_urls(all_companies)
        return

    companies_to_run = get_todays_companies(all_companies)

    if '--test' in sys.argv:
        companies_to_run = companies_to_run[:5]
        print("=" * 60)
        print("🧪 TEST MODE — First 5 companies only")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
    else:
        print("=" * 60)
        print("🤖 JOB SCRAPER STARTING")
        print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)

    _load_config()

    print(f"\n📋 Total Database: {len(all_companies)} companies")
    print(f"📅 Schedule: Processing group {day_of_week + 1} of 7")
    print(
        f"🚀 Today's Queue: {len(companies_to_run)} companies ({len(priority_companies)} priority)")

    cv_text = load_cv()
    run_pipeline(companies_to_run, cv_text, dry_run='--test' in sys.argv)


if __name__ == "__main__":
    main()
