"""The agent. Five explicit steps, each one visible and saved to runs/<timestamp>/.

  0 INGEST    code   parse headers, dates, staleness, source-trust tier
  1 EXTRACT   LLM    per document -> atomic claims with verbatim evidence
      (code)         drop any claim whose quote is not really in the document
  2 CROSS-CHECK LLM  conflicts, gaps, credibility problems across all claims
  3 WRITE     LLM    brief as JSON from the claims ledger; CODE adds citations and headings
  4 VERIFY    code   citations, numbers, length, conflicts surfaced -> repair loop
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor

import json
import re
import time
from datetime import datetime
from pathlib import Path

from agent import llm
from agent.ingest import load_docs, public_meta
from agent.verify import assemble, check_quote, split_sections, verify_brief
from config import MAX_REPAIR_ROUNDS, TODAY

ROOT = Path(__file__).resolve().parent.parent
noop = lambda step, data: None  # noqa: E731


def _prompt(name: str, **kw) -> str:
    text = (ROOT / "prompts" / name).read_text(encoding="utf-8")
    for k, v in kw.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _system() -> str:
    return _prompt("system_prompt.md", TODAY=f"{TODAY:%d %B %Y}")


def _save(run_dir: Path, name: str, obj):
    p = run_dir / name
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=2, default=str, ensure_ascii=False),
                 encoding="utf-8")


# ---------- step 1 ----------
def extract_claims(doc: dict, ticker: str) -> dict:
    header = (f"DOCUMENT {doc['id']} | source: {doc['source']} | published: {doc['date_str']} "
              f"| trust tier {doc['tier']} ({doc['tier_label']}) | flags: {', '.join(doc['flags']) or 'none'}")
    user = (_prompt("extract_claims.md", TICKER=ticker) + "\n\n" + header +
            "\n=== DOCUMENT START ===\n" + doc["text_for_llm"] + "\n=== DOCUMENT END ===")
    data = llm.chat_json(_system(), user)
    kept, dropped = [], 0
    for c in data.get("claims", []) if data.get("relevant", True) else []:
        if not isinstance(c, dict):
            continue
        text, ev = str(c.get("text", "")).strip(), str(c.get("evidence", "")).strip()
        status = check_quote(ev, doc["text"])
        if not text or status == "fail":
            dropped += 1          # hallucinated or mangled quote -> the claim is thrown away
            continue
        kept.append({"id": f"{doc['id']}.{len(kept) + 1}", "doc": doc["id"], "text": text,
                     "evidence": ev, "quote_check": status,
                     "kind": str(c.get("kind", "unknown")).lower(),
                     "topic": str(c.get("topic", "other")).lower(),
                     "stance": str(c.get("stance", "neutral")).lower(),
                     "period": c.get("period")})
    return {"relevant": bool(data.get("relevant", True)), "note": data.get("doc_note", ""),
            "claims": kept, "dropped": dropped}


# ---------- ledger shown to later steps ----------
def make_ledger(docs: list[dict], claims: list[dict]) -> str:
    lines = ["SOURCES (id | name | published | age in days | trust tier | flags)"]
    for d in docs:
        lines.append(f"{d['id']} | {d['source']} | {d['date_str']} | {d['age_days']} | "
                     f"tier {d['tier']} ({d['tier_label']}) | {', '.join(d['flags']) or 'none'}")
    lines.append("\nCLAIMS")
    for c in claims:
        lines.append(f"[{c['doc']}] ({c['kind']}, {c['topic']}, {c['stance']}, period={c['period']}) {c['text']}")
    return "\n".join(lines)


# ---------- step 2 ----------
def cross_check(docs, claims, ledger: str) -> dict:
    data = llm.chat_json(_system(), _prompt("find_conflicts.md") + "\n\n" + ledger)
    ids = {d["id"] for d in docs}
    data["conflicts"] = [c for c in data.get("conflicts", [])
                         if isinstance(c, dict) and any(s in ids for s in c.get("sources", []))]
    data.setdefault("gaps", [])
    data.setdefault("credibility_flags", [])
    data.setdefault("latest_results", {})
    # deterministic flags from step 0 are added by code, so the LLM cannot forget them
    for d in docs:
        for f in d["flags"]:
            data["credibility_flags"].append({"source": d["id"], "issue": f"(rule-based) {f}"})
    return data


# ---------- steps 3 and 4 ----------
ALIASES = {"bull_case": "bull", "bullcase": "bull", "bear_case": "bear", "bearcase": "bear",
           "openquestions": "open_questions", "questions": "open_questions"}


def _ids(sources) -> list[str]:
    out = []
    if isinstance(sources, str):
        sources = re.findall(r"S\d+", sources)
    for s in sources or []:
        m = re.match(r"S\d+", str(s).strip())
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def render_brief(data: dict, analysis: dict | None = None) -> str:
    """The model returns structured JSON; CODE adds bullets, headings and [S#] tags, and guarantees
    that every conflict found in step 2 appears in Open questions."""
    data = {ALIASES.get(k.lower().replace(" ", "_"), k.lower().replace(" ", "_")): v
            for k, v in data.items()}
    caps = {"snapshot": 4, "bull": 4, "bear": 4, "open_questions": 5}

    def items(key):
        out = []
        for it in (data.get(key) or [])[:caps[key]]:
            if isinstance(it, str):
                it = {"text": it, "sources": []}
            if not isinstance(it, dict):
                continue
            text = re.sub(r"[\[(]\s*S\d+[^\])]*[\])]", "", str(it.get("text", ""))).replace("**", "").strip()
            if text:
                out.append((text, _ids(it.get("sources") or it.get("source"))))
        return out

    oq = items("open_questions")
    raised = {s for _, ids in oq for s in ids}
    for c in (analysis or {}).get("conflicts", []):
        srcs = _ids(c.get("sources"))
        if len(srcs) >= 2 and not raised.intersection(srcs):
            detail = " ".join(str(c.get("detail", "")).split()[:40])
            oq.append((f"Sources disagree on {c.get('topic', 'a key point')}: {detail} (added by cross-check)", srcs))
            raised.update(srcs)

    def fmt(rows, bullet=True):
        return "\n".join(("- " if bullet else "") + f"{t} {''.join(f'[{i}]' for i in ids)}".strip()
                         for t, ids in rows)

    return ("## Snapshot\n" + fmt(items("snapshot"), False) + "\n\n## Bull case\n" + fmt(items("bull")) +
            "\n\n## Bear case\n" + fmt(items("bear")) + "\n\n## Open questions\n" + fmt(oq))


def write_brief(ticker: str, ledger: str, analysis: dict) -> str:
    user = (_prompt("write_brief.md", TICKER=ticker) + "\n\n" + ledger +
            "\n\nANALYSIS (JSON)\n" + json.dumps(analysis, indent=1, ensure_ascii=False))
    return render_brief(llm.chat_json(_system(), user), analysis)


def repair_brief(ticker: str, brief: str, errors: list[str], ledger: str, analysis: dict) -> str:
    user = (_prompt("repair_brief.md", TICKER=ticker, BRIEF=brief,
                    ERRORS="\n".join(f"- {e}" for e in errors)) + "\n\n" + ledger +
            "\n\nANALYSIS (JSON)\n" + json.dumps(analysis, indent=1, ensure_ascii=False))
    return render_brief(llm.chat_json(_system(), user), analysis)


def _baseline(ticker: str, docs: list[dict]) -> str:
    """The naive approach, kept for the test log: dump everything into one prompt, no steps."""
    body = "\n\n".join(f"[{d['id']}]\n{d['text_for_llm']}" for d in docs)
    user = (f"Write a one-page research brief on {ticker} with sections Snapshot, Bull case, Bear case, "
            f"Open questions. Cite sources like [S1] at the end of each line.\n\n{body}")
    return llm.chat("You are a helpful assistant.", user, temperature=0.2)


# ---------- the whole run ----------
def run(ticker: str, docs_dir: str, emit=noop, mode: str = "agent", repair: bool = True) -> dict:
    t0 = time.time()
    run_dir = ROOT / "runs" / f"{datetime.now():%Y%m%d-%H%M%S}-{mode}"
    run_dir.mkdir(parents=True, exist_ok=True)
    log = {"ticker": ticker, "mode": mode, "repair": repair, "provider": llm.provider_name(),
           "model": llm.model_name(), "today": str(TODAY)}

    # 0 ingest
    docs = load_docs(docs_dir)
    _save(run_dir, "0_docs.json", [public_meta(d) for d in docs])
    emit("ingest", [public_meta(d) for d in docs])

    claims, analysis, ledger = [], {}, ""
    if mode == "baseline":
        brief_md = _baseline(ticker, docs)
    else:
                # 1 extract (documents are independent, so run 3 at a time)
        with ThreadPoolExecutor(max_workers=3) as ex:
            for d, res in zip(docs, ex.map(lambda doc: extract_claims(doc, ticker), docs)):
                claims += res["claims"]
                emit("extract", {"doc": d["id"], "relevant": res["relevant"], "note": res["note"],
                                 "kept": len(res["claims"]), "dropped": res["dropped"]})
        if not claims:
            raise RuntimeError("No verifiable claims extracted. Check your model / documents.")
        _save(run_dir, "1_claims.json", claims)
        emit("claims", claims)

        # 2 cross-check
        ledger = make_ledger(docs, claims)
        analysis = cross_check(docs, claims, ledger)
        _save(run_dir, "2_analysis.json", analysis)
        emit("analysis", analysis)

        # 3 write
        brief_md = write_brief(ticker, ledger, analysis)

    # 4 verify (+ repair loop in agent mode)
    rounds = 0
    while True:
        _save(run_dir, f"3_draft_{rounds}.md", brief_md)
        emit("draft", {"round": rounds, "brief": brief_md})
        sections = split_sections(brief_md)
        report = verify_brief(sections, docs, analysis)
        _save(run_dir, f"4_verify_{rounds}.json", report)
        emit("verify", {"round": rounds, **report})
        if report["ok"] or mode == "baseline" or not repair or rounds >= MAX_REPAIR_ROUNDS:
            break
        rounds += 1
        brief_md = repair_brief(ticker, brief_md, report["errors"], ledger, analysis)

    final = assemble(ticker, sections, docs, TODAY)
    _save(run_dir, "5_final_brief.md", final)
    log.update({"repair_rounds": rounds, "verified": report["ok"], "errors_left": report["errors"],
                "warnings": report["warnings"], "seconds": round(time.time() - t0, 1)})
    _save(run_dir, "run.json", log)
    emit("final", {"brief": final, "run_dir": str(run_dir), **log})
    return {"brief": final, "report": report, "run_dir": str(run_dir), "log": log,
            "claims": claims, "analysis": analysis}