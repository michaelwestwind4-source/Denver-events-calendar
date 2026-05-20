#!/usr/bin/env python3
import re
import uuid
import html
import requests
from bs4 import BeautifulSoup
from dateutil import parser
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Denver")

SYMPHONY_URLS = [
    "https://coloradosymphony.org/view-all-events/",
    "https://coloradosymphony.org/calendar/",
]

DAZZLE_URLS = [
    "https://www.dazzledenver.com/",
    "https://www.dazzledenver.com/live-music/touring-shows/",
]

DAZZLE_INCLUDE_TERMS = [
    "straight-ahead",
    "straight ahead",
    "jazz",
    "dave corbus",
    "nelson rangell",
    "dotsero",
    "touring",
    "national",
]

def clean(s):
    return re.sub(r"\s+", " ", html.unescape(s or "")).strip()

def esc(s):
    return clean(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

def fetch(url):
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text

def find_events_from_page(url, source_name, location, filter_terms=None):
    soup = BeautifulSoup(fetch(url), "html.parser")
    text_blocks = []

    for tag in soup.find_all(["article", "li", "div", "section"]):
        txt = clean(tag.get_text(" "))
        if len(txt) > 20 and re.search(r"\b(2026|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{1,2}:\d{2})\b", txt, re.I):
            text_blocks.append(txt)

    events = []
    seen = set()

    for block in text_blocks:
        lower = block.lower()
        if filter_terms and not any(term in lower for term in filter_terms):
            continue

        try:
            dt = parser.parse(block, fuzzy=True, default=datetime.now(TZ))
        except Exception:
            continue

        if dt.year < datetime.now(TZ).year:
            continue

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)

        title = block[:110]
        title = re.sub(r"\b(Get Tickets|Buy Tickets|View Event|Learn More)\b.*", "", title, flags=re.I)
        title = clean(title)

        key = (title.lower(), dt.isoformat())
        if key in seen:
            continue
        seen.add(key)

        events.append({
            "title": title,
            "start": dt,
            "end": dt + timedelta(hours=2),
            "location": location,
            "description": f"Source: {url}",
            "url": url,
            "source": source_name,
        })

    return events

def make_calendar(name, events):
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Michael Westwind//{name}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{esc(name)}",
        "X-WR-TIMEZONE:America/Denver",
    ]

    for e in sorted(events, key=lambda x: x["start"]):
        uid = str(uuid.uuid5(uuid.NAMESPACE_URL, e["source"] + e["title"] + e["start"].isoformat()))
        start = e["start"].astimezone(TZ).strftime("%Y%m%dT%H%M%S")
        end = e["end"].astimezone(TZ).strftime("%Y%m%dT%H%M%S")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{now}",
            f"DTSTART;TZID=America/Denver:{start}",
            f"DTEND;TZID=America/Denver:{end}",
            f"SUMMARY:{esc(e['title'])}",
            f"DESCRIPTION:{esc(e['description'])}",
            f"LOCATION:{esc(e['location'])}",
            f"URL:{e['url']}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\n".join(lines) + "\n"

def main():
    symphony_events = []
    for url in SYMPHONY_URLS:
        try:
            symphony_events += find_events_from_page(
                url,
                "Colorado Symphony",
                "Boettcher Concert Hall, Denver, CO"
            )
        except Exception as ex:
            print(f"Symphony fetch failed for {url}: {ex}")

    dazzle_events = []
    for url in DAZZLE_URLS:
        try:
            dazzle_events += find_events_from_page(
                url,
                "Dazzle Jazz",
                "Dazzle Denver, Denver, CO",
                DAZZLE_INCLUDE_TERMS
            )
        except Exception as ex:
            print(f"Dazzle fetch failed for {url}: {ex}")

    if not symphony_events:
        symphony_events = [{
            "title": "Colorado Symphony calendar update found no events",
            "start": datetime.now(TZ) + timedelta(days=1),
            "end": datetime.now(TZ) + timedelta(days=1, hours=1),
            "location": "Denver, CO",
            "description": "The updater ran but found no parseable events.",
            "url": SYMPHONY_URLS[0],
            "source": "Colorado Symphony",
        }]

    if not dazzle_events:
        dazzle_events = [{
            "title": "Dazzle calendar update found no matching events",
            "start": datetime.now(TZ) + timedelta(days=1),
            "end": datetime.now(TZ) + timedelta(days=1, hours=1),
            "location": "Dazzle Denver, Denver, CO",
            "description": "The updater ran but found no matching filtered events.",
            "url": DAZZLE_URLS[0],
            "source": "Dazzle Jazz",
        }]

    with open("colorado-symphony.ics", "w", encoding="utf-8") as f:
        f.write(make_calendar("Colorado Symphony", symphony_events))

    with open("dazzle-jazz.ics", "w", encoding="utf-8") as f:
        f.write(make_calendar("Dazzle Jazz", dazzle_events))

    print(f"Wrote {len(symphony_events)} Symphony events")
    print(f"Wrote {len(dazzle_events)} Dazzle events")

if __name__ == "__main__":
    main()
