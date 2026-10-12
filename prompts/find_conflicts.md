TASK: you are given the list of sources and every claim extracted from them. Cross-examine them like a sceptical analyst.

Return ONLY a JSON object with this exact shape:

{
  "latest_results": {"period": "e.g. Q1 FY27", "sources": ["S1"], "note": "which source gives the latest reported results and why you chose it"},
  "conflicts": [
    {"topic": "short label", "detail": "what each source says, with numbers", "sources": ["S2", "S5"],
     "more_reliable": "S2", "reason": "why, using trust tier, date and source type"}
  ],
  "gaps": ["important things an investor would need that NO source provides"],
  "credibility_flags": [{"source": "S4", "issue": "e.g. promotional, unverified, stale, forecast presented as fact"}]
}

LOOK FOR
- The same metric with different numbers in different sources.
- The same event told differently (for example a "record order" vs a delayed order).
- Positive claims that only a weak source makes and no filing confirms.
- Old data presented as current, undated sources, sources dated after today.
- Forecasts or guidance that contradict the latest reported results.
- Missing basics: cash flow, debt level, promoter holding or pledging, order book, customer concentration, peer or valuation context.

RULES
- Only report real findings that you can see in the claims. Never invent a conflict to look thorough. Empty lists are fine.
- Use only source ids that exist in the SOURCES list.
- Where trust tier, date and source type allow, say which side is more reliable. If you cannot tell, set "more_reliable" to null and say so.
