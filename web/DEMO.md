# Three-minute G60 / US demo

## Before presenting

Use a copy of the local database for rehearsals and any recorded decisions. Copy its sibling `originals/` archive too, or preserved-source downloads will return `404`. Build the current API and web images together; an older API image can serve the overview data while returning `404` for `/actors`.

```sh
docker compose --profile web up --build -d api web
cd web
bun run demo:check http://127.0.0.1:3003
```

The preflight is read-only. It checks the frontend, API health, a PM reviewer, G60/US evidence and requirements, and the exact source trace of a current requirement. Open `http://127.0.0.1:3003/g60/us` after it passes.

## Presentation path

| Time | Show | Point to make |
| --- | --- | --- |
| 0:00–0:35 | Overview | The visible counts come from the G60/US inventory. Mention the Source B concentration notice: counts are not market prevalence. |
| 0:35–1:15 | Open the featured requirement | The proposal has a recorded priority and a separate evidence grade. A high score is not automatic approval. |
| 1:15–2:05 | Evidence Trace tab | Show one original customer record, its workbook sheet and row, and the linked finding. Supporting and conflicting links are both visible. |
| 2:05–2:35 | Score tab | Explain the scored factors and the evidence limitations. Skip the weight simulator. |
| 2:35–3:00 | Human decision footer | Select a declared PM reviewer, show the required rationale and decision action. Only submit if this is the prepared demo database. |

The core message: source evidence, the exact requirement version and score, and the PM decision remain connected. Use **More tools** only if the audience asks about imports, workflow runs, reviews or audit history.
