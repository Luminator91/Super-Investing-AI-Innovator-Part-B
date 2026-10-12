"""Step 0 (no LLM): read the research pack, parse each header, score recency and source trust."""
import re
from datetime import datetime
from pathlib import Path

from config import MAX_DOC_CHARS, STALE_DAYS, TODAY

DATE_FORMATS = ["%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y",
                "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]

# (trust tier, label, regex over source+url+title). Order matters: first match wins.
# Tier 1 = most trustworthy. These are heuristics; the LLM sees the tier as a hint, not a verdict.
TIERS = [
    (4, "unverified / social", r"blog|forum|reddit|telegram|whatsapp|twitter|x\.com|youtube|stocktwits|substack|tipster|rumou?r|message board"),
    (1, "exchange / regulatory filing", r"nseindia|bseindia|\bnse\b|\bbse\b|\bsebi\b|stock exchange|regulatory|annual report|\bfiling\b"),
    (2, "company-issued", r"press release|investor (?:presentation|deck|update)|earnings call|management commentary|company website|corporate"),
    (3, "media / analyst", r"times|mint|express|reuters|bloomberg|hindu|business|news|analyst|brokerage|research|report|moneycontrol|economic"),
]


def parse_date(s: str):
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s.replace(",", " ")).strip()
    s = re.sub(r"\s+", " ", s)
    candidates = [s] + re.findall(r"\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]+ \d{4}|[A-Za-z]+ \d{1,2} \d{4}", s)
    for c in candidates:
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(c, fmt).date()
            except ValueError:
                pass
    return None


def _field_of(key: str):
    key = key.lower().strip()
    if "url" in key or "link" in key:
        return "url"
    if "date" in key or "published" in key:
        return "date"
    if key in ("source", "publisher", "publication", "outlet", "site"):
        return "source"
    return None


def parse_header(text: str) -> dict:
    meta, title = {}, None
    for line in text.splitlines()[:15]:
        clean = re.sub(r"[*_`>]", "", line).strip().lstrip("#").strip()
        if title is None and line.lstrip().startswith("#"):
            title = clean
        m = re.match(r"^([A-Za-z ]{2,25})\s*[:\-–—]\s*(.+)$", clean)
        if m and _field_of(m.group(1)):
            meta.setdefault(_field_of(m.group(1)), m.group(2).strip())
    if "url" not in meta:
        u = re.search(r"https?://\S+", "\n".join(text.splitlines()[:15]))
        if u:
            meta["url"] = u.group(0).rstrip(").,")
    meta["title"] = title or (text.strip().splitlines()[0][:80] if text.strip() else "")
    return meta


def classify(source: str, url: str, title: str):
    blob = f"{source} {url} {title}".lower()
    for tier, label, pattern in TIERS:
        if re.search(pattern, blob):
            return tier, label
    return 3, "unclassified"


def load_docs(folder: str) -> list[dict]:
    files = sorted(p for p in Path(folder).iterdir()
                   if p.suffix.lower() in {".md", ".txt"} and p.name.lower() != "readme.md")
    if not files:
        raise FileNotFoundError(f"No .md/.txt documents found in '{folder}'. Copy the research_pack files there.")
    docs = []
    for i, p in enumerate(files, 1):
        text = p.read_text(encoding="utf-8", errors="ignore")
        meta = parse_header(text)
        d = parse_date(meta.get("date", "")) if meta.get("date") else None
        source, url = meta.get("source", "unknown source"), meta.get("url", "")
        tier, label = classify(source, url, meta["title"])
        age = (TODAY - d).days if d else None
        flags = []
        if d is None:
            flags.append("undated")
        elif age < 0:
            flags.append(f"future-dated ({-age} days after today)")
        elif age > STALE_DAYS:
            flags.append(f"stale ({age} days old)")
        if not url:
            flags.append("no URL")
        docs.append({
            "id": f"S{i}", "file": p.name, "title": meta["title"], "source": source, "url": url,
            "date": d, "date_str": d.isoformat() if d else "unknown", "age_days": age,
            "tier": tier, "tier_label": label, "flags": flags,
            "text": text, "text_for_llm": text[:MAX_DOC_CHARS],
        })
    return docs


def public_meta(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("text", "text_for_llm", "date")}
