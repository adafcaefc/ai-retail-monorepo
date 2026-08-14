# Pull Request Template

Copy this into a PR description. Delete sections that genuinely don't apply (e.g. no
schema change) — don't leave unchecked boxes for things you didn't touch.

```markdown
## Summary

<!-- 1-3 sentences: what changed and why. Link the plan/issue/QC item if there is one. -->

## Area touched

- [ ] Backend agent (folder/id: `____.____`)
- [ ] Dashboard / filters
- [ ] Formulas (`resources/formula.md` / formula store)
- [ ] Data / schema (`newdata`, `retail`, or superseded schema — say which)
- [ ] Frontend page or agent UI override
- [ ] API route
- [ ] Deploy / CI (`Dockerfile`, `.forgejo/workflows/`)
- [ ] Docs only

## What changed

<!-- Bullet points. For an agent change, name the tool(s)/config(s)/prompt(s) touched.
     For a schema change, name the table(s). -->

## Testing

- [ ] `cd backend && pytest tests/ -q` passes
- [ ] `cd frontend && npm test` passes
- [ ] `scripts/verify_new_dataset.py` — N/A / passes (data-derivation change)
- [ ] `scripts/verify_agent_bugs.py` — N/A / passes (dashboard-figure change)
- [ ] Verification pack regenerated and byte-identical — N/A / done (`resources/formula.md` change)
- [ ] Manually exercised in the running app (describe below) — N/A / done

<!-- For a UI change: what you clicked through, and what you were checking for. -->

## Definition of Done

Checked against [`engineering-standards/ai/definition-of-done.md`](../ai/definition-of-done.md).
Call out anything intentionally skipped and why.

## Screenshots (UI changes only)

<!-- Before/after, or just after if this is new UI. -->

## Follow-ups

<!-- Anything deliberately left out of scope, with a pointer to where it's tracked. -->
```

## Notes for reviewers

- An agent PR without a matching `ENABLED_MODULES` change is valid ("scaffolding only")
  — check the PR says so rather than assuming it's an oversight.
- A dashboard-figure change with no `verify_agent_bugs.py` run is the single most common
  way a QC regression re-enters — ask for it explicitly if the checklist above is
  unchecked and the PR touches a dashboard card.
- If the diff adds a table to `freeform_query.py`, confirm it went to the correct
  domain's allow-list, not a shared one, per
  [`../principles/security.md`](../principles/security.md).
