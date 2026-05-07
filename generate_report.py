#!/usr/bin/env python3
"""
Generate HTML or PDF reports of Python code contributions by a single author for a given month.

Follows the specification provided in the handoff document.
Use --html-only to generate HTML without converting to PDF.
"""
import argparse
import calendar
import datetime
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# Hardcoded author name (per spec)
AUTHOR_NAME = "Jakub Woropaj"

# Edge binary path for macOS (per spec)
EDGE_PATH = "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"

# Output directory inside this project
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# Default: only include .py files
PY_GLOBS = ["*.py"]

# Config/infra file patterns (activated by --include-config)
CONFIG_GLOBS = [
    "*.yml",
    "*.yaml",
    "*Dockerfile*",
    "*.toml",
    "*.cfg",
    "*.ini",
    "*.json",
    "*.env",
    "*.sh",
    "*.bash",
    "*.conf",
    # "*.md",
    "*.lock",
    ".dockerignore",
    ".gitignore",
    "*.example",
]

# CSS for simple HTML reports (used for both modes)
BASE_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 24px; }
.header { border-bottom: 1px solid #ddd; margin-bottom: 18px; padding-bottom: 8px; }
.meta { color: #444; }
.commit { margin: 18px 0; padding: 12px; border: 1px solid #eee; background: #fafafa; }
pre.diff { white-space: pre-wrap; font-family: monospace; font-size: 12px; background: #1e1e1e; color: #d4d4d4; padding: 12px; overflow: auto; }
pre.source { background: #f7f7f7; padding: 12px; overflow: auto; }
span.add { color: #073; background: rgba(0,128,0,0.06); display: inline-block; }
span.rem { color: #c00; background: rgba(255,0,0,0.04); display: inline-block; }
.file-header { font-weight: 600; margin-top: 12px; }
.section-title { font-size: 1.05em; font-weight: 700; margin-top: 18px; }
.footer { border-top: 1px solid #ddd; margin-top: 18px; padding-top: 8px; color: #666; font-size: 0.9em; }
.label-new { color: #0a0; font-weight: 700; }
.label-mod { color: #0a58ca; font-weight: 700; }
.label-del { color: #c00; font-weight: 700; }
"""


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def run_git(args: List[str], repo_path: Path, capture_output=True, text=True) -> subprocess.CompletedProcess:
    cmd = ["git"] + args
    try:
        return subprocess.run(cmd, cwd=str(repo_path), capture_output=capture_output, text=text, check=True)
    except subprocess.CalledProcessError as e:
        eprint(f"Git command failed: {' '.join(cmd)}")
        eprint(e.stderr or e.stdout or str(e))
        raise


def validate_repo(repo_path: Path) -> None:
    if not repo_path.exists():
        eprint(f"Repository path does not exist: {repo_path}")
        sys.exit(1)
    if not (repo_path / ".git").exists():
        eprint(f"Not a git repository (missing .git): {repo_path}")
        sys.exit(1)


def parse_month(month_str: str) -> Tuple[datetime.datetime, datetime.datetime]:
    try:
        year, month = month_str.split("-")
        year = int(year)
        month = int(month)
    except Exception:
        eprint("--month must be in YYYY-MM format")
        sys.exit(1)
    first = datetime.datetime(year, month, 1, 0, 0, 0)
    last_day = calendar.monthrange(year, month)[1]
    last = datetime.datetime(year, month, last_day, 23, 59, 59)
    return first, last


def format_header_html(repo_name: str, month: str, mode_label: str) -> str:
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    return f"""
<div class="header">
  <h1>Code Contribution Report</h1>
  <div class="meta">Repository: <strong>{repo_name}</strong> — Author: <strong>{AUTHOR_NAME}</strong> — Month: <strong>{month}</strong> — Mode: <strong>{mode_label}</strong></div>
</div>
"""


def write_pdf_from_html(html_path: Path, pdf_path: Path) -> None:
    # Use Edge headless to print the HTML to PDF
    if not Path(EDGE_PATH).exists():
        eprint(f"Edge binary not found at {EDGE_PATH}. Please install Edge or change EDGE_PATH in the script.")
        sys.exit(1)
    cmd = [EDGE_PATH, "--headless", "--disable-gpu", f"--print-to-pdf={str(pdf_path)}", f"file://{str(html_path)}"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        eprint("Failed to convert HTML to PDF via Edge:")
        eprint(e)
        sys.exit(1)


def default_mode(repo_path: Path, first: datetime.datetime, last: datetime.datetime, repo_name: str, output_path: Path, html_only: bool = False, file_globs: Optional[List[str]] = None) -> None:
    if file_globs is None:
        file_globs = PY_GLOBS
    # Build git log -p for the author and month filtered to file globs, excluding merges
    after = first.strftime("%Y-%m-%d %H:%M:%S")
    before = last.strftime("%Y-%m-%d %H:%M:%S")
    git_args = [
        "log",
        "--all",
        f"--author={AUTHOR_NAME}",
        f"--after={after}",
        f"--before={before}",
        "--no-merges",
        "-p",
        "--date=iso",
        "--",
    ] + file_globs
    try:
        cp = run_git(git_args, repo_path)
    except Exception:
        sys.exit(1)
    git_output = cp.stdout

    if not git_output.strip():
        # No commits -> generate no-commits report
        html = build_no_commits_html(repo_name, first.strftime("%Y-%m"))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if html_only:
            output_path.write_text(html, encoding="utf-8")
            print(f"Wrote: {output_path}")
            return
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as tf:
            tf.write(html)
            tmp_html = Path(tf.name)
        write_pdf_from_html(tmp_html, output_path)
        print(f"Wrote: {output_path}")
        return

    # Try to convert git diff output to pretty HTML using diff2html-cli
    # We'll attempt several binary names. If none present, error out per spec.
    diff2html_binaries = ["diff2html", "diff2html-cli", "npx", "npx.cmd"]
    html_content = None
    for bin_name in diff2html_binaries:
        if bin_name == "npx":
            cmd = ["npx", "diff2html-cli", "-i", "stdin", "-o", "stdout"]
        else:
            cmd = [bin_name, "-i", "stdin", "-o", "stdout"]
        try:
            p = subprocess.run(cmd, input=git_output, capture_output=True, text=True, check=True)
            html_content = p.stdout
            break
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError:
            # If binary exists but fails, continue trying others
            continue

    if html_content is None:
        eprint("diff2html-cli not found or failed. Please install it with: npm install -g diff2html-cli")
        sys.exit(1)

    # Build final HTML: include header and footer around generated body
    header_html = format_header_html(repo_name, first.strftime("%Y-%m"), "Diff Mode")
    full_html = f"<html><head><meta charset=\"utf-8\"><style>{BASE_CSS}</style></head><body>{header_html}{html_content}<div class=\"footer\">Generated: {datetime.datetime.utcnow().isoformat()} UTC</div></body></html>"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if html_only:
        output_path.write_text(full_html, encoding="utf-8")
        print(f"Wrote: {output_path}")
        return
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as tf:
        tf.write(full_html)
        tmp_html = Path(tf.name)
    write_pdf_from_html(tmp_html, output_path)
    print(f"Wrote: {output_path}")


# ---------------- Last-state mode helpers ----------------
from pygments import highlight
from pygments.lexers import PythonLexer, get_lexer_for_filename, TextLexer
from pygments.formatters import HtmlFormatter


def _get_lexer(filename: str):
    """Return a Pygments lexer appropriate for the file, falling back to plain text."""
    try:
        return get_lexer_for_filename(filename)
    except Exception:
        return TextLexer()


def get_touched_files(repo_path: Path, first: datetime.datetime, last: datetime.datetime, file_globs: Optional[List[str]] = None) -> List[str]:
    if file_globs is None:
        file_globs = PY_GLOBS
    after = first.strftime("%Y-%m-%d %H:%M:%S")
    before = last.strftime("%Y-%m-%d %H:%M:%S")
    args = [
        "log",
        "--all",
        f"--author={AUTHOR_NAME}",
        f"--after={after}",
        f"--before={before}",
        "--no-merges",
        "--name-status",
        "--pretty=format:%H",
        "--",
    ] + file_globs
    try:
        cp = run_git(args, repo_path)
    except Exception:
        sys.exit(1)
    lines = cp.stdout.splitlines()
    files = []
    for line in lines:
        if not line.strip():
            continue
        if "\t" in line:
            parts = line.split("\t")
            status = parts[0].strip()
            path = parts[-1].strip()
            files.append(path)
    # deduplicate preserving order
    seen = set()
    uniq = []
    for f in files:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def file_exists_at_commit(repo_path: Path, commit: str, file_path: str) -> bool:
    try:
        run_git(["cat-file", "-e", f"{commit}:{file_path}"], repo_path)
        return True
    except subprocess.CalledProcessError:
        return False


def last_commit_before(repo_path: Path, dt: datetime.datetime, file_path: str) -> Optional[str]:
    # per spec: last commit before the month that touched the file
    before = dt.strftime("%Y-%m-%d %H:%M:%S")
    try:
        cp = run_git(["rev-list", "-1", f"--before={before}", "--all", "--", file_path], repo_path)
        return cp.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def last_commit_in_month_for_file(repo_path: Path, first: datetime.datetime, last: datetime.datetime, file_path: str) -> Optional[str]:
    after = first.strftime("%Y-%m-%d %H:%M:%S")
    before = last.strftime("%Y-%m-%d %H:%M:%S")
    try:
        cp = run_git(["log", "--all", "--author=%s" % AUTHOR_NAME, f"--after={after}", f"--before={before}", "--no-merges", "--pretty=format:%H", "--", file_path], repo_path)
        commits = [l for l in cp.stdout.splitlines() if l.strip()]
        if not commits:
            return None
        # commits are in reverse chronological order; pick first (most recent)
        return commits[0].strip()
    except subprocess.CalledProcessError:
        return None


def get_file_content_at(repo_path: Path, commit: str, file_path: str) -> Optional[str]:
    try:
        cp = run_git(["show", f"{commit}:{file_path}"], repo_path)
        return cp.stdout
    except subprocess.CalledProcessError:
        return None


def build_diff_html_for_file(repo_path: Path, base: str, target: str, file_path: str) -> str:
    # produce a git diff between base and target for the single file
    try:
        cp = run_git(["diff", f"{base}..{target}", "--", file_path], repo_path)
    except subprocess.CalledProcessError:
        return "<pre class=\"diff\">(failed to produce diff)</pre>"
    diff_text = cp.stdout
    # Simple coloring: lines starting with + are green, - are red, others neutral
    html_lines = []
    html_lines.append(f"<div class=\"file-header\">{file_path}</div>")
    html_lines.append('<pre class="diff">')
    for line in diff_text.splitlines():
        esc = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        if line.startswith("+") and not line.startswith("+++"):
            html_lines.append(f"<span class=\"add\">{esc}</span>")
        elif line.startswith("-") and not line.startswith("---"):
            html_lines.append(f"<span class=\"rem\">{esc}</span>")
        else:
            html_lines.append(esc)
    html_lines.append('</pre>')
    return "\n".join(html_lines)


def build_last_state_mode(repo_path: Path, first: datetime.datetime, last: datetime.datetime, repo_name: str, output_path: Path, html_only: bool = False, file_globs: Optional[List[str]] = None) -> None:
    if file_globs is None:
        file_globs = PY_GLOBS
    files = get_touched_files(repo_path, first, last, file_globs)
    if not files:
        html = build_no_commits_html(repo_name, first.strftime("%Y-%m"))
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if html_only:
            output_path.write_text(html, encoding="utf-8")
            print(f"Wrote: {output_path}")
            return
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as tf:
            tf.write(html)
            tmp_html = Path(tf.name)
        write_pdf_from_html(tmp_html, output_path)
        print(f"Wrote: {output_path}")
        return

    new_files = []
    modified_files = []
    deleted_files = []

    for f in files:
        base = last_commit_before(repo_path, first, f)
        last_in_month = last_commit_in_month_for_file(repo_path, first, last, f)
        # if no last_in_month, skip
        if not last_in_month:
            continue
        exists_at_target = file_exists_at_commit(repo_path, last_in_month, f)
        if base is None and exists_at_target:
            new_files.append((f, last_in_month))
        elif base is not None and not exists_at_target:
            # deleted in month
            deleted_files.append((f, base))
        elif base is not None and exists_at_target:
            modified_files.append((f, base, last_in_month))
        else:
            # Fallback: treat as modified
            modified_files.append((f, base or last_in_month, last_in_month))

    # Build HTML
    parts = ["<html><head><meta charset=\"utf-8\"><style>", BASE_CSS, HtmlFormatter().get_style_defs('.highlight'), "</style></head><body>"]
    parts.append(format_header_html(repo_name, first.strftime("%Y-%m"), "Last State Mode"))

    # New files
    if new_files:
        parts.append('<div class="section-title">New files</div>')
        for f, commit in new_files:
            content = get_file_content_at(repo_path, commit, f) or ""
            highlighted = highlight(content, _get_lexer(f), HtmlFormatter(nowrap=True))
            parts.append(f'<div class="file-header">{f} — <span class="label-new">NEW FILE</span></div>')
            parts.append(f'<div class="source">{highlighted}</div>')

    # Modified files
    if modified_files:
        parts.append('<div class="section-title">Modified files</div>')
        for f, base, target in modified_files:
            parts.append(f'<div class="file-header">{f} — <span class="label-mod">MODIFIED</span></div>')
            parts.append(build_diff_html_for_file(repo_path, base, target, f))

    # Deleted files
    if deleted_files:
        parts.append('<div class="section-title">Deleted files</div>')
        for f, base in deleted_files:
            content = get_file_content_at(repo_path, base, f) or ""
            highlighted = highlight(content, _get_lexer(f), HtmlFormatter(nowrap=True))
            parts.append(f'<div class="file-header">{f} — <span class="label-del">DELETED</span></div>')
            parts.append(f'<div class="source">{highlighted}</div>')

    parts.append(f"<div class=\"footer\">Generated: {datetime.datetime.utcnow().isoformat()} UTC</div>")
    parts.append('</body></html>')
    full_html = "\n".join(parts)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if html_only:
        output_path.write_text(full_html, encoding="utf-8")
        print(f"Wrote: {output_path}")
        return
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as tf:
        tf.write(full_html)
        tmp_html = Path(tf.name)
    write_pdf_from_html(tmp_html, output_path)
    print(f"Wrote: {output_path}")


def build_no_commits_html(repo_name: str, month: str) -> str:
    header = format_header_html(repo_name, month, "N/A")
    body = f"<div class=\"section-title\">No commits</div><p>No commits found for this period.</p>"
    footer = f"<div class=\"footer\">Generated: {datetime.datetime.utcnow().isoformat()} UTC</div>"
    return f"<html><head><meta charset=\"utf-8\"><style>{BASE_CSS}</style></head><body>{header}{body}{footer}</body></html>"


def repo_folder_name(repo_path: Path) -> str:
    return repo_path.resolve().name


def main():
    p = argparse.ArgumentParser(description="Generate code contribution PDF reports for a given author and month.")
    p.add_argument("--repo", required=True, help="Path to target git repository")
    p.add_argument("--month", required=True, help="Year and month in YYYY-MM format")
    p.add_argument("--last-state", action="store_true", help="Switch to last-state mode")
    p.add_argument("--html-only", action="store_true", help="Generate HTML only, skip PDF conversion")
    p.add_argument("--include-config", action="store_true", help="Also include config/infra files (.yml, .yaml, Dockerfile, .toml, .cfg, .ini, .json, .env, .sh)")
    args = p.parse_args()

    repo_path = Path(args.repo).expanduser()
    validate_repo(repo_path)

    first, last = parse_month(args.month)
    repo_name = repo_folder_name(repo_path)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ext = ".html" if args.html_only else ".pdf"
    repo_slug = repo_name.lower()
    if args.last_state:
        out_name = f"{first.strftime('%Y-%m')}-tax-relief-jakub-woropaj-{repo_slug}-last-state{ext}"
    else:
        out_name = f"{first.strftime('%Y-%m')}-tax-relief-jakub-woropaj-{repo_slug}{ext}"
    output_path = OUTPUT_DIR / out_name

    file_globs = PY_GLOBS[:]
    if args.include_config:
        file_globs += CONFIG_GLOBS

    try:
        if args.last_state:
            build_last_state_mode(repo_path, first, last, repo_name, output_path, html_only=args.html_only, file_globs=file_globs)
        else:
            default_mode(repo_path, first, last, repo_name, output_path, html_only=args.html_only, file_globs=file_globs)
    except Exception as e:
        eprint("Error:", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
