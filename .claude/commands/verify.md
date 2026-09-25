---
description: Verify the current phase against its acceptance criteria and the non-negotiables
---
Verify the work of the current phase (ask me which phase if unclear):

1. Run `make test`, `make lint`, and `cd reference && python -m pytest -q`.
2. Check each acceptance criterion in `docs/implementation-plan.md` for this phase: met / not met / evidence.
3. Check the non-negotiables in `CLAUDE.md`:
   - no truth data in operational code paths
   - anonymous events carry no identity
   - no hard-coded parameters
   - no mock data in API/frontend (`rg -n "Math.random|faker|mockData|dummy" frontend/src services`)
   - no aggregate maths in React components
   - only tables/events/endpoints/pages that exist in the docs
4. Report as a short table plus a list of fixes. Don't fix anything unless I ask.
