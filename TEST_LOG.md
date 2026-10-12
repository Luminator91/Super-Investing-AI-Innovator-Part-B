# Test log (fill in with your REAL results from runs/ folders)

Run order suggested: the first run is the naive baseline, so you can show a real "what went wrong".

| Run | Command | Design | What went wrong | What I changed |
|---|---|---|---|---|
| 1 | `python run.py --mode baseline` | One prompt, all docs, no steps | (e.g. hallucinated numbers, conflict missed, forum tip treated as fact, verifier errors: N) | Split into steps; claims ledger |
| 2 | `python run.py --no-repair` | 5-step agent, verifier only reports | (e.g. uncited bullet, conflict not in Open questions) | Added repair loop feeding verifier errors back |
| 3 | `python run.py` | Full agent with repair loop | (e.g. still X; how many repair rounds it needed) | (prompt tweak you made, if any) |

Paste the verifier error counts from each `runs/<timestamp>/run.json` and `4_verify_*.json`.
