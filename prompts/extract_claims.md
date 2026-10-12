TASK: read ONE document about {{TICKER}} and extract the claims an investor would care about.

Return ONLY a JSON object with this exact shape:

{
  "relevant": true,
  "doc_note": "one sentence: what this document is and how much weight it deserves",
  "claims": [
    {
      "text": "one atomic claim, with number, unit and period if given",
      "evidence": "words copied EXACTLY from the document, at most 30 words",
      "kind": "fact | forecast | opinion | promotional",
      "topic": "business | revenue | profit | margin | debt | cash_flow | orders | capacity | governance | valuation | risk | other",
      "stance": "positive | negative | neutral",
      "period": "for example Q1 FY27, or null"
    }
  ]
}

RULES
- "relevant" is false if the document is not actually about {{TICKER}} (wrong company, generic market commentary). Then return an empty claims list.
- Extract 5 to 12 claims, the most decision-relevant ones. One fact per claim.
- Include the unflattering and boring items: debt, contingent liabilities, related-party dealings, promoter pledging, auditor remarks, customer concentration, delays, one-off gains. Buried disclosures matter.
- "evidence" must be a verbatim copy from the document. Do not paraphrase it. Do not fix its typos. Do not translate or convert its numbers.
- "kind": fact = reported as having happened; forecast = about the future; opinion = someone's judgement; promotional = marketing language or a claim made to sell the stock or the company.
- Keep numbers exactly as written, with their units (crore, lakh, %, etc.).
- Do not invent a period. Use null if none is stated.
