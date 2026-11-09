# Architecture and Installation

## Architecture

The backend does all the modeling and publishes its results; this app only lists, downloads, validates, and displays them.

```
 legend: [external]   module.py   ─► data flow

 [aliciadata-finance-backend]   backend repo; uploads one date folder per run
            │
            ▼
 [DigitalOcean Space]   one bucket (S3_BUCKET_NAME), two folders
   <portfolio optimization folder>/YYYY-MM-DD/
       optimization_metadata.yml             marker: the date is complete
       portfolio_optimization_plot_data.h5
       portfolio_backtest_daily.csv          optional (contract v36+)
       portfolio_backtest_metadata.yml       optional (contract v36+)
   <time series folder>/YYYY-MM-DD/
       all_forecasts.csv                     marker
       all_forecasts_metadata.yml            optional (contract v21+)
            │
            ▼
 app.py   entry point; FSFinance builds the single Gradio page
   │
   ├─ 1. LIST      on every page load
   │      s3_downloader.py   list_keys()        every key per folder, with ETags
   │      data_loading.py    available_dates()  dates with both markers
   │                         ─► date dropdown, newest first
   │
   ├─ 2. LOAD      when a date is selected, unless already cached
   │      s3_downloader.py   download_file()    ─► input/YYYY-MM-DD/<file>
   │      data_loading.py    load_*()           validate against the contract
   │      in-memory cache shared by all visitors, keyed by date + ETags
   │
   └─ 3. DISPLAY   per visitor (selected date and ticker in Gradio state)
          # AliciaData Finance       page title (the display name)
          date selector              date dropdown; individual assets accordion
          # Portfolio Optimization
            ## Historical Performance Back Test   metric cards, growth of $1
            ## Latest Optimization                frontier, random portfolios, weights
          # Timeseries Analysis      actual, ARIMA, and naive; backend metrics
          disclaimer, once at the bottom
            │
            ▼
       [visitor's browser]
```

The files the backend delivers, and how the app must read them, are specified in the [Interface Contract](INTERFACE_CONTRACT.md). That file is a read-only mirror of the copy in the backend repo. The app requires contract v4 or later data; older files are reported on the dashboard instead of being displayed.

All data lives in one DigitalOcean Space (one S3 bucket) with two top-level folders, one for portfolio optimization and one for time series forecasts. The backend stores each run's files in a date folder inside each, at keys `<folder>/YYYY-MM-DD/<file>`, where the date is the last NYSE trading day in the data. A dropdown at the top of the app lists the dates whose data is complete in both folders, newest first, and selects the newest by default. The list is refreshed on every page load, and the page's two stacked sections, **Portfolio Optimization** (top) and **Timeseries Analysis** (below), show data from the selected date only. The Portfolio Optimization section has two parts, **Historical Performance Back Test** and **Latest Optimization**; dates before contract v36 have no back test files and show a message in place of the first. Objects directly under a top-level folder (left by older backend versions) are ignored. The read-only access key needs permission to **list** the Space as well as to read objects.

## Installation

### Development environment (uv)

Local development uses [uv](https://docs.astral.sh/uv/) to manage both the Python version and the dependencies. The relevant files are:

| File | Role |
| ---- | ---- |
| `.python-version` | Exact Python version used by uv for local development (`3.13.5`). |
| `pyproject.toml` | Direct production dependencies, the `dev` dependency group, and pytest settings. **Edit dependencies here.** |
| `uv.lock` | Exact resolved versions of every package. Commit it. |
| `.pre-commit-config.yaml` | Git pre-commit hook that keeps `uv.lock` in sync with `pyproject.toml` on every commit. |

Install uv (once), then create the virtual environment in `.venv/` with the pinned Python version and all production and development dependencies:

```
brew install uv
uv sync
```

Then install the pre-commit hook (once per clone):

```
uv run pre-commit install
```

Run the app and the tests through uv:

```
uv run python app.py
uv run pytest
```

### Changing dependencies

Add or remove packages with uv, which updates `pyproject.toml` and `uv.lock` together:

```
uv add <package>
uv add --dev <package>
uv remove <package>
```

Commit `pyproject.toml` and `uv.lock` together. The pre-commit hook re-locks `uv.lock` whenever it is out of date. The hook runs in GitHub Desktop as well as on the command line. The Docker build installs with `uv sync --locked`, so it fails if `uv.lock` does not match `pyproject.toml`; `uv lock --check` tests this locally.

**If a commit fails because the hook changed files:** this is expected. The hook updated `uv.lock` and stopped the commit so you can include it. In GitHub Desktop, the updated file appears in the Changes list; make sure it is checked and commit again.

### Keeping versions in sync

These must be kept in agreement by hand:

- **Python:** `.python-version` and the base image in the `Dockerfile` (`FROM python:3.13.5-slim-bookworm`) must name the same exact version (currently `3.13.5`). `requires-python` in `pyproject.toml` (`==3.13.*`) must include it; it covers the whole 3.13 series, so a patch upgrade does not require re-locking.
- **uv:** the `rev` in `.pre-commit-config.yaml`, the `ghcr.io/astral-sh/uv` image tag in the `Dockerfile`, and `version` in `.github/workflows/tests.yml` (currently `0.13.0`).
- **Gradio:** pinned only by `gradio==` in `pyproject.toml` (currently `6.30.0`).

Development is on macOS while production runs in a Debian-based Linux container on an x86_64 Ubuntu VPS, so the environments match in Python and package versions but not in operating system or CPU architecture. One practical consequence: macOS file names are case-insensitive by default and Linux file names are case-sensitive, so keep file name casing exact in code.

### Dependency updates

[`.github/dependabot.yml`](../.github/dependabot.yml) has Dependabot open weekly pull requests for:

- **GitHub Actions** used in `.github/workflows/`, updating the pinned commit SHA and its version comment.
- **Python dependencies** in `uv.lock`. Minor and patch updates arrive together in one pull request; each major update (such as pandas 2 to 3) arrives in its own pull request so it can be checked separately. Gradio is ignored, because bumping it is a deliberate change.

The Docker base image is not tracked, because its Python version must change together with `.python-version`.

The tests workflow runs on every Dependabot pull request. To check one locally, check out its branch, then run:

```
uv sync --locked
uv run pytest
uv run python app.py
```

After merging, deploy in Dokploy as usual (see "Deployment"). If a Dependabot branch has been rebased since you last checked it out, replace your local copy with the one on GitHub instead of pulling.

### `.env` file and environment variables

In production, these environment variables are set in the Dokploy application's environment settings (see "Deployment" below). On a development environment, they are managed in a `.env` file **that should never be committed to GitHub**; `.dockerignore` also keeps it out of the Docker image.

1. `AWS_ENDPOINT_URL_S3`: the **region-only** endpoint, `https://<region>.digitaloceanspaces.com`. Do **not** use the Space-specific "origin endpoint" (`https://<space>.<region>.digitaloceanspaces.com`); with it, listing the available dates fails with `NoSuchKey`, so the app refuses an endpoint whose host starts with the Space name.

2. `AWS_DEFAULT_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: region and read-only access key for the Space.

3. `S3_BUCKET_NAME`: name of the DigitalOcean Space (the S3 bucket) that holds all the data.

4. `S3_PORTFOLIO_OPTIMIZATION_FOLDER`: the **top-level folder** inside the Space that holds the portfolio optimization files (e.g. `portfolio-optimization`).

5. `S3_TIME_SERIES_FOLDER`: the **top-level folder** inside the Space that holds the time series forecasts (e.g. `time-series`).

The four `AWS_*` variables use boto3's standard names, like the backend, but they are this app's own settings, not part of the [Interface Contract](INTERFACE_CONTRACT.md). The app reads each one explicitly and passes it to boto3. If any is missing or empty, it does not connect: the log names every missing variable (never a value) and the page shows a message instead of data. boto3 therefore never falls back to other credentials (such as `~/.aws` or a profile) or to AWS's own endpoint. The app loads `.env` with `override=True`, so a local `.env` wins over AWS variables exported in your shell; keep all four in `.env`, because a variable missing from `.env` is still taken from the shell.

Dev and production share the one Space and differ only in the two folder names, so these two variables select the environment. Use the same pair of values as the backend for the same environment.

Older names are no longer read, with no fallback. Before contract v45 the three shared variables were `FSF_FRONT_END_BUCKET_NAME`, `FSF_FRONT_END_PORTFOLIO_OPTIMIZATION_FOLDER`, and `FSF_FRONT_END_TIME_SERIES_FOLDER` (and before v13 the folder variables were `PORTFOLIO_OPTIMIZATION_SPACE_NAME` and `TIME_SERIES_SPACE_NAME`). The credentials were `FSF_FRONT_END_BUCKET_ENDPOINT`, `FSF_FRONT_END_BUCKET_REGION`, `FSF_FRONT_END_BUCKET_READ_ONLY_KEY_ID`, and `FSF_FRONT_END_BUCKET_READ_ONLY`.

## Deployment

The live dashboard, AliciaData Finance, is served at https://aliciadata.com by a self-hosted [Dokploy](https://dokploy.com) instance on a VPS. Deployment is manual; GitHub Actions only runs the tests.

```
 pull request to main ─► GitHub Actions: tests workflow (uv sync --locked, pytest)
                         required to pass by a ruleset before merging
 merge to main
 click Deploy in Dokploy ─► Dokploy pulls main from GitHub
                            builds the Dockerfile on the VPS
                            replaces the running container (one replica)
 visitor ─► https://aliciadata.com ─► Traefik (Let's Encrypt HTTPS)
                                   ─► container, port 7860 ─► Gradio app
```

### Docker image

The [`Dockerfile`](../Dockerfile) builds from `python:3.13.5-slim-bookworm`, copies in uv, installs the production dependencies from `uv.lock` with `uv sync --locked --no-dev --no-install-project`, and copies only `app.py`, `data_loading.py`, and `s3_downloader.py`. The app runs as a non-root user that can write only `input/`, which is a throwaway download cache inside the container (no volume is needed). Gradio listens on `0.0.0.0:7860` (set by `GRADIO_SERVER_NAME` and `GRADIO_SERVER_PORT`). [`.dockerignore`](../.dockerignore) keeps `.env`, `input/`, `.venv/`, the tests, the docs, and other development files out of the build.

### Tests workflow

[`.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs `uv sync --locked` and `uv run pytest` on every pull request to `main` and every push to `main`, with read-only repository permissions and no secrets. Its actions are pinned by full commit SHA. A ruleset on `main` requires the `test` job to pass before a pull request can be merged. The workflow does not deploy: the Dokploy dashboard is reachable only over a private network, not from GitHub.

### Dokploy application settings

- **Source:** Git, `https://github.com/akey7/aliciadata-finance-frontend.git`, branch `main`. Build type Dockerfile, path `Dockerfile`, context `.`. Automatic deployment is off.
- **Environment:** the seven variables listed above, with the **production** folder names.
- **Domain:** `aliciadata.com`, path `/`, container port **7860**, HTTPS with Let's Encrypt. No ports are published directly.
- **Replicas:** 1, because the in-memory cache and Gradio sessions are per process.

### Deploying and rolling back

1. Merge a pull request into `main` after the tests workflow passes.
2. In Dokploy, open the application and click **Deploy**. Follow the build in the deployment log.
3. Check the application log for `Running on local URL: http://0.0.0.0:7860` and the absence of `Could not create the S3 client` or `Missing configuration`, then load https://aliciadata.com.

There is no automatic rollback. To roll back, redeploy an earlier deployment from the application's deployment list in Dokploy, or revert the change on `main` and deploy again.

**Troubleshooting:** if the container keeps restarting with no log output, `docker service ps <service> --no-trunc` on the server shows its exit code, and running the image with `-e PYTHONFAULTHANDLER=1` prints a traceback for crashes such as exit code 132 (illegal instruction).

## Purposes of folders and scripts

### Folders

1. `input/`: Holds input data downloaded from backend, one folder per date: `input/YYYY-MM-DD/<file>`, one folder per date viewed. If it does not exist, `app.py` creates it before access. Files directly in `input/` (from app versions before the date folders) are no longer used and can be deleted.

2. `tests/`: Unit tests for the data loaders (including the optional forecast columns, `all_forecasts_metadata.yml`, and the back test files), the available-date logic, bucket listing, and the app's text describing how forecasts are made. They build synthetic files in a temporary folder or use a fake S3 client, and never touch `input/` or the network. Run them from the repo root with `uv run pytest`.

### Scripts

| Filename           | Standalone Execution? | Purpose                                                                                  |
| ------------------ | --------------------- | ---------------------------------------------------------------------------------------- |
| `app.py`           | Yes                   | Run the AliciaData Finance Frontend Gradio app.                                          |
| `s3_downloader.py` | No                    | Lists folders in the Space and downloads data from it for display on the app.            |
| `data_loading.py`  | No                    | Finds available dates and loads and validates the downloaded files against the [Interface Contract](INTERFACE_CONTRACT.md). |

### Deployment files

| Filename                      | Purpose                                                                                       |
| ----------------------------- | --------------------------------------------------------------------------------------------- |
| `Dockerfile`                  | Builds the production image (see "Deployment").                                               |
| `.dockerignore`               | Keeps secrets, local data, and development files out of the image build.                      |
| `.github/workflows/tests.yml` | Runs the tests on pull requests to `main` and pushes to `main`. Does not deploy.              |
| `.github/dependabot.yml`      | Weekly update pull requests for the GitHub Actions and the Python dependencies (see "Dependency updates"). |
