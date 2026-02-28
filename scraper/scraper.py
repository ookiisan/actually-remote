import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin


def load_companies(filepath='companies.csv'):
    """Load companies from CSV. Columns: name, url, priority, category, hq_country, remote_policy.
    priority is stored as 'true'/'false' string — converted to boolean."""
    companies = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            priority = row.get('priority', 'false').lower() == 'true'
            companies.append({
                'name': row['name'],
                'url': row['url'],
                'priority': priority,
                'category': row.get('category', ''),
                'hq_country': row.get('hq_country', ''),
                'remote_policy': row.get('remote_policy', ''),
            })
    return companies


def validate_urls(companies):
    """Dry-run mode: validate each company URL, no AI, no notifications.
    Prints each found job with title and URL so you can verify results before AI runs."""
    print("--- 🧪 Dry Run: Validating URLs ---")
    for company in companies:
        scrape_careers_page(company['url'], company['name'], verbose=True)
    print("\n" + "=" * 30)
    print("✅ URL validation complete")
    print("=" * 30)


def matches_any(text, keyword_list):
    """Helper to check if any keyword exists in text (case-insensitive)"""
    if not text:
        return False
    text_lower = text.lower()
    return any(k.lower() in text_lower for k in keyword_list)


def scrape_careers_page(url, company_name, verbose=False, role_keywords=None):
    """Scrape a careers page and extract job listings.
    If verbose=True, prints each job with title and URL (for dry-run validation).
    role_keywords: list of role terms to match (e.g. from config target_titles)."""
    if role_keywords is None:
        role_keywords = [
            "engineer", "developer", "architect", "specialist", "manager", "support",
            "solutions", "solution", "customer", "forward", "deployed", "integration",
            "EMEA", "Europe"
        ]
    print(f"\n🔍 Scraping {company_name}...")

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        # Reduce timeout slightly to keep loop moving
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        jobs = []

        for link in soup.find_all('a', href=True):
            if link.find_parent(['nav', 'footer', 'header']):
                continue

            href = link.get('href').strip()
            if not href: continue

            href = urljoin(url, href)
            href_lower = href.lower()

            # 1. HARD BLOCKS
            if any(skip in href_lower for skip in [
                '/blog', '/privacy', '/terms', '/cookies', '/about', '/press',
                '/docs', '/integrations', '/customers', 'juraj.blog', 'mailto:',
                'twitter.com', 'linkedin.com', 'facebook.com', 'javascript:'
            ]):
                continue

            # 2. CLEAN TEXT
            text = " ".join(link.get_text().split())
            text_lower = text.lower()

            # 3. JOB-ONLY KEYWORDS (role_keywords param)
            # 4. FILTERING LOGIC
            is_job_portal = any(p in href_lower for p in ['greenhouse.io', 'lever.co', 'ashbyhq.com', 'workable.com'])
            has_job_path = any(p in href_lower for p in ['/job', '/career', '/opening', '/position'])
            has_strict_role = any(role.lower() in text_lower for role in role_keywords)

            if is_job_portal or (has_job_path and has_strict_role) or ('#' in href and has_strict_role):
                if len(text.split()) > 7 or len(text) < 8:
                    continue

                if href.rstrip('/') == url.rstrip('/') or text_lower in ['engineering', 'careers', 'view jobs', 'all jobs']:
                    continue

                if not any(j['url'] == href for j in jobs):
                    jobs.append({
                        'title': text,
                        'url': href,
                        'company': company_name
                    })

        if verbose:
            for i, job in enumerate(jobs, 1):
                print(f"    [{i}] {job['title']} — {job['url']}")
            print(f"    Found {len(jobs)} items")
        else:
            print(f"    Found {len(jobs)} potential job matches")
        return jobs

    except Exception as e:
        print(f"    ❌ Error: {str(e)}")
        return []


def fetch_job_description(job_url):
    """Fetch full job description from URL"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        response = requests.get(job_url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        for script in soup(["script", "style", "nav", "header", "footer"]):
            script.decompose()

        text = soup.get_text(separator='\n')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned_text = '\n'.join(lines)
        return cleaned_text[:3000]
    except Exception as e:
        print(f"    ⚠️ Could not fetch full JD: {str(e)}")
        return None
