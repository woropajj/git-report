# git-report

Generates HTML (or PDF) reports of code contributions by a single author for a given month. Pulls diffs directly from git history across all branches.

---

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

Optional — needed for prettier diffs in default mode:

```bash
npm install -g diff2html-cli
```

Optional — needed for PDF output: install Google Chrome, Chromium, or Microsoft Edge. The script defaults to Edge at `/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge`. To use Chrome instead, change `EDGE_PATH` at line 21 of `git-report/generate_report.py`.

---

## Usage

```
python generate_report.py --repo <path> --month <YYYY-MM> [options]
```

### Required arguments

| Argument | Description |
|---|---|
| `--repo <path>` | Path to the target git repository |
| `--month <YYYY-MM>` | Month to report on, e.g. `2026-04` |

### Optional arguments

| Argument | Description |
|---|---|
| `--html-only` | Output an `.html` file instead of PDF. Skips the headless browser step — no Edge/Chrome needed. |
| `--last-state` | Switch to last-state mode (see below). |
| `--include-config` | Also include infra/config files in the report (see below). |

---

## Modes

### Default mode (diff mode)

Shows a unified diff of every commit by the author in the given month, across all branches. Uses `diff2html-cli` to render colorized diffs. Falls back to plain patches if `diff2html-cli` is not installed.

```bash
python generate_report.py \
  --repo /path/to/repo \
  --month 2026-04 \
  --html-only
```

### Last-state mode (`--last-state`)

Instead of a commit-by-commit patch view, shows the end state of each file touched during the month. Files are grouped as:

- **New** — file did not exist before the month; shows full highlighted source
- **Modified** — file existed before and after; shows a per-file diff (before → last commit in month)
- **Deleted** — file existed before the month but was removed; shows the last known source

```bash
python generate_report.py \
  --repo /path/to/repo \
  --month 2026-04 \
  --last-state \
  --html-only
```

---

## File types included

By default only `.py` files are included.

Pass `--include-config` to also include:

| Pattern | Examples |
|---|---|
| `*.yml`, `*.yaml` | GitHub Actions workflows, docker-compose |
| `*Dockerfile*` | `Dockerfile`, `Dockerfile.nginx`, `.devcontainer/Dockerfile` |
| `*.toml` | `pyproject.toml` |
| `*.conf` | nginx, supervisord configs |
| `*.cfg`, `*.ini` | config files |
| `*.json` | `devcontainer.json`, etc. |
| `*.env`, `*.example` | `.env.example` |
| `*.sh`, `*.bash` | shell scripts |
| `.dockerignore`, `.gitignore` | ignore files |

```bash
python generate_report.py \
  --repo /path/to/repo \
  --month 2026-04 \
  --html-only \
  --include-config
```

---

## Output

Reports are written to `output/`. File names follow this pattern:

| Mode | Output file |
|---|---|
| Default (PDF) | `<repo-name>_<YYYY-MM>.pdf` |
| Default (HTML) | `<repo-name>_<YYYY-MM>.html` |
| Last-state (PDF) | `<repo-name>_<YYYY-MM>_last-state.pdf` |
| Last-state (HTML) | `<repo-name>_<YYYY-MM>_last-state.html` |

---

## Common combinations

**Quick check, no external tools needed:**
```bash
python generate_report.py --repo /path/to/repo --month 2026-04 --html-only --include-config
```

**Full report including infra work, last state view:**
```bash
python generate_report.py --repo /path/to/repo --month 2026-04 --last-state --html-only --include-config
```

**PDF output (requires Edge or Chrome):**
```bash
python generate_report.py --repo /path/to/repo --month 2026-04 --include-config
```
