# Contributing

## Workflow

- Branch from `main`, open a pull request, merge when CI is green and the change is reviewed.
  `main` deploys, so it only takes reviewed changes.
- Keep a pull request to one change. Commits are small and each one passes the checks.
- Dependabot opens weekly updates; they go through the same review.

## Tests

- New behaviour starts with a failing test; a bug fix starts with the test that reproduces it.
- The risk maths (`indicators`, `scoring`, `exposure`) are pure functions with unit tests and
  Hypothesis properties. Anything that touches PostGIS or the Zarr store gets an integration
  test (`tests/integration`, Testcontainers).
- CI fails under 90% line and branch coverage. Coverage is a floor, not the goal: test what the
  code promises, not its lines.
- The web app has Vitest for components and Playwright with axe for whole pages; the
  infrastructure has `terraform test` with a mocked provider.

Run everything as in the README's Development section before pushing.

## Style

`ruff` and `mypy --strict` for Python, ESLint and Prettier for TypeScript, `terraform fmt` and
`tflint` for the infrastructure. CI runs all of them.

## AI coding agents

Much of this repository was written with an AI coding agent (Claude Code) and reviewed by a
person. If you use one too:

- You own every line it writes. Read the diff as you would a colleague's pull request.
- Never let it change a test to make it pass, or skip one; a failing test is information.
- Keep its changes small enough to review, and run the checks yourself.
- No secrets, credentials or private data in prompts.

## Security

Report vulnerabilities privately, as described in [SECURITY.md](SECURITY.md).
