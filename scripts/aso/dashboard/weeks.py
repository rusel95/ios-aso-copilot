"""Monday weeks. A flow is shown for a week only once that week has closed."""
from __future__ import annotations

import datetime as dt


def monday(day: dt.date) -> dt.date:
    """The Monday of the week `day` falls in."""
    return day - dt.timedelta(days=day.weekday())


def closed(week_start: dt.date, as_of: dt.date) -> bool:
    """True from the Monday after the week: on its own Sunday the week is still being lived."""
    return week_start + dt.timedelta(days=6) < as_of
