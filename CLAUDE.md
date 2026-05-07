# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Summary
- Small single-purpose Python tool under git-report/ that generates HTML (and attempts PDF) reports of Python contributions by a single hard-coded author.
- Entry point: git-report/generate_report.py

Command-line options
- `--repo` (required): Path to the target git repository.
- `--month` (required): Year and month in YYYY-MM format (e.g. 2026-02).
- `--last-state`: Switch to last-state mode. Shows touched files categorized as new/modified/deleted, with full source or per-file diffs instead of a single commit-patch view.
- `--html-only`: Generate HTML only and skip PDF conversion. Output goes to .html files. Skips Edge/Chrome (no PDF step); diff2html-cli is still required for diff mode.

Common commands
- Create & activate a virtualenv and install runtime deps (macOS / Linux):
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/python -m pip install -r git-report/requirements.txt

- Run the report generator (diff mode, produces PDF):
  .venv/bin/python git-report/generate_report.py --repo /path/to/repo --month 2026-02

- Run diff mode, HTML only (no PDF, no Edge/Chrome needed):
  .venv/bin/python git-report/generate_report.py --repo /path/to/repo --month 2026-02 --html-only

- Run last-state mode (produces PDF):
  .venv/bin/python git-report/generate_report.py --repo /path/to/repo --month 2026-02 --last-state

- Run last-state mode, HTML only (no PDF):
  .venv/bin/python git-report/generate_report.py --repo /path/to/repo --month 2026-02 --last-state --html-only

- Install optional tooling for prettier diffs and PDF conversion (host machine, not Python):
  npm install -g diff2html-cli   # optional: colorized diff HTML (script already tries npx)
  Install Google Chrome/Chromium or Microsoft Edge for headless HTML->PDF printing.

Notes about build / lint / tests
- There is no build step or linter configured in this repo.
- There are currently no unit tests. If pytest is added, run a single test like:
  .venv/bin/pytest tests/path/to/test_file.py::test_function_name

High-level architecture and important files
- git-report/generate_report.py: main program and only substantial module. Key places to look:
  - AUTHOR_NAME constant at git-report/generate_report.py:18 controls which author is filtered.
  - EDGE_PATH at git-report/generate_report.py:21 is the headless browser binary path used for PDF printing.
  - OUTPUT_DIR at git-report/generate_report.py:25 is where HTML/PDF outputs are written (git-report/output/).
  - default_mode(...) (diff-mode) starts at git-report/generate_report.py:110 and runs a git log -p pipeline, then converts the patch into HTML using diff2html-cli (or npx) if available.
  - build_last_state_mode(...) (last-state mode) starts at git-report/generate_report.py:285 and collects touched files, determines added/modified/deleted status, and either highlights source (pygments) or produces per-file diffs.

Runtime dependencies and external tooling
- Python deps: listed in git-report/requirements.txt (pygments). The script imports pygments only when building last-state mode views.
- External tools the script expects (not installed by pip):
  - git (uses subprocess calls extensively)
  - diff2html-cli (optional, installed via npm; script falls back to raw patches when unavailable)
  - A headless browser binary (Edge/Chrome) for PDF printing. The script calls the path in EDGE_PATH (git-report/generate_report.py:21).

Known issues / context (from SESSION_SUMMARY.md)
- Using Edge headless on macOS may require adjusting EDGE_PATH and fixing macOS permissions for the updater/crashpad; Edge headless runs sometimes fail with permission errors (see git-report/SESSION_SUMMARY.md for the exact troubleshooting steps that were tried).
- If PDF generation is required and Edge headless is problematic, prefer pointing EDGE_PATH at Chrome/Chromium, or convert the generated HTML manually or with wkhtmltopdf as an alternative.
- If you want prettier diffs, install diff2html-cli globally or rely on npx (the script already considers several binary names and npx).

Guidance for future Claude Code agents working here
- Prefer small, targeted edits. This repository is dominated by one script; changes should be isolated and explained in the commit message.
- When changing behavior related to PDF conversion or external binaries, update the constant at git-report/generate_report.py:21 and document the reason in git-report/SESSION_SUMMARY.md.
- Avoid committing git-report/.venv (virtual environments). The repo already contains a local .venv used during development.
- If adding tests, put them under a tests/ directory at repo root and include pytest in requirements.txt or pyproject.toml.

Where outputs land
- Generated HTML and PDFs are written to git-report/output/ (see OUTPUT_DIR in git-report/generate_report.py:25).

If you need me to make a specific change (for example, add wkhtmltopdf fallback, change EDGE_PATH to Chrome, or add a pytest skeleton), ask and I will plan the change before implementing it.
