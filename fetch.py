"""Fetch the CV Amsterdam programme for the next 10 days.

Weekdays: only screenings starting 18:00-20:00 (Amsterdam time).
Saturday/Sunday: all screenings of that cinema day (04:00 to 04:00).

Writes data/latest.json plus a dated copy. Standard library only.
"""

import json
import re
import sys
import urllib.request
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.cineville.nl/events/search"
TZ = ZoneInfo("Europe/Amsterdam")
CITY = "amsterdam"
DAYS = 10
WEEKDAY_FROM, WEEKDAY_TO = time(18, 0), time(20, 0)  # inclusive start-time window
DAY_START = time(4, 0)  # cinema day runs 04:00 -> 04:00
PAGE_LIMIT = 500
HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "locale": "nl-NL",
    "User-Agent": "personal-weekly-agenda/1.0 (one run per week)",
}


def utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def window_for(day):
    """Return (start, end, inclusive_end) in Amsterdam time for one day."""
    if day.weekday() >= 5:  # Saturday, Sunday: whole cinema day
        start = datetime.combine(day, DAY_START, TZ)
        end = datetime.combine(day + timedelta(days=1), DAY_START, TZ)
        return start, end, False
    return datetime.combine(day, WEEKDAY_FROM, TZ), datetime.combine(day, WEEKDAY_TO, TZ), True


def post(body):
    req = urllib.request.Request(API, data=json.dumps(body).encode(), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def fetch_day(day):
    start, end, inclusive = window_for(day)
    body = {
        "productionId": {"isNull": False},
        "startDate": {"gte": utc_iso(start), ("lte" if inclusive else "lt"): utc_iso(end)},
        "venue": {"collection": {"cities": {"in": [CITY]}}},
        "isHidden": {"eq": False},
        "embed": {"production": True, "venue": True},
        "sort": {"startDate": "asc"},
        "page": {"limit": PAGE_LIMIT},
    }
    data = post(body)
    events = (data.get("_embedded") or {}).get("events", [])
    total = data.get("totalCount", len(events))
    if total > len(events):
        raise RuntimeError(f"{day}: got {len(events)} of {total} events; raise PAGE_LIMIT")
    return events


def clean(text, limit=400):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"[_*]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def strip_tracking(url):
    """Drop utm_* tracking parameters from a ticket link."""
    if not url:
        return url
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit(parts._replace(query=urlencode(query)))


def summarise(events_by_day):
    films = {}
    for day, events in events_by_day.items():
        for e in events:
            emb = e.get("_embedded") or {}
            p, v = emb.get("production") or {}, emb.get("venue") or {}
            attrs = p.get("attributes") or {}
            loc = p.get("localizableAttributes") or {}
            pid = p.get("id") or e.get("productionId")
            film = films.setdefault(pid, {
                "title": p.get("title") or (e.get("productionHint") or {}).get("title"),
                "slug": p.get("slug"),
                "year": attrs.get("releaseYear"),
                "directors": attrs.get("directors") or [],
                "cast": (attrs.get("cast") or [])[:4],
                "duration": attrs.get("duration"),
                "languages": attrs.get("spokenLanguages") or [],
                "description": clean(loc.get("shortDescription") or loc.get("description")),
                "tags": set(),
                "screenings": [],
            })
            tags = (e.get("attributes") or {}).get("tags") or []
            film["tags"].update(tags)
            start = datetime.fromisoformat(e["startDate"].replace("Z", "+00:00")).astimezone(TZ)
            film["screenings"].append({
                "cinema_day": day.isoformat(),
                "start": start.strftime("%Y-%m-%d %H:%M"),
                "weekday": start.strftime("%a"),
                "venue": v.get("name"),
                "subtitles": (e.get("attributes") or {}).get("subtitles") or [],
                "tags": tags,
                "tickets": strip_tracking(e.get("ticketingUrl")),
            })
    out = []
    for f in films.values():
        f["tags"] = sorted(f["tags"])
        f["screenings"].sort(key=lambda s: s["start"])
        out.append(f)
    out.sort(key=lambda f: (f["title"] or "").lower())
    return out


def main():
    today = datetime.now(TZ).date()
    if len(sys.argv) > 1:
        today = date.fromisoformat(sys.argv[1])
    days = [today + timedelta(days=i) for i in range(DAYS)]
    events_by_day = {d: fetch_day(d) for d in days}
    films = summarise(events_by_day)
    result = {
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "city": CITY,
        "from": days[0].isoformat(),
        "to": days[-1].isoformat(),
        "rules": "weekdays: start 18:00-20:00; Sat/Sun: whole day (04:00-04:00); Amsterdam time",
        "screenings_per_day": {d.isoformat(): len(ev) for d, ev in events_by_day.items()},
        "film_count": len(films),
        "films": films,
    }
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    (out_dir / "latest.json").write_text(text, encoding="utf-8")
    (out_dir / f"{today.isoformat()}.json").write_text(text, encoding="utf-8")
    print(f"{len(films)} films, per day: {result['screenings_per_day']}")


if __name__ == "__main__":
    main()
