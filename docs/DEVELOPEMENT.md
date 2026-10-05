# Developement Guide

## Installation

Run the commands in all these sections, in order

### System Dependencies (OSX)

Install the following

- homebrew
- git
- [uv](https://docs.astral.sh/uv/)
- postgres
- gnupg

via

    brew install git uv postgres gnupg

### System Dependencies (Linux)

The requirements are the same, you will just want to swap out homebrew for apt-get or similar

### Local Environment Setup

    git clone git@github.com:project-callisto/callisto-core.git # first time only
    cd callisto-core
    make dev-setup

`make dev-setup` creates the database, installs the locked environment with
`uv sync --locked` (uv installs the Python version from `.python-version`),
installs the pre-commit hooks, and loads the demo data.

Dependencies live in `pyproject.toml` and are pinned in `uv.lock`. After
changing them, run `uv lock` and commit both files.

## Running

The linters and tests

    make test-lint
    make test-suite

The demo app

    uv run python manage.py runserver

## Releasing

1. Bump `__version__` in `callisto_core/utils/version.py` and add an entry to `docs/HISTORY.md`.
2. Publish a GitHub release tagged with that version (for example `v0.28.0`).
3. `.github/workflows/release.yml` builds the package and publishes it to PyPI
   with trusted publishing. This needs a one-time trusted-publisher setup on PyPI.
