# Contributing to DS Chat

Thanks for considering a contribution.

## Reporting bugs and requesting features

Open an issue on this project's issue tracker. Include steps to reproduce
for a bug, or the problem you're trying to solve for a feature request —
that's usually more useful than a proposed solution.

## Development setup

See the root [README.md](README.md)'s Quickstart, plus
[backend/README.md](backend/README.md) and
[frontend/README.md](frontend/README.md) for the full local dev setup
(Postgres, Redis, Python venv, migrations, the Vite dev server).
[ARCHITECTURE.md](ARCHITECTURE.md) covers the overall system design if
you're orienting yourself before a larger change.

## Before opening a pull request

- **Tests**: run `pytest` in `backend/` for any backend change, and add
  tests for new behavior rather than just the happy path — see
  `backend/README.md`'s "Run tests" section. For frontend changes, run
  `npx tsc -b` in `frontend/` and confirm `npm run build` succeeds.
- **Style**: match the conventions already in the file you're editing
  rather than introducing a new pattern — this codebase doesn't have a
  separate style guide beyond "look at what's already there."
- **Scope**: smaller, focused PRs are easier to review than large ones
  that mix unrelated changes.

## Contributor terms

By submitting a contribution (a pull request, patch, or similar), you
agree that:

1. Your contribution is licensed under the project's own license,
   AGPL-3.0-or-later ([LICENSE](LICENSE)), and
2. You grant the project's maintainer(s) a perpetual, worldwide,
   non-exclusive right to also relicense your contribution under different
   terms — for example, as part of a separately-licensed commercial
   offering built on this project.

This keeps the option of a future dual-licensed (open-source +
commercial) version of the project available, without requiring a
separate signed agreement for every contribution.

*This is a lightweight starting point, not a substitute for legal advice —
if you're contributing something substantial, or maintaining a fork with
your own commercial plans, it's worth having this reviewed by a lawyer
rather than relying on the paragraph above alone.*
