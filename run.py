"""CLI:  python run.py --ticker SRVCABLE --docs research_pack
        python run.py --mode baseline     (naive one-shot, for the test log)
        python run.py --no-repair         (agent without the verifier loop)
        python run.py --list-models       (show models your API key can use)"""
import argparse

from agent.pipeline import run


def emit(step, d):
    if step == "ingest":
        print(f"[0] Ingested {len(d)} documents")
        for x in d:
            print(f"    {x['id']}  {x['date_str']:<11} tier {x['tier']}  {x['source'][:38]:<38} {', '.join(x['flags'])}")
    elif step == "extract":
        skip = "" if d["relevant"] else "  (NOT RELEVANT, skipped)"
        print(f"[1] {d['doc']}: kept {d['kept']} claims, dropped {d['dropped']} unverifiable{skip}")
    elif step == "analysis":
        print(f"[2] Cross-check: {len(d['conflicts'])} conflicts, {len(d['gaps'])} gaps, "
              f"{len(d['credibility_flags'])} credibility flags")
    elif step == "verify":
        print(f"[4] Verify round {d['round']}: {'PASS' if d['ok'] else 'FAIL'} "
              f"({len(d['errors'])} errors, {len(d['warnings'])} warnings, {d['words']} words)")
        for e in d["errors"]:
            print("      -", e)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="SRVCABLE")
    ap.add_argument("--docs", default="research_pack")
    ap.add_argument("--mode", choices=["agent", "baseline"], default="agent")
    ap.add_argument("--no-repair", action="store_true")
    ap.add_argument("--list-models", action="store_true", help="show models your API key can use")
    a = ap.parse_args()
    if a.list_models:
        from agent import llm
        print("\n".join(llm.list_models()))
        raise SystemExit
    res = run(a.ticker.upper(), a.docs, emit, mode=a.mode, repair=not a.no_repair)
    out_file = f"{a.ticker.upper()}_brief.md"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(res["brief"])
    print("\n" + "=" * 70 + "\n" + res["brief"] + "\n" + "=" * 70)
    print(f"Brief saved to: {out_file}")
    print(f"All intermediate files: {res['run_dir']}  ({res['log']['seconds']}s, model {res['log']['model']})")