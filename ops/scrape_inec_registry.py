#!/usr/bin/env python3
"""
Scrape the full Nigerian polling-unit registry (states, LGAs, wards, PUs)
from cvr.inecnigeria.org's public cascade API.

Output: one JSON line per ward (checkpointed, resumable):
  {"state_id","state_code","state_name","lga_id","lga_code","lga_name",
   "ward_id","ward_code","ward_name","pus":[{"id","code","name"}]}

Usage: scrape_inec_registry.py <worker_idx> <worker_count>
Each worker takes every worker_count-th state, so multiple workers can run
in parallel over disjoint state sets.
"""
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://cvr.inecnigeria.org"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
OUT = os.path.expanduser("~/inec_registry.jsonl")
DELAY = 0.25  # seconds between requests per worker

worker_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
worker_count = int(sys.argv[2]) if len(sys.argv) > 2 else 1


def get(path, params, retries=6):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/html",
                "Referer": BASE + "/pu",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:
            wait = min(2 ** attempt, 30) + random.random()
            print(f"[w{worker_idx}] retry {attempt + 1}/{retries} ({e}) "
                  f"sleeping {wait:.1f}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"give up: {url}")


def options(resp):
    """Cascade APIs return [{"0": "--SELECT--", "selected": "0", "id": "label", ...}]"""
    d = resp[0] if isinstance(resp, list) and resp else (resp or {})
    return {int(k): v for k, v in d.items() if k not in ("0", "selected")}


def split_label(label):
    """'01 - AGUATA' -> ('01', 'AGUATA'); falls back to ('', label) if no prefix."""
    m = re.match(r"^\s*(\d+)\s*-\s*(.+?)\s*$", str(label))
    if m:
        return m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
    return "", re.sub(r"\s+", " ", str(label)).strip()


def done_wards():
    done = set()
    if os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["ward_id"])
                except Exception:
                    pass
    return done


def fetch_states():
    req = urllib.request.Request(BASE + "/pu", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'<select[^>]*id="SearchStateId".*?</select>', html, re.S)
    if not m:
        raise RuntimeError("state select not found on /pu page")
    return {int(v): n.strip() for v, n in
            re.findall(r'<option value="(\d+)"[^>]*>([^<]+)<', m.group(0))}


def main():
    states = fetch_states()
    finished = done_wards()
    print(f"[w{worker_idx}] {len(states)} states on site, "
          f"{len(finished)} wards already scraped", flush=True)

    out = open(OUT, "a", encoding="utf-8")
    for i, (state_id, state_label) in enumerate(sorted(states.items())):
        if i % worker_count != worker_idx:
            continue
        state_code, state_name = split_label(state_label)
        lg_as = options(get("/PublicApi/lgas/1/Search",
                            {"data[Search][state_id]": state_id}))
        print(f"[w{worker_idx}] state {state_name}: {len(lg_as)} LGAs", flush=True)
        time.sleep(DELAY)
        for lga_id, lga_label in sorted(lg_as.items()):
            lga_code, lga_name = split_label(lga_label)
            wards = options(get("/PublicApi/wards/1/Search",
                                {"data[Search][local_government_id]": lga_id}))
            time.sleep(DELAY)
            for ward_id, ward_label in sorted(wards.items()):
                if ward_id in finished:
                    continue
                ward_code, ward_name = split_label(ward_label)
                pus = options(get("/PublicApi/pus/1/Search",
                                  {"data[Search][registration_area_id]": ward_id}))
                time.sleep(DELAY)
                out.write(json.dumps({
                    "state_id": state_id, "state_code": state_code,
                    "state_name": state_name,
                    "lga_id": lga_id, "lga_code": lga_code, "lga_name": lga_name,
                    "ward_id": ward_id, "ward_code": ward_code,
                    "ward_name": ward_name,
                    "pus": [{"id": pid, "code": pcode, "name": pname}
                            for pid, (pcode, pname) in sorted(
                                (p, split_label(l)) for p, l in pus.items())],
                }) + "\n")
                out.flush()
                os.fsync(out.fileno())
        print(f"[w{worker_idx}] state {state_name} complete", flush=True)

    out.close()
    print(f"[w{worker_idx}] ALL DONE", flush=True)


if __name__ == "__main__":
    main()
