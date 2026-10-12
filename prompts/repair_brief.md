TASK: your previous brief for {{TICKER}} failed automatic checks. Rewrite it so that every listed problem is fixed.

PROBLEMS FOUND BY THE VERIFIER
{{ERRORS}}

HOW TO FIX
- Uncited item: give it a non-empty "sources" list with the right id, or delete the item if no source supports it.
- Number not in the cited source: use the number exactly as the source writes it, or remove the number. Never compute or convert.
- Conflict not raised: add an open_questions item that states both sides with numbers and lists both source ids.
- Too long: delete the weakest items first and shorten the text of the rest.
- Keep everything that was already correct.

Return ONLY a JSON object with this exact shape (plain text, no source ids inside "text", 3-4 items in snapshot/bull/bear, 3-5 in open_questions, at most 35 words per item). Do NOT write Markdown:

{
  "snapshot": [{"text": "...", "sources": ["S1"]}],
  "bull": [{"text": "...", "sources": ["S1"]}],
  "bear": [{"text": "...", "sources": ["S2"]}],
  "open_questions": [{"text": "...", "sources": ["S1", "S4"]}]
}

PREVIOUS BRIEF
{{BRIEF}}