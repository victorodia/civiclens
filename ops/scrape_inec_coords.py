#!/usr/bin/env python3
"""
Scrape per-polling-unit GPS coordinates from cvr.inecnigeria.org.

The /pu form POSTs to /pu_locator/index, which 302-redirects to Google Maps:
  - with coordinates when INEC has them:  ?q=5.9678,7.1245
  - with the address text otherwise:     ?q=VILLAGE SQUARE, ..., AKWA IBOM

Reads ~/inec_registry.jsonl (produced by scrape_inec_registry.py) and writes
~/inec_coords.jsonl, one line per PU:
  {"pu_id": 8261, "lat": 5.9678, "lng": 7.1245}
or
  {"pu_id": 5284, "address_only": "VILLAGE SQUARE, IKOT AKWA EBOM, ABAK..."}

Resumable: PUs already present in the output file are skipped.

Usage: scrape_inec_coords.py <worker_idx> <worker_count>
"""
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cvr.inecnigeria.org"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
REG = os.path.expanduser("~/inec_registry.jsonl")
OUT = os.path.expanduser("~/inec_coords.jsonl")
DELAY = 0.3

worker_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
worker_count = int(sys.argv[2]) if len(sys.argv) > 2 else 1

COORD_RE = re.compile(r"^q=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)(?:&|$)")


def locate(state_id, lga_id, ward_id, pu_id, retries=6):
    body = urllib.parse.urlencode({
        "data[Search][state_id]": state_id,
        "data[Search][local_government_id]": lga_id,
        "data[Search][registration_area_id]": ward_id,
        "data[Search][polling_unit_id]": pu_id,
    }).encode()
    for attempt in range(retries):
        try:
            req = urllib.request.Request(BASE + "/pu_locator/index", data=body,
                                         headers={"User-Agent": UA,
                                                  "Referer": BASE + "/pu",
                                                  "Content-Type": "application/x-www-form-urlencoded"})
            # We WANT the 302, not the followed redirect.
            opener = urllib.request.build_opener(NoRedirect())
            try:
                opener.open(req, timeout=30)
                return None  # no Location? treat as miss
            except urllib.error.HTTPError as e:
                if e.code in (301, 302, 303, 307, 308):
                    return e.headers.get("Location", "")
                if 400 <= e.code < 500:
                    return None  # client error: retrying won't help
                raise  # 5xx etc.: fall into the retry loop below
        except Exception as e:
            wait = min(2 ** attempt, 30) + random.random()
            print(f"[w{worker_idx}] retry {attempt + 1}/{retries} ({e}) "
                  f"sleep {wait:.1f}s", flush=True)
            time.sleep(wait)
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["pu_id"])
                except Exception:
                    pass
    print(f"[w{worker_idx}] {len(done)} PUs already have coordinates", flush=True)

    out = open(OUT, "a", encoding="utf-8")
    n_new = 0
    for i, line in enumerate(open(REG, encoding="utf-8")):
        if i % worker_count != worker_idx:
            continue
        try:
            ward = json.loads(line)
        except json.JSONDecodeError:
            continue  # torn line: registry file is still being appended
        for pu in ward["pus"]:
            if pu["id"] in done:
                continue
            loc = locate(ward["state_id"], ward["lga_id"],
                         ward["ward_id"], pu["id"])
            time.sleep(DELAY)
            if not loc:
                rec = {"pu_id": pu["id"], "error": True}
            else:
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query).get("q", [""])[0]
                m = COORD_RE.match("q=" + q) if q else None
                if m:
                    rec = {"pu_id": pu["id"], "lat": float(m.group(1)),
                           "lng": float(m.group(2))}
                else:
                    rec = {"pu_id": pu["id"], "address_only": q}
            out.write(json.dumps(rec) + "\n")
            n_new += 1
            if n_new % 50 == 0:
                out.flush()
                os.fsync(out.fileno())
                print(f"[w{worker_idx}] {n_new} new lookups this session "
                      f"(last: pu {pu['id']})", flush=True)
    out.close()
    print(f"[w{worker_idx}] ALL DONE", flush=True)


if __name__ == "__main__":
    main()
