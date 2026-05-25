#!/usr/bin/env python3

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import html
import re
import uuid

import requests
from bs4 import BeautifulSoup
from dateutil import parser

TZ = ZoneInfo("America/Denver")

SYMPHONY_URLS = [
    "https://coloradosymphony.org/view-all-events/",
    "https://coloradosymphony.org/calendar/",
]

DAZZLE_URLS = [
    "https://www.dazzledenver.com/",
    "https://www.dazzledenver.com/live-music/touring-shows/",
]

DAZZLE_ARTISTS = [
    "Dave Corbus",
    "Nelson Rangell",
    "Dotsero",
]

DAZZLE_STYLE_TERMS = [
    "straight-ahead",
    "straight ahead",
    "bebop",
    "hard bop",
    "post-bop",
    "mainstream jazz",
    "jazz quartet",
    "jazz trio",
    "jazz quintet",
]

DAZZLE_NATIONAL_TERMS = [
    "national",
    "touring",
    "grammy",
    "internationally",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def clean(text):
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def esc(text):
    return (
        clean(text)
        .replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def fetch(url):
    response = requests.get(url, timeout=30, headers=HEADERS)
    response.raise_for_status()
    return response.text


def looks_like_event_text(text):
    return (
        len(text) > 25
        and re.search(
            r"\b(2026|2027|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|"
            r"\d{1,2}:\d{2}|AM|PM)\b",
            text,
            re.I,
        )
    )


def extract_candidate_blocks(url):
    soup = BeautifulSoup(fetch(url), "html.parser")
    blocks = []

    for tag in soup.find_all(["article", "li", "section", "div"]):
        text = clean(tag.get_text(" "))
        if looks_like_event_text(text):
            blocks.append(text)

    seen = set()
    unique = []

    for block in blocks:
        key = block[:250].lower()
        if key not in seen:
            seen.add(key)
            unique.append(block)

    return unique


def parse_event_datetime(text):
    try:
        dt = parser.parse(text, fuzzy=True, default=datetime.now(TZ))
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)

    return dt


def make_title(text):
    title = text[:140]
    title = re.sub(
        r"\b(Get Tickets|Buy Tickets|Tickets|View Event|Learn More)\b.*",
        "",
        title,
        flags=re.I,
    )
    return clean(title)[:120]


def block_matches_dazzle_filter(block):
    lower = block.lower()

    artist_match = any(
        artist.lower() in lower for artist in DAZZLE_ARTISTS
    )

    style_match = any(
        term.lower() in lower for term in DAZZLE_STYLE_TERMS
    )

    national_match = any(
        term.lower() in lower for term in DAZZLE_NATIONAL_TERMS
    )

    return artist_match or style_match or national_match



def find_symphony_events():
    events = []
    seen = set()

    url = "https://coloradosymphony.org/calendar/"
    soup = BeautifulSoup(fetch(url), "html.parser")

    lines = [clean(line) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]

    date_re = re.compile(
        r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
        r"(January|February|March|April|May|June|July|August|September|October|November|December) "
        r"(\d{1,2})$"
    )

    time_re = re.compile(r"^\d{1,2}:\d{2} (AM|PM)$", re.I)

    skip_titles = {
        "buy tickets",
        "calendar",
        "list view",
        "all events",
        "movie",
        "classics",
        "young professionals",
        "fundraising events",
        "summer",
        "spotlight",
        "family-friendly",
    }

    current_date = None
    pending_title = None

    for line in lines:
        if date_re.match(line):
            current_date = line
            pending_title = None
            continue

        # A bare day number means we have left the previous date cell.
        if re.match(r"^\d{1,2}$", line):
            current_date = None
            pending_title = None
            continue

        if not current_date:
            continue

        if time_re.match(line):
            if pending_title:
                try:
                    dt = parser.parse(f"{current_date} 2026 {line}", fuzzy=False)
                except Exception:
                    pending_title = None
                    continue

                dt = dt.replace(tzinfo=TZ)

                key = (pending_title.lower(), dt.isoformat())
                if key not in seen:
                    seen.add(key)
                    events.append(
                        {
                            "title": pending_title,
                            "start": dt,
                            "end": dt + timedelta(hours=2),
                            "location": "Boettcher Concert Hall, Denver, CO",
                            "description": f"Colorado Symphony. Source: {url}",
                            "url": url,
                            "source": "Colorado Symphony",
                        }
                    )

                pending_title = None

            continue

        if line.lower() in skip_titles:
            continue

        # Ignore very short noise lines.
        if len(line) < 4:
            continue

        # Treat the first non-noise line after a valid date as the event title.
        pending_title = line

    return events


def find_events(urls, source_name, location, filter_func=None):
    events = []
    seen = set()

    for url in urls:
        try:
            blocks = extract_candidate_blocks(url)
        except Exception as exc:
            print(f"Fetch failed for {url}: {exc}")
            continue

        for block in blocks:

            if filter_func and not filter_func(block):
                continue

            dt = parse_event_datetime(block)

            if not dt:
                continue

            title = make_title(block)

            key = (
                source_name.lower(),
                title.lower(),
                dt.isoformat(),
            )

            if key in seen:
                continue

            seen.add(key)

            events.append(
                {
                    "title": title,
                    "start": dt,
                    "end": dt + timedelta(hours=2),
                    "location": location,
                    "description": f"{source_name}. Source: {url}",
                    "url": url,
                    "source": source_name,
                }
            )

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

    for event in sorted(events, key=lambda e: e["start"]):

        uid = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                event["source"]
                + event["title"]
                + event["start"].isoformat(),
            )
        )

        start = event["start"].astimezone(TZ).strftime("%Y%m%dT%H%M%S")
        end = event["end"].astimezone(TZ).strftime("%Y%m%dT%H%M%S")

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID=America/Denver:{start}",
                f"DTEND;TZID=America/Denver:{end}",
                f"SUMMARY:{esc(event['title'])}",
                f"DESCRIPTION:{esc(event['description'])}",
                f"LOCATION:{esc(event['location'])}",
                f"URL:{event['url']}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    return "\n".join(lines) + "\n"


def main():

    symphony_events = find_symphony_events()

    dazzle_events = find_events(
        DAZZLE_URLS,
        "Dazzle Jazz",
        "Dazzle Denver, Denver, CO",
        filter_func=block_matches_dazzle_filter,
    )

    entertainment_events = (
        symphony_events + dazzle_events
    )

    with open(
        "colorado-symphony.ics",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            make_calendar(
                "Colorado Symphony",
                symphony_events,
            )
        )

    with open(
        "dazzle-jazz.ics",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            make_calendar(
                "Dazzle Jazz",
                dazzle_events,
            )
        )

    with open(
        "entertainment.ics",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            make_calendar(
                "Entertainment",
                entertainment_events,
            )
        )

    print(
        f"Wrote {len(symphony_events)} Symphony events"
    )

    print(
        f"Wrote {len(dazzle_events)} Dazzle events"
    )

    print(
        f"Wrote {len(entertainment_events)} Entertainment events"
    )


if __name__ == "__main__":
    main()

