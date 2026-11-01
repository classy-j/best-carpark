"""Singapore public holidays. Maintain annual dates from MOM's gazetted calendar.
2026: https://www.mom.gov.sg/newsroom/press-releases/2025/0616-public-holidays-for-2026
Dates include observed Monday substitutes. Update for future years before using future searches.
"""
from datetime import date

SG_PUBLIC_HOLIDAYS_2026 = frozenset(date.fromisoformat(day) for day in (
    "2026-01-01", "2026-02-17", "2026-02-18", "2026-03-21", "2026-04-03",
    "2026-05-01", "2026-05-27", "2026-05-31", "2026-06-01", "2026-08-09",
    "2026-08-10", "2026-11-08", "2026-11-09", "2026-12-25",
))


def sg_public_holidays():
    """Return confirmed 2026 dates only; do not assume another year's dates."""
    return SG_PUBLIC_HOLIDAYS_2026
