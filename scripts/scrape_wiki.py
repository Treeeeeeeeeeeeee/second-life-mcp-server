#!/usr/bin/env python3
"""
scrape_wiki.py — Scrape the Second Life LSL wiki and write one JSON file
per function into data/functions/.

The wiki uses MediaWiki templates. Each function page has:
  ## Summary   — signature table, parameter table, description
  ## Caveats   — bullet list
  ## Examples  — <syntaxhighlight> blocks
  ## See Also  — events/functions lists
  ## Deep Notes / Signature — canonical signature line

Usage:
    python3 scripts/scrape_wiki.py --function llListen --dry-run
    python3 scripts/scrape_wiki.py --function llListen
    python3 scripts/scrape_wiki.py
    python3 scripts/scrape_wiki.py --overwrite

Dependencies:
    pip install requests beautifulsoup4 lxml
"""

import argparse
import json
import re
import time
import sys
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup, Tag, NavigableString
except ImportError:
    print("[error] Missing dependencies. Run:")
    print("        pip install requests beautifulsoup4 lxml")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT          = Path(__file__).resolve().parent.parent
FUNCTIONS_DIR = ROOT / "data" / "functions"
ERRORS_LOG    = ROOT / "data" / "scrape_errors.json"

# ── Wiki config ───────────────────────────────────────────────────────────────

WIKI_BASE       = "https://wiki.secondlife.com"
API_URL         = f"{WIKI_BASE}/w/api.php"
FUNCTION_URL    = f"{WIKI_BASE}/wiki/{{name}}"
REQUEST_DELAY   = 0.5
REQUEST_TIMEOUT = 15
HEADERS         = {"User-Agent": "lsl-mcp-scraper/1.0 (personal/educational tool)"}

LSL_TYPES = {"integer", "float", "string", "key", "vector", "rotation", "list", "void"}

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch(url: str, session: requests.Session) -> BeautifulSoup | None:
    try:
        r = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return BeautifulSoup(r.text, "lxml")
    except requests.RequestException as e:
        print(f"  [fetch error] {url}: {e}")
        return None

# ── Category crawl ────────────────────────────────────────────────────────────

def get_all_function_names(session: requests.Session) -> list[str]:
    names  = []
    params = {
        "action":      "query",
        "list":        "categorymembers",
        "cmtitle":     "Category:LSL_Functions",
        "cmlimit":     "500",
        "cmnamespace": "0",
        "format":      "json",
    }
    while True:
        try:
            r = session.get(API_URL, params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, json.JSONDecodeError) as e:
            print(f"[error] Category API failed: {e}")
            break

        for m in data.get("query", {}).get("categorymembers", []):
            title = m.get("title", "")
            if title.startswith("ll") or title.startswith("os"):
                names.append(title)

        if "continue" not in data:
            break
        params["cmcontinue"] = data["continue"]["cmcontinue"]
        time.sleep(REQUEST_DELAY)

    return sorted(set(names))

# ── Text helpers ──────────────────────────────────────────────────────────────

def tag_text(tag: Tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()

def find_heading_sibling_content(soup: BeautifulSoup, heading_text: str) -> list[Tag]:
    result = []
    for h in soup.find_all(["h2", "h3", "h4"]):
        if heading_text.lower() in h.get_text().lower():
            for sib in h.next_siblings:
                if isinstance(sib, NavigableString):
                    continue
                if sib.name in ("h2", "h3", "h4"):
                    break
                result.append(sib)
            break
    return result

# ── Feature request detection ─────────────────────────────────────────────────

def is_feature_request(soup: BeautifulSoup) -> bool:
    text = soup.get_text()
    if "LSL Feature Request" in text and "does not exist" in text:
        return True
    if re.search(r"//\s*function\s+\w+\s+\w+\s*\(", text):
        return True
    return False

# ── Signature parsing ─────────────────────────────────────────────────────────

def parse_summary(soup: BeautifulSoup) -> dict:
    result = {
        "signature":   None,
        "return_type": "void",
        "description": None,
        "delay":       None,
        "energy":      None,
        "mono_only":   False,
        "deprecated":  False,
    }

    full_text = soup.get_text(" ")

    if re.search(r"deprecated", full_text, re.I):
        result["deprecated"] = True
    if re.search(r"mono.?only|requires mono", full_text, re.I):
        result["mono_only"] = True

    m = re.search(r"([\d.]+)\s*Forced Delay", full_text)
    if m:
        result["delay"] = float(m.group(1))
    m = re.search(r"([\d.]+)\s*Energy", full_text)
    if m:
        result["energy"] = float(m.group(1))

    # Primary: Deep Notes > Signature section — plain text, most reliable
    sig_match = re.search(
        r"function\s+(void|integer|float|string|key|vector|rotation|list)\s+"
        r"(ll\w+|os\w+)\s*\(([^)]*)\)",
        full_text,
        re.I | re.S,
    )
    if sig_match:
        ret    = sig_match.group(1)
        name   = sig_match.group(2)
        params = sig_match.group(3).strip()
        result["return_type"] = ret.lower()
        result["signature"]   = f"{ret} {name}( {params} )"

    # Fallback: parse Summary <p> tag (linked types, get_text strips links)
    if not result["signature"]:
        body = soup.find("div", class_="mw-parser-output")
        if body:
            for p in body.find_all("p"):
                t = tag_text(p)
                m2 = re.search(
                    r"Function:\s*"
                    r"(void|integer|float|string|key|vector|rotation|list)\s+"
                    r"(ll\w+|os\w+)\s*\(([^)]*)\)",
                    t, re.I,
                )
                if m2:
                    ret    = m2.group(1)
                    name   = m2.group(2)
                    params = m2.group(3).strip()
                    result["return_type"] = ret.lower()
                    result["signature"]   = f"{ret} {name}( {params} )"
                    break

    # Description: first substantial <p> that isn't boilerplate
    body = soup.find("div", class_="mw-parser-output")
    if body:
        for p in body.find_all("p"):
            t = tag_text(p)
            if (
                len(t) > 40
                and "Function:" not in t
                and not t.startswith("From Second Life")
                and not re.match(r"^\s*\d+\.\d+\s", t)
            ):
                result["description"] = t
                break

    return result

# ── Parameter parsing ─────────────────────────────────────────────────────────

def parse_parameters(soup: BeautifulSoup, func_name: str) -> list[dict]:
    params = []
    for tag in find_heading_sibling_content(soup, "Summary"):
        if tag.name != "table":
            continue
        for row in tag.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            type_text = tag_text(cells[0]).lstrip("•").strip().lower()
            if type_text not in LSL_TYPES:
                continue
            param_name = tag_text(cells[1]).strip()
            if not param_name or not re.match(r"^\w+$", param_name):
                continue
            desc = tag_text(cells[3]) if len(cells) > 3 else None
            params.append({
                "position":    len(params),
                "type":        type_text,
                "name":        param_name,
                "description": desc or None,
            })
    return params

# ── Caveats ───────────────────────────────────────────────────────────────────

def parse_caveats(soup: BeautifulSoup) -> list[str]:
    caveats = []
    for tag in find_heading_sibling_content(soup, "Caveats"):
        for li in tag.find_all("li"):
            t = tag_text(li)
            if t and len(t) > 5:
                caveats.append(t)
    return caveats

# ── Examples ──────────────────────────────────────────────────────────────────

def parse_examples(soup: BeautifulSoup) -> list[str]:
    examples = []
    for tag in find_heading_sibling_content(soup, "Examples"):
        for code_tag in tag.find_all(["pre", "code"]):
            t = code_tag.get_text("\n", strip=True)
            if t and len(t) > 10:
                examples.append(t)
                if len(examples) >= 3:
                    return examples
    return examples

# ── Related ───────────────────────────────────────────────────────────────────

def parse_related(soup: BeautifulSoup) -> list[str]:
    related = []
    for tag in find_heading_sibling_content(soup, "See Also"):
        for a in tag.find_all("a"):
            text = a.get_text(strip=True)
            if re.match(r"^(ll|os)[A-Z]\w+$", text):
                related.append(text)
    return list(dict.fromkeys(related))

# ── Page parser ───────────────────────────────────────────────────────────────

def parse_function_page(soup: BeautifulSoup, name: str) -> dict | None:
    if is_feature_request(soup):
        return None

    summary = parse_summary(soup)
    if not summary["signature"]:
        return None

    return {
        "name":            name,
        "signature":       summary["signature"],
        "return_type":     summary["return_type"],
        "description":     summary["description"],
        "parameters":      parse_parameters(soup, name),
        "delay":           summary["delay"],
        "energy":          summary["energy"],
        "mono_only":       summary["mono_only"],
        "deprecated":      summary["deprecated"],
        "caveats":         parse_caveats(soup),
        "examples":        parse_examples(soup),
        "related":         parse_related(soup),
        "common_mistakes": [],
        "since_version":   None,
    }

# ── Output ────────────────────────────────────────────────────────────────────

def write_function(data: dict) -> Path:
    FUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = FUNCTIONS_DIR / f"{data['name']}.json"
    with path.open("w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return path

# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape LSL function reference from wiki.secondlife.com")
    p.add_argument("--function", "-f", default=None, metavar="NAME")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--delay", type=float, default=REQUEST_DELAY, metavar="SECONDS")
    return p


def scrape_one(name: str, session: requests.Session, dry_run: bool, overwrite: bool) -> bool:
    out_path = FUNCTIONS_DIR / f"{name}.json"
    if not overwrite and out_path.exists():
        print(f"  [skip] {name} (already exists)")
        return True

    url  = FUNCTION_URL.format(name=name)
    soup = fetch(url, session)
    if not soup:
        return False

    data = parse_function_page(soup, name)
    if not data:
        print(f"  [skip] {name} (feature request or unparseable)")
        return False

    if dry_run:
        print(json.dumps(data, indent=2))
        return True

    path = write_function(data)
    print(f"  [ok]   {name} → {path.relative_to(ROOT)}")
    return True


def main() -> None:
    args    = build_parser().parse_args()
    session = requests.Session()
    errors  = []

    FUNCTIONS_DIR.mkdir(parents=True, exist_ok=True)

    if args.function:
        ok = scrape_one(args.function, session, args.dry_run, overwrite=True)
        sys.exit(0 if ok else 1)

    print("[*] Fetching function list from Category:LSL_Functions ...")
    names = get_all_function_names(session)
    print(f"[*] Found {len(names)} functions\n")

    for i, name in enumerate(names, 1):
        print(f"[{i:>4}/{len(names)}] {name}", end="  ")
        ok = scrape_one(name, session, args.dry_run, args.overwrite)
        if not ok:
            errors.append(name)
        time.sleep(args.delay)

    print(f"\n[done] {len(names) - len(errors)}/{len(names)} functions scraped")

    if errors:
        print(f"[warn] {len(errors)} errors — see {ERRORS_LOG.relative_to(ROOT)}")
        with ERRORS_LOG.open("w") as f:
            json.dump(errors, f, indent=2)


if __name__ == "__main__":
    main()
