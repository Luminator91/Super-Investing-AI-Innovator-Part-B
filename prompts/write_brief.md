TASK: write a one-page research brief on {{TICKER}} for a retail investor, using ONLY the CLAIMS and ANALYSIS below.

Return ONLY a JSON object with this exact shape:

{
  "snapshot": [{"text": "...", "sources": ["S1"]}],
  "bull": [{"text": "...", "sources": ["S1"]}],
  "bear": [{"text": "...", "sources": ["S2"]}],
  "open_questions": [{"text": "...", "sources": ["S1", "S4"]}]
}

Do NOT write Markdown, headings or prose outside the JSON.

COUNTS: snapshot 3 to 4 items, bull 3 to 4 items, bear 3 to 4 items, open_questions 3 to 5 items. Never more.

WHAT GOES IN EACH
- snapshot: what the company does, then its latest reported results with the period and the source date. Use the latest_results field of the analysis.
- bull: the strongest reasons to be positive.
- bear: the strongest reasons to be cautious.
- open_questions: conflicts between sources (both sides, with numbers), stale or unverified evidence, and important things not disclosed.

RULES
- Every item MUST have a non-empty "sources" list with ids from the SOURCES list (for example "S3"). Use the document id only, never "S3.2".
- "text" is plain text: one or two sentences, at most 35 words. NO source ids, NO brackets, NO bold, NO numbering inside "text". The code adds those.
- Use numbers exactly as the claim writes them. Do NOT compute new numbers, convert units, or round.
- Rank by materiality, not by count. A filing beats a press release, a press release beats a media story, and a forum tip is never the main support of a point.
- A forecast, opinion or promotional claim must be labelled as such ("management expects...", "the company says..."), never stated as fact.
- If a point rests only on a weak or promotional source, say that in the text.
- Every conflict listed in ANALYSIS.conflicts must appear in open_questions, listing both sources in "sources".
- Plain words. Explain any jargon in a few words. No investment advice (no buy, sell, hold, price target).