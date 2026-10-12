"""Minimal UI:  streamlit run app.py
Upload any set of documents + a ticker -> the agent shows every step and produces the brief."""
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from agent.pipeline import run

st.set_page_config(page_title="Research brief agent", layout="wide")
st.title("📄 Research brief agent")
st.caption("Upload documents + a ticker, get a one-page brief. Every step is shown, and nothing is trusted until it is checked.")


def save_uploads(files) -> str:
    """Write uploaded files into a temp folder the pipeline can read. PDFs are converted to text first."""
    folder = tempfile.mkdtemp(prefix="research_")
    for f in files:
        name = Path(f.name)
        if name.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError:
                st.error("PDF support needs:  pip install pypdf")
                st.stop()
            text = "\n".join(p.extract_text() or "" for p in PdfReader(f).pages)
            (Path(folder) / f"{name.stem}.txt").write_text(text, encoding="utf-8")
        else:
            (Path(folder) / name.name).write_bytes(f.getvalue())
    return folder


with st.sidebar:
    ticker = st.text_input("NSE ticker", "SRVCABLE").strip().upper()
    source = st.radio("Documents", ["Upload files", "Use a folder on disk"])
    uploads, folder_path = None, "research_pack"
    if source == "Upload files":
        uploads = st.file_uploader("Drop the documents here", type=["md", "txt", "pdf"],
                                   accept_multiple_files=True)
        if uploads:
            st.caption(f"{len(uploads)} file(s) ready")
    else:
        folder_path = st.text_input("Folder path", "research_pack")
    os.environ["LLM_PROVIDER"] = st.selectbox("Model provider", ["groq", "ollama"])
    mode = st.radio("Mode", ["agent", "baseline"], help="baseline = naive one-shot prompt, for comparison")
    repair = st.checkbox("Verifier repair loop", True)
    ready = bool(ticker) and (bool(uploads) if source == "Upload files" else True)
    go = st.button("Run agent", type="primary", disabled=not ready)
    if source == "Upload files" and not uploads:
        st.info("Upload at least one document to start.")

if go:
    docs_dir = save_uploads(uploads) if source == "Upload files" else folder_path
    log = st.container()
    result = {}

    def emit(step, d):
        with log:
            if step == "ingest":
                st.subheader("0 · Ingest (plain code, no AI)")
                st.dataframe(pd.DataFrame(d)[["id", "file", "source", "date_str", "age_days", "tier_label", "flags"]],
                             use_container_width=True, hide_index=True)
            elif step == "extract":
                msg = f"**{d['doc']}**: kept {d['kept']} claims, dropped {d['dropped']} with unverifiable quotes"
                st.write(msg if d["relevant"] else f"**{d['doc']}**: ⚠️ not relevant to the ticker, skipped")
                if d["note"]:
                    st.caption(d["note"])
            elif step == "claims":
                st.subheader("1 · Claims (each backed by a verified quote)")
                st.dataframe(pd.DataFrame(d)[["id", "kind", "topic", "stance", "period", "text", "quote_check"]],
                             use_container_width=True, hide_index=True)
            elif step == "analysis":
                st.subheader("2 · Cross-check across sources")
                lr = d.get("latest_results", {})
                st.info(f"Latest results: {lr.get('period')} from {lr.get('sources')}. {lr.get('note', '')}")
                for c in d["conflicts"]:
                    st.warning(f"**Conflict · {c.get('topic')}** ({', '.join(c.get('sources', []))}): {c.get('detail')}  \n"
                               f"More reliable: {c.get('more_reliable')} — {c.get('reason')}")
                for g in d["gaps"]:
                    st.write(f"🕳️ Gap: {g}")
                for f in d["credibility_flags"]:
                    st.write(f"🚩 {f.get('source')}: {f.get('issue')}")
            elif step == "draft":
                with st.expander(f"3 · Draft #{d['round']}", expanded=False):
                    st.markdown(d["brief"])
            elif step == "verify":
                st.subheader(f"4 · Verifier, round {d['round']}")
                (st.success if d["ok"] else st.error)(
                    f"{'PASS' if d['ok'] else 'FAIL'} · {d['words']} words")
                for e in d["errors"]:
                    st.write("❌", e)
                for w in d["warnings"]:
                    st.write("⚠️", w)
            elif step == "final":
                result.update(d)

    try:
        with st.spinner("Agent is working..."):
            run(ticker, docs_dir, emit, mode=mode, repair=repair)
        st.divider()
        st.header("Final brief")
        st.markdown(result["brief"])
        st.download_button("⬇️ Download brief (.md)", result["brief"], file_name=f"{ticker}_brief.md",
                           mime="text/markdown")
        st.caption(f"Model: {result['model']} · {result['seconds']}s · repair rounds: {result['repair_rounds']} · saved in {result['run_dir']}")
    except Exception as e:  # noqa: BLE001
        st.error(f"{type(e).__name__}: {e}")