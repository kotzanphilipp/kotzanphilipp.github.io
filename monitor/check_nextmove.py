#!/usr/bin/env python3
"""Checks the nextmove Ueberfuehrungsfahrten page for changes.

Fetches the page, extracts the offer list ("Kostenlose Ueberfuehrungsfahrten"),
and compares it against the last stored snapshot.

Exit codes:
    0  no change
    1  content changed (unified diff on stdout)
    2  transient failure - network error or bot challenge (message on stderr)
    3  parse failure - the page loaded but no longer has the expected markers

Use --init to write the first snapshot without reporting a change.
"""

import difflib
import html
import os
import re
import sys
import time
import urllib.request

URL = "https://nextmove.de/ueberfuehrungsfahrten/"
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "snapshots", "nextmove-ueberfuehrungsfahrten.txt")

# The offer list sits between these two markers in the page text.
START_MARKER = "Kostenlose Überführungsfahrten"
END_MARKER = "Die allgemeinen Test Drives im Detail"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# The site sits behind a WAF that intermittently serves an interstitial instead
# of the page. Those responses are short and carry one of these phrases; they
# are a transient block, not a layout change.
CHALLENGE_PHRASES = (
    "your request is being verified",
    "one moment, please",
    "just a moment",
    "enable javascript and cookies to continue",
    "checking your browser",
)
# A real page run is ~97 KB; the interstitial is ~12 KB.
MIN_PAGE_BYTES = 40000

ATTEMPTS = 3
BACKOFF_SECONDS = 20


class Blocked(Exception):
    """The WAF served a challenge page instead of the content."""


def fetch_once(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    markup = raw.decode(resp.headers.get_content_charset() or "utf-8",
                        errors="replace")

    lowered = markup.lower()
    if any(phrase in lowered for phrase in CHALLENGE_PHRASES):
        raise Blocked("WAF interstitial served (%d bytes)" % len(raw))
    if len(raw) < MIN_PAGE_BYTES:
        raise Blocked("response too short to be the real page (%d bytes)"
                      % len(raw))
    return markup


def fetch(url):
    """Fetches with retries; raises the last error if every attempt fails."""
    last = None
    for attempt in range(ATTEMPTS):
        try:
            return fetch_once(url)
        except Exception as exc:  # noqa: BLE001 - retry on anything
            last = exc
            if attempt < ATTEMPTS - 1:
                time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise last


def visible_text(markup):
    markup = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", markup)
    markup = re.sub(r"(?s)<!--.*?-->", " ", markup)
    text = re.sub(r"(?s)<[^>]+>", "\n", markup)
    text = html.unescape(text)
    return [line.strip() for line in text.split("\n") if line.strip()]


def extract_offers(lines):
    """Returns the offer section, or None if the page layout no longer matches."""
    start = end = None
    for i, line in enumerate(lines):
        if start is None and START_MARKER in line:
            start = i
        elif start is not None and END_MARKER in line:
            end = i
            break
    if start is None or end is None:
        return None
    return lines[start:end]


def main():
    init = "--init" in sys.argv

    try:
        markup = fetch(URL)
    except Blocked as exc:
        print("BLOCKED: %s - transient, will retry next run" % exc,
              file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - any failure is a fetch failure
        print("FETCH FAILED: %s" % exc, file=sys.stderr)
        return 2

    section = extract_offers(visible_text(markup))
    if section is None:
        print("PARSE FAILED: page loaded but the offer section markers are "
              "gone - layout has changed, monitor needs updating",
              file=sys.stderr)
        return 3

    current = "\n".join(section) + "\n"

    if not os.path.exists(SNAPSHOT) or init:
        os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
        with open(SNAPSHOT, "w", encoding="utf-8") as fh:
            fh.write(current)
        print("Snapshot initialised (%d lines)." % len(section))
        return 0

    with open(SNAPSHOT, encoding="utf-8") as fh:
        previous = fh.read()

    if previous == current:
        print("No change.")
        return 0

    diff = difflib.unified_diff(
        previous.splitlines(keepends=True), current.splitlines(keepends=True),
        fromfile="previous", tofile="current", n=1)
    sys.stdout.write("".join(diff))

    with open(SNAPSHOT, "w", encoding="utf-8") as fh:
        fh.write(current)
    return 1


if __name__ == "__main__":
    sys.exit(main())
