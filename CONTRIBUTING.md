# Contributing to fvs_client

## Development environment

```bash
uv sync --all-groups          # create .venv with runtime + dev dependencies
uv run pre-commit install     # optional: run the checks on every commit
```

## Quality gates (run before every PR)

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pyright
uv run pytest --cov --cov-branch
```

Integration tests need a running FHIR Validation Service; see
`specs/001-fvs-python-sdk/quickstart.md` and run `uv run pytest -m integration`.

## Rules

- **Test first** (constitution principle III): write the test, see it fail, then implement.
- Public API changes update docstrings, docs and `CHANGELOG.md` (`[Unreleased]`) in the same PR.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages.
- Changes to the pinned service contract (`tests/contract/fvs-openapi-*.yaml`) go in their own PR.

## Releasing

1. Move the `## [Unreleased]` entries into a `## [X.Y.Z] - YYYY-MM-DD` section of `CHANGELOG.md`
   (the release workflow publishes that section as the GitHub release notes).
2. Tag the commit on `main`: `git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z`.
   The version comes from the tag (hatch-vcs); there is no version string to edit.
3. `.github/workflows/release.yml` then runs the full CI and integration suites, builds and
   checks the sdist and wheel, publishes to TestPyPI, smoke-tests the install, publishes to PyPI
   with Trusted Publishing (OIDC, with attestations), and creates the GitHub release.

One-time setup: register the `testpypi` and `pypi` environments as trusted publishers for this
repository on test.pypi.org and pypi.org.
