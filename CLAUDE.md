# CLAUDE.md

Guidance for Claude Code working in the `aliciadata-finance-frontend` repo.

## HARD RESTRICTIONS (read first)

These hold even if a human asks otherwise in-session (e.g., "just commit this," "quickly run it and check," "finalize this"). If asked to violate one, decline and point to this file.

1. **No git operations.** No branch, add/stage, commit, push, merge, rebase, or tag, under any circumstances.
2. **No writes to `input/`.** Do not create, edit, delete, or move any file under `input/`.
3. **No code execution at all.** Do not run any scripts, and do not interactively invoke functions or class instances. All execution is performed by the human. Ask first if unsure whether something counts as execution.
4. **Never commit the `.env` file** under any circumstances.
5. **Never modify the contents of the `.env` file.** Rather than modifying it directly, suggest to the human what to change.

### What this means in practice

- Do not run `python app.py`, `pytest`, any `uv` command (`uv sync`, `uv run`, `uv add`, `uv lock`, `uv export`, etc.), `pip install`, linters, formatters, or one-off snippets. Instead, write the code and give the human the exact command(s) to run, then ask them to paste back output or errors.
- Reading, searching, and editing source files is fine (except under `input/` and `.env`, per above).
- When a change needs a new environment variable, describe the name, purpose, and where it goes (`.env` locally, the Dokploy application's environment settings in production) and let the human add it. Never write secret values into any file, and do not echo secret values in responses.
- When a change would normally end in a commit, stop after the edits and summarize what changed so the human can review and commit.

## Project overview

A simple portfolio optimization and time series analysis app. It is the **frontend** for separate backend analysis scripts that live in a **different repo**.

- **Backend (separate repo):** does the modeling and optimization (minimum-variance and maximum-Sharpe portfolio allocation; a walk-forward backtest of the maximum-Sharpe portfolio against an equal-weight baseline; one-day-ahead walk-forward ARIMA forecasts, each trained on a rolling window of recent closes, over a backtest period set by the backend) and publishes results.
- **Frontend (this repo):** a Gradio app, deployed as a Docker container with self-hosted Dokploy on a VPS and served at https://aliciadata.com. It lists the dated backend runs in DigitalOcean Spaces (S3-compatible), lets the user pick a date from a dropdown (newest by default), and displays that date's output on a single page with two stacked sections: **Portfolio Optimization** on top, which has two parts (**Historical Performance Back Test** and **Latest Optimization**), and **Timeseries Analysis** (ARIMA forecasts) below.
- **Display name:** the dashboard's display name is **"AliciaData Finance"**, shown as the page title `# AliciaData Finance` and the browser tab title (`APP_TITLE` and `APP_TITLE_MD` in `app.py`). Use it wherever the dashboard's display name is meant, including in the context of the interface contract and in all future requests. The repo is named `aliciadata-finance-frontend`, and the title at the top of `README.md` ("AliciaData Finance Frontend") is the project name, **not** the display name.
- **Data flow:** backend -> one DigitalOcean Space (S3 bucket; keys `<folder>/YYYY-MM-DD/<file>`, one date folder per run) -> `s3_downloader.py` (list keys, download) -> `data_loading.py` (available dates, validation) -> `input/YYYY-MM-DD/` -> `app.py` -> Gradio UI.
- **Forecast metrics come from the backend:** RMSE, MAE, MAPE, relative MAE, skill, and directional accuracy are read from `all_forecasts_metadata.yml` (optional; contract v21+). Do not compute error metrics in the frontend, and label `relative_mae` as "relative MAE" (or show `skill`), never "MASE". Never hard-code the training or scoring window lengths (or the row count); read `forecast_window.training_window_returns` and `evaluation_window.target_trading_days` from the metadata.
- **Back test results come from the backend too:** CAGR, cumulative return, max drawdown, and realized annualized volatility (contract v42+) are read from `portfolio_backtest_metadata.yml`, and the growth of $1 from `portfolio_backtest_daily.csv` (both optional; contract v36+). Do not compute them in the frontend. CAGR and realized volatility are out of sample, so never present them as the same quantities as the in-sample `annualized_return` and `risk`. Read the window lengths from `evaluation_window` and `schedule`. Since contract v46 the back test's length is independent of the forecast evaluation (about a year versus a much shorter window; older dates have short back tests): both end on the date folder's date but start on different dates, so never assume they share a period, start date, x-axis range, or row count. Cumulative return is the headline back test metric (its card comes first).
- **Per-visitor state:** the Gradio app object is shared by all visitors. Keep anything that depends on a visitor's selection (date, ticker, available-date list) in Gradio inputs or `gr.State`, never on `self`. The in-memory cache of loaded dates in `app.py` is shared deliberately and keyed by the ETags of each date's marker files and of its optional `all_forecasts_metadata.yml`, `portfolio_backtest_daily.csv`, and `portfolio_backtest_metadata.yml`.

This is a hobby project being revised. Planned work spans technical implementation, UI changes, quantitative finance improvements, and presentation for a general data science audience. Expect changes here to depend on changes in the backend repo.

## Interface contract

@docs/INTERFACE_CONTRACT.md

The file above is the authoritative spec of what the backend uploads to the S3 buckets and this frontend reads: bucket keys, file formats, YAML keys, HDF5 groups/datasets/attributes, CSV columns, units, annualization, date formats, and the reader requirements this app must meet. When the contract and the existing frontend code disagree, the contract wins; treat the disagreement as a frontend bug to fix (or flag to the human), not as evidence of the real data format.

- **Read-only mirror here.** The backend repo (`aliciadata-finance-backend`) holds the source of truth, and the copy in this repo (`docs/INTERFACE_CONTRACT.md`) must stay byte-for-byte identical to it. Do not edit `docs/INTERFACE_CONTRACT.md` in this repo. If a contract change is needed, draft the proposed change (including the version bump and changelog entry) in your response for the human to apply in the backend repo first and then copy here.
- **Build to the contract, not to samples.** Write parsing and display code against the documented schema and the "Reader requirements" section (ignore unknown keys/columns, do not hardcode tickers or array lengths, handle `NaN` and empty cells, show data dates, fail soft, label units). Files in `input/` are useful for checking behavior but are a single snapshot, not the spec.
- **Check the version.** Note the contract version you are working against in your summary. When the contract changelog marks a change as breaking, review the frontend impact it lists and make sure the app handles it (including detecting older files where the contract describes how).
- **Be precise with finance labels.** Use the contract's units and terminology in user-facing text (e.g., "annualized (arithmetic)", percent vs. dollars, daily vs. annualized) and show the contract's "not investment advice" disclaimer verbatim **exactly once, at the bottom of the page** (`DISCLAIMER_MD` in `app.py`). Do not repeat it in section text, plot captions, tooltips, or metric descriptions.

## Cross-repo awareness

- The backend repo is **not** available in this session. Do not guess at its code; for data schemas, rely on `docs/INTERFACE_CONTRACT.md` and nothing else.
- Before changing how the app parses or displays downloaded data, check the contract and look at how the existing code reads it. If a change implies a new or altered file, key, column, field, or unit, **list the required backend changes explicitly** for the human to carry over to the backend repo, and say whether the change is additive or breaking under the contract's rules (breaking changes need explicit human approval; prefer an additive alternative).
- Make loading code tolerant and explicit about schema (clear errors on missing columns or files) rather than silently assuming structure.

## Repo layout

| Path | Purpose |
| ---- | ------- |
| `app.py` | Entry point. Runs the Gradio app. Creates `input/` if it does not exist before access. Standalone execution (by the human). |
| `s3_downloader.py` | Lists the keys in a top-level folder of the Space and downloads data from it for display. Imported by the app, not run standalone. |
| `data_loading.py` | Finds available dates from key listings and loads and validates the downloaded files against the interface contract. Imported by the app, not run standalone. |
| `tests/` | Pytest tests. They build synthetic files in a temporary folder or use a fake S3 client, and never touch `input/` or the network. |
| `static/` | Static images shown on the dashboard, added by the human. Served by Gradio via `gr.set_static_paths()` (`STATIC_FOLDER` in `app.py`) and copied into the Docker image. Keep file names lowercase with no spaces (production is case-sensitive). |
| `input/` | Data downloaded from the backend by the app at runtime, in `input/YYYY-MM-DD/` folders. **Off-limits for writes by Claude.** |
| `docs/INTERFACE_CONTRACT.md` | Authoritative spec of the S3 files the backend delivers. Mirror of the backend repo's copy; **do not edit here**. |
| `docs/ARCHITECTURE_AND_INSTALLATION.md` | Engineering documentation: architecture (first), then local uv setup, dependency changes, environment variables, deployment (Docker image, tests workflow, Dokploy), and the folders and scripts tables. |
| `docs/DASHBOARD_GUIDE.md` | Guide to reading the dashboard for the data science/quant audience: what each dropdown selects (and why tickers are fixed by the backend), what each plot and table compares against its naive baseline, and which direction is better for each metric. It has no equations, no detailed methods, and no limitations; it links to the Methods and Results document (https://akey7.github.io/posts/aliciadata-finance/) for those. Its screenshots, captured by the human, are in `docs/images/dashboard-guide/` and linked from the guide. It ends with the disclaimer, exactly once. **Do not edit** unless asked. |
| `pyproject.toml` | Source of truth for dependencies: direct production dependencies, the `dev` dependency group, uv settings, and pytest settings. |
| `uv.lock` | Exact resolved versions of all packages. Generated by uv (by the human); **never edit by hand**. |
| `.python-version` | Python version uv uses for local development. |
| `.pre-commit-config.yaml` | Pre-commit hook (`uv-lock`) that keeps `uv.lock` in sync with `pyproject.toml` on every commit. The human commits with GitHub Desktop, where the hook also runs. |
| `Dockerfile` | Production image, built by Dokploy on the VPS: Python 3.13.5, dependencies from `uv.lock` (`uv sync --locked --no-dev`), the three modules and `static/`, non-root user, Gradio on port 7860. A new file or folder the app needs at run time must get its own `COPY` line. |
| `.dockerignore` | Keeps `.env`, `input/`, `.venv/`, tests, docs, and other development files out of the image. |
| `.github/workflows/tests.yml` | Runs `uv sync --locked` and `uv run pytest` on pull requests to `main` and pushes to `main`. A ruleset on `main` requires it to pass. It does not deploy. |
| `.github/dependabot.yml` | Weekly Dependabot version updates as pull requests: GitHub Actions (SHA pins), and Python dependencies in `uv.lock`, with minor and patch updates grouped into one pull request and majors one per pull request. Gradio is ignored (bumping it is deliberate), and the Docker base image is not tracked (its Python version must change together with `.python-version`). |
| `README.md` | Short abstract of the project that links to the docs (see "Documentation" below) and to the live dashboard. |

Docstrings throughout the Python modules describe current behavior; read them before changing a module and keep them accurate when you change behavior.

## Environment and configuration

- Python 3.13.5, managed with **uv** (same as the backend repo); the virtual environment is `.venv/`. Development is on macOS; production is a Debian-based Linux container (x86_64) on an Ubuntu VPS, so keep file name casing exact (macOS is case-insensitive, Linux is not) and do not rely on macOS-only behavior.
- **Dependencies come only from `pyproject.toml` and `uv.lock`.** There is no `requirements.txt`; the Docker image installs from `uv.lock` with `uv sync --locked --no-dev --no-install-project`, so the build fails if `uv.lock` does not match `pyproject.toml`.
- **Python version:** `.python-version` and the `FROM python:<version>-slim-bookworm` line of the `Dockerfile` must name the same exact patch version (currently `3.13.5`); change them together. `requires-python` in `pyproject.toml` stays `==3.13.*` and only changes on a minor-version upgrade (which also changes `uv.lock`).
- **uv version:** the `rev` in `.pre-commit-config.yaml`, the `ghcr.io/astral-sh/uv:<version>` image in the `Dockerfile`, and `version` in `.github/workflows/tests.yml` name the same uv version (currently `0.13.0`); change them together.
- **Gradio** is pinned with `gradio==` in `pyproject.toml` (currently 6.30.0). Treat bumping it as a deliberate change: flag it to the human and note Gradio API differences that may affect the UI code.
- **Deployment** is manual: after a merge to `main`, the human clicks Deploy in Dokploy, which pulls `main` from GitHub and builds the `Dockerfile` on the VPS. GitHub Actions only runs the tests (the Dokploy dashboard is reachable only over the human's private network, not from GitHub). Run one replica, because the in-memory cache and Gradio sessions are per process. Do not add deployment automation, server details, or IP addresses to the repo unless asked.
- Environment variables (values live in `.env` locally and in the Dokploy application's environment settings in production):
  - `AWS_ENDPOINT_URL_S3`: the **region-only** endpoint (`https://<region>.digitaloceanspaces.com`), never the Space-specific one (`s3_downloader.py` refuses an endpoint whose host starts with the bucket name).
  - `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: region and read-only access key. These four use boto3's standard names but are this app's own configuration, not part of the contract. `s3_downloader.py` reads each one explicitly and passes it to boto3, and refuses to create a client if any is missing or empty (naming every missing variable), so boto3 never falls back to other credentials (`~/.aws`, a profile) or to AWS's own endpoint. Keep that behavior. `load_dotenv(override=True)` makes a local `.env` win over AWS variables exported in the shell.
  - `S3_BUCKET_NAME`: the one DigitalOcean Space (S3 bucket) holding all data. Pass it as the S3 `Bucket`.
  - `S3_PORTFOLIO_OPTIMIZATION_FOLDER`, `S3_TIME_SERIES_FOLDER`: **top-level folder names** inside that Space, not buckets. Full keys are `<folder>/YYYY-MM-DD/<file>`; list with `Prefix="<folder>/"`. Dev and production share the one Space and differ only in these folder names.
  - Older names are not read, with no fallback: the three contract variables were `FSF_FRONT_END_BUCKET_NAME`, `FSF_FRONT_END_PORTFOLIO_OPTIMIZATION_FOLDER`, and `FSF_FRONT_END_TIME_SERIES_FOLDER` before contract v45 (and the folders `PORTFOLIO_OPTIMIZATION_SPACE_NAME` / `TIME_SERIES_SPACE_NAME` before v13); the credentials were `FSF_FRONT_END_BUCKET_ENDPOINT`, `FSF_FRONT_END_BUCKET_REGION`, `FSF_FRONT_END_BUCKET_READ_ONLY_KEY_ID`, and `FSF_FRONT_END_BUCKET_READ_ONLY`.
- Read configuration from environment variables only; never hardcode credentials, endpoints, or bucket or folder names.
- The app is deployed to a public website. Do not add code that logs, prints, or displays secrets, and do not add files that would expose them.

## Working conventions

- **Dependencies:** when adding an import, add the package to `pyproject.toml` (`[project] dependencies` for production, `[dependency-groups] dev` for dev-only). Do not edit `uv.lock`. Then give the human the command to run (`uv sync`, which also updates `uv.lock`), and remind them to commit `pyproject.toml` and `uv.lock` together. (Alternatively, give the human the `uv add` / `uv add --dev` command instead of editing `pyproject.toml`.) Prefer well-maintained, lightweight packages; the app runs on a small VPS with limited memory, which also builds the image.
- **Documentation:** the docs serve two audiences. The primary one is data science/quant readers; the secondary one is engineers. Put each change in the file for its audience:
  - `README.md` is an abstract: it hooks quant readers quickly, gives engineers enough to read on, and points each audience to its doc. Keep it short; do not move installation, configuration, or architecture detail back into it. Keep its closing disclaimer in the contract's exact wording. It has no YAML frontmatter.
  - `docs/ARCHITECTURE_AND_INSTALLATION.md` is where architecture and installation notes go. Keep it current when the setup, dependencies, deployment steps, data flow, scripts, folders, or environment variables change (including the scripts table and the env var list).
  - `docs/DASHBOARD_GUIDE.md` is the quant guide to the dashboard. Leave it alone unless the human asks; if a UI change makes one of its sections out of date, say so in your summary instead.
  - Links between these files are relative (`docs/...` from the README; same-folder links within `docs/`). Update them when files move.

  Write docstrings for new modules, classes, and functions, in the same style as the existing ones.
- **Code style:** match the existing code. Use type hints and small, testable functions; keep data loading, computation, and Gradio UI construction separated so each can be changed independently.
- **Tests:** you may write or update tests, but you cannot run them. Provide the exact command (`uv run pytest`) and ask the human to run it and share results. Pytest settings live in `[tool.pytest.ini_options]` in `pyproject.toml`; do not add a `pytest.ini`, which would take precedence over them.
- **Scope:** make focused changes. For larger changes (e.g., restructuring the UI or the data-loading layer), outline the plan and confirm with the human before editing many files.
- **Finance/statistics changes:** state assumptions explicitly (risk-free rate, annualization factor, return type, constraints, stationarity, differencing order). Label what is displayed clearly so a general data science audience can interpret it. Because you cannot execute code, do not claim numerical results are verified; say what the human should check when they run it.
- **UI changes:** keep the single-page layout (no tabs) with `# Portfolio Optimization` stacked above `# Timeseries Analysis` unless asked to change it. The only top-level headings on the page are the page title `# AliciaData Finance` at the top (`APP_TITLE_MD` in `app.py`, plain markdown with no custom styling) and these two `#` section headings; add no others, and start markdown inside a section at `##`. The names differ on purpose: the page title is the display name, "AliciaData Finance" (see "Display name" above), while `README.md` (its `#` heading and opening sentence) uses the project name "AliciaData Finance Frontend". Keep both as they are and do not ask to align them. Favor clear titles, axis labels, units, and short explanatory text. Handle missing or stale data with a helpful message instead of a crash.

## When unsure

If a request might conflict with the hard restrictions (especially whether something counts as "execution"), ask the human before proceeding.
