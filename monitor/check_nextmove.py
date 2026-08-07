#!/usr/bin/env python3
"""Checks the nextmove Ueberfuehrungsfahrten page for changes.

Fetches the page, extracts the offer list ("Kostenlose Ueberfuehrungsfahrten"),
and compares it against the last stored snapshot.

Exit codes:
    0  no change
    1  content changed (unified diff on stdout)
    2  fetch or parse failure (message on stderr)

Use --init to write the first snapshot without reporting a change.
"""

import difflib
import html
import os
import re
import sys
import urllib.request

URL = "https://nextmove.de/ueberfuehrungsfahrten/"
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "snapshots", "nextmove-ueberfuehrungsfahrten.txt")

# The offer list sits between these two markers in the page text.
START_MARKER = "Kostenlose Überführungsfahrten"
END_MARKER = "Die allgemeinen Test Drives im Detail"

USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": "de-DE,de;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    return raw.decode(resp.headers.get_content_charset() or "utf-8",
                      errors="replace")


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
    except Exception as exc:  # noqa: BLE001 - any failure is a fetch failure
        print("FETCH FAILED: %s" % exc, file=sys.stderr)
        return 2

    section = extract_offers(visible_text(markup))
    if section is None:
        print("PARSE FAILED: offer section markers not found - page layout "
              "may have changed", file=sys.stderr)
        return 2

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
