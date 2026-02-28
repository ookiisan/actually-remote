# Contributing to Actually Remote

First off, thank you! **Actually Remote** grows through community contributions,
and the company list is only as good as the people maintaining it.

---

## Ways to contribute

- **Add a company** — submit a PR to add a remote-friendly company to `companies.csv`
- **Report a broken URL** — open an issue if a career page has moved or stopped working
- **Report a bug** — something in the scraper or matching isn't behaving correctly
- **Suggest a feature** — ideas for improving the tool

---

## Adding a company to `companies.csv`

This is the most valuable contribution you can make.

### Requirements

A company belongs in `companies.csv` if:
- It is a tech company (software, SaaS, devtools, fintech, data, infra, etc.)
- It has a **direct, public careers page** (no login required to view jobs)
- It genuinely hires outside the US and/or UK
- Its `remote_policy` is `global`, `emea`, or `eu`

A company does **not** belong if:
- It only hires in the US or requires US work authorization
- It uses a generic job board link with no company-specific careers page
- Its careers page requires login to view listings
- It is a staffing agency, recruiter, or job board itself

### Format

Add your entry to `companies.csv` following this format:

|     name     |             url             | priority | category | hq_country | remote_policy |
| ------------ | --------------------------- | -------- | -------- | ---------- | ------------- |
| Company Name | https://company.com/careers |   false  |   saas   |     NL     |     global    |


**Required fields:**
- `name` — company name
- `url` — direct link to the careers/jobs page (not the homepage)
- `priority` — always `false` for new contributions (users set their own priorities)

**Optional but appreciated:**
- `category` — one of: `fintech`, `saas`, `devtools`, `infra`, `data`, `other`
- `hq_country` — ISO country code of headquarters (e.g. `DE`, `NL`, `SE`, `FR`)
- `remote_policy` — one of: `global`, `emea`, `eu`, `country-specific`

### Before submitting

Please verify your URL works by visiting it directly in a browser and confirming
it shows actual job listings (not a homepage, blog, or 404).

The `validate_companies.yml` GitHub Action will automatically run a dry-run check
on your URL when you open a PR. If it fails, check the URL and try again.

### Submitting

1. Fork the repo
2. Add your company entry to `companies.csv`
3. Open a PR with the title: `add: Company Name`
4. The automated URL validation will run — fix any issues if it fails

---

## Reporting a broken URL

Open an issue using the **Broken URL** template. Include:
- The company name
- The current (broken) URL
- The correct URL if you know it

---

## Reporting a bug

Open an issue using the **Bug Report** template. The more detail the better —
include your Python version, OS, and any error messages from the logs.

---

## Code contributions

If you want to contribute code improvements:

1. Open an issue first to discuss what you want to change
2. Fork the repo and create a branch: `git checkout -b feat/your-feature`
3. Make your changes with clear commit messages
4. Open a PR describing what you changed and why

Please keep PRs focused — one feature or fix per PR makes reviewing much easier.

---

## Questions?

Open a discussion or an issue — happy to help.
