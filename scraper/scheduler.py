"""
Batch rotation scheduler — determines which companies to scrape on each run.
Priority companies run every day. Others rotate on a 7-day cycle.
"""
from datetime import datetime


def get_todays_companies(all_companies):
    """Return the batch of companies to process today.
    Priority companies run every day. Regular companies rotate on a 7-day cycle."""
    day_of_week = datetime.now().weekday()

    priority_companies = [c for c in all_companies if c.get('priority')]
    regular_companies = [c for c in all_companies if not c.get('priority')]

    num_regular = len(regular_companies)
    if num_regular > 0:
        batch_size = max(1, num_regular // 7)
        start_idx = day_of_week * batch_size

        if day_of_week == 6:
            todays_batch = regular_companies[start_idx:]
        else:
            todays_batch = regular_companies[start_idx: start_idx + batch_size]
    else:
        todays_batch = []

    return priority_companies + todays_batch
