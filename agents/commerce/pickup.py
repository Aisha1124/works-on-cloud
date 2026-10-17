"""Which pickup times a shop can take, in Singapore time.

A pickup time is valid when the shop is not paused, it is at least min_notice_hours away,
the shop is open then, and that day is not full (daily_capacity). The shop page only offers
valid 30-minute slots; agents that send an invalid time get the reason and the next slots.

Shops whose hours text can't be read are treated as open 9am-6pm every day.
"""

from datetime import date, datetime, time, timedelta

from agents.risk.scorer import is_open, parse_hours
from backend.models import OrderStatus, Shop
from backend.store.base import Store
from backend.timeutil import SGT, now_sg, to_sg

STEP = timedelta(minutes=30)
HORIZON_DAYS = 60  # how far ahead next_slots looks
DEFAULT_HOURS = {d: [(9 * 60, 18 * 60)] for d in range(7)}
NOT_COUNTED = {OrderStatus.rejected, OrderStatus.cancelled}


def shop_hours(shop: Shop) -> dict[int, list[tuple[int, int]]]:
    """{weekday: [(open_min, close_min)]}; 9am-6pm daily when the hours can't be read."""
    return (parse_hours(shop.hours) if shop.hours.strip() else None) or DEFAULT_HOURS


def hours_readable(shop: Shop) -> bool:
    return bool(shop.hours.strip()) and parse_hours(shop.hours) is not None


def fmt_day(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b %Y}"


def fmt_time(dt: datetime) -> str:
    return f"{to_sg(dt):%a} {to_sg(dt).day} {to_sg(dt):%b %H:%M}"


def paused_message(shop: Shop, now: datetime | None = None) -> str:
    """'Not taking orders until Mon 26 Oct 2026.' while paused, else ''."""
    today = to_sg(now or now_sg()).date()
    if shop.paused_until and today < shop.paused_until:
        return f"Not taking orders until {fmt_day(shop.paused_until)}."
    return ""


def _counts(store: Store, shop: Shop) -> dict[date, int]:
    counts: dict[date, int] = {}
    if shop.daily_capacity is None:
        return counts
    for order in store.list_orders(shop.id):
        if order.status not in NOT_COUNTED:
            day = to_sg(order.pickup_at).date()
            counts[day] = counts.get(day, 0) + 1
    return counts


def _full(shop: Shop, counts: dict[date, int], day: date) -> bool:
    return shop.daily_capacity is not None and counts.get(day, 0) >= shop.daily_capacity


def _earliest(shop: Shop, now: datetime) -> datetime:
    return to_sg(now) + timedelta(hours=shop.min_notice_hours)


def pickup_problem(store: Store, shop: Shop, pickup: datetime, now: datetime | None = None,
                   counts: dict[date, int] | None = None) -> str | None:
    """Why the shop can't take a pickup at this time (one plain sentence), or None."""
    now = to_sg(now or now_sg())
    pickup = to_sg(pickup)
    paused = paused_message(shop, now)
    if paused:
        return f"{shop.name} is {paused[0].lower()}{paused[1:]}"
    if pickup <= now:
        return "The pickup time must be in the future (Singapore time)."
    if pickup < _earliest(shop, now):
        return (f"This shop needs {shop.min_notice_hours} hours' notice, so the earliest pickup "
                f"is {fmt_time(_earliest(shop, now))}.")
    if not is_open(shop_hours(shop), pickup):
        hours = shop.hours.strip() if hours_readable(shop) else "9am-6pm daily"
        return f"The shop is closed at {fmt_time(pickup)}. Opening hours: {hours}."
    counts = _counts(store, shop) if counts is None else counts
    if _full(shop, counts, pickup.date()):
        return f"The shop is fully booked on {fmt_day(pickup.date())}. Please pick another day."
    return None


def _day_slots(shop: Shop, day: date, earliest: datetime) -> list[datetime]:
    hours = shop_hours(shop)
    out = []
    t = datetime.combine(day, time(0, 0), tzinfo=SGT)
    end = t + timedelta(days=1)
    while t < end:
        if t >= earliest and is_open(hours, t):
            out.append(t)
        t += STEP
    return out


def next_slots(store: Store, shop: Shop, now: datetime | None = None,
               after: datetime | None = None, n: int = 3) -> list[datetime]:
    """The next n valid pickup times, starting at the requested time if that is later than the
    earliest allowed one (so an agent gets alternatives near what it asked for), else from now.
    Empty while the shop is paused."""
    now = to_sg(now or now_sg())
    if paused_message(shop, now):
        return []
    counts = _counts(store, shop)
    earliest = _earliest(shop, now)

    def scan(start: datetime) -> list[datetime]:
        found: list[datetime] = []
        day = start.date()
        while len(found) < n and day <= now.date() + timedelta(days=HORIZON_DAYS):
            if not _full(shop, counts, day):
                found += _day_slots(shop, day, start)[: n - len(found)]
            day += timedelta(days=1)
        return found

    start = max(earliest, to_sg(after)) if after else earliest
    return scan(start) or (scan(earliest) if start != earliest else [])


def available_days(store: Store, shop: Shop, now: datetime | None = None,
                   days: int = 14) -> list[dict]:
    """For the shop page: [{date, label, times: [{value, label}]}] for the next `days` days
    that have at least one free slot."""
    now = to_sg(now or now_sg())
    if paused_message(shop, now):
        return []
    counts = _counts(store, shop)
    earliest = _earliest(shop, now)
    out = []
    for i in range(HORIZON_DAYS + 1):  # stops once `days` days with free slots are found
        day = now.date() + timedelta(days=i)
        if _full(shop, counts, day):
            continue
        slots = _day_slots(shop, day, earliest)
        if slots:
            out.append({"date": day.isoformat(), "label": f"{day:%a} {day.day} {day:%b}",
                        "times": [{"value": s.strftime("%Y-%m-%dT%H:%M"),
                                   "label": s.strftime("%H:%M")} for s in slots]})
        if len(out) >= days:
            break
    return out


def iso(dt: datetime) -> str:
    return to_sg(dt).strftime("%Y-%m-%dT%H:%M")


# --- Opening hours as a weekly table (owner settings) ---------------------------------------

DAY_ABBR = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _hhmm(minutes: int) -> str:
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _ampm(minutes: int) -> str:
    """540 -> '9am', 570 -> '9:30am', 720 -> '12pm', 0 -> '12am'."""
    minutes %= 24 * 60
    h, m = divmod(minutes, 60)
    suffix = "am" if h < 12 else "pm"
    h = h % 12 or 12
    return f"{h}{f':{m:02d}' if m else ''}{suffix}"


def week_table(shop: Shop) -> list[dict]:
    """[{day, closed, open, close}] for Mon..Sun ("HH:MM"), the first range of each day. Uses
    the 9am-6pm default when the hours can't be read."""
    hours = shop_hours(shop)
    out = []
    for day in range(7):
        ranges = hours[day]
        if ranges:
            start, end = ranges[0]
            out.append({"day": day, "closed": False, "open": _hhmm(start), "close": _hhmm(end)})
        else:
            out.append({"day": day, "closed": True, "open": "09:00", "close": "18:00"})
    return out


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def format_week(table: list[dict]) -> str:
    """The weekly table as hours text the rest of the app reads (parse_hours), with
    neighbouring days that have the same hours grouped: 'Mon closed; Tue-Sun 9am-6pm'."""
    by_day = {row["day"]: row for row in table}
    specs = []
    for day in range(7):
        row = by_day.get(day, {"closed": True})
        specs.append("closed" if row["closed"] else
                     f"{_ampm(_minutes(row['open']))}-{_ampm(_minutes(row['close']))}")
    parts, start = [], 0
    for day in range(1, 8):
        if day == 7 or specs[day] != specs[start]:
            days = DAY_ABBR[start] if day - 1 == start else f"{DAY_ABBR[start]}-{DAY_ABBR[day - 1]}"
            parts.append(f"{days} {specs[start]}")
            start = day
    return "; ".join(parts)
