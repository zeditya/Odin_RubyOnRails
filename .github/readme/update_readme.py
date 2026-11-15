#!/usr/bin/env python3
"""
Rebuild README.md from normal git history.

You do NOT need DONE files, notes, projects.yml, or time tags.
Just make a course folder, put code inside, commit, push.

Course folder names (simple aliases are handled too):
    ruby/  html-css/  databases/  rails/
    advanced-css/  javascript/  react/  job/

Inside a course folder, any subfolder is a "work folder".
The newest work folder is in progress; older ones count as done.

Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import math
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

# ---------------------------------------------------------------------------
# CONFIG — edit only this block if the curriculum changes.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
README_FILE = ROOT / "README.md"
ASSET_DIR = ROOT / ".github" / "readme"
ROADMAP_FILE = ASSET_DIR / "roadmap.svg"
BANNER_FILE = ASSET_DIR / "banner.svg"
BADGES_FILE = ASSET_DIR / "badges.svg"

IST = timezone(timedelta(hours=5, minutes=30))

# Simple, personal heading shown at the top of the README.
DISPLAY_NAME = "Ruby on Rails"
JOURNEY_TITLE = "Learning Journey"
TAGLINE = "The Odin Project · Learning in public · India (IST)"
REPO_DESCRIPTION = "Learning full-stack Ruby on Rails in public, one course at a time."

# TOP Full Stack Ruby on Rails, in order.
# aliases = folder names or words in commit messages that point to this course.
COURSES: list[dict[str, Any]] = [
    {
        "key": "ruby",
        "name": "Ruby",
        "emoji": "💎",
        "aliases": ("ruby", "ruby-basics", "ruby-exercises"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/ruby",
    },
    {
        "key": "html-css",
        "name": "Intermediate HTML and CSS",
        "emoji": "🎨",
        "aliases": ("html-css", "intermediate-html-css", "html", "css"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/intermediate-html-and-css",
    },
    {
        "key": "databases",
        "name": "Databases",
        "emoji": "🗄️",
        "aliases": ("databases", "database", "sql", "postgres", "postgresql", "db"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/databases",
    },
    {
        "key": "rails",
        "name": "Ruby on Rails",
        "emoji": "🛤️",
        "aliases": ("rails", "ruby-on-rails", "ror"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/ruby-on-rails",
    },
    {
        "key": "advanced-css",
        "name": "Advanced HTML and CSS",
        "emoji": "✨",
        "aliases": ("advanced-css", "advanced-html-css", "advanced-html", "animations"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/advanced-html-and-css",
    },
    {
        "key": "javascript",
        "name": "JavaScript",
        "emoji": "⚡",
        "aliases": ("javascript", "js", "java-script"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/javascript",
    },
    {
        "key": "react",
        "name": "React",
        "emoji": "⚛️",
        "aliases": ("react", "react-js"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/react",
    },
    {
        "key": "job",
        "name": "Getting Hired",
        "emoji": "🤝",
        "aliases": ("job", "jobs", "getting-hired", "hired", "career", "interview"),
        "top_url": "https://www.theodinproject.com/paths/full-stack-ruby-on-rails/courses/getting-hired",
    },
]

# Folders that are never treated as course work.
IGNORED_TOP = {".git", ".github", "node_modules", "vendor", "tmp", "log"}
# If a Rails/JS app is directly inside a course folder, these are app internals,
# not separate lessons. They let us keep "rails/app/..." as one work folder.
IGNORED_WORK_SUBDIRS = {
    "app",
    "bin",
    "config",
    "db",
    "lib",
    "log",
    "node_modules",
    "public",
    "spec",
    "storage",
    "test",
    "tests",
    "tmp",
    "vendor",
    "coverage",
}

# Colours used by the animated roadmap image.
STATUS_STYLE = {
    "done": {"fill": "#22c55e", "text": "#4ade80"},
    "active": {"fill": "#8b5cf6", "text": "#c4b5fd"},
    "todo": {"fill": "#475569", "text": "#94a3b8"},
}

MILESTONE_STREAKS = (7, 30, 100)

BOT_NAMES = {"github-actions", "github-actions[bot]"}
BOT_EMAILS = {
    "github-actions[bot]@users.noreply.github.com",
    "41898282+github-actions[bot]@users.noreply.github.com",
}

SECTION_ORDER = [
    "header",
    "about",
    "roadmap",
    "courses",
    "stats",
    "heatmap",
    "recent",
    "milestones",
    "connect",
]

HOURS_RE = re.compile(r"\[(\d+(?:\.\d+)?)\s*h\]", re.IGNORECASE)
FIX_RE = re.compile(r"\bfix(?:es|ed)?\b", re.IGNORECASE)

README_COMMENT = "<!-- README is generated from git history. Push code; do not edit this file. -->"
SECTION_MARKER_RE = re.compile(r"<!--(START|END)_SECTION:([a-z0-9-]+)-->")
CACHE_BUSTER_RE = re.compile(r"roadmap\.svg\?v=([a-f0-9]{8})")
REPO_PART_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
UNSAFE_SVG = ("<script", "<foreignobject", "onload=", "onerror=")
UNSAFE_SVG_RE = re.compile(r"""(?:href|src)\s*=\s*["']\s*javascript:|url\(\s*javascript:""", re.I)

# ---------------------------------------------------------------------------
# SMALL HELPERS
# ---------------------------------------------------------------------------


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def today_ist() -> date:
    override = os.environ.get("ODIN_TODAY")
    if override:
        try:
            return date.fromisoformat(override)
        except ValueError:
            warn(f"ODIN_TODAY is not YYYY-MM-DD: {override!r}")
    return datetime.now(IST).date()


def clean_text(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    return CONTROL_RE.sub("", text).strip()


def fmt_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    return f"{value.day} {value.strftime('%b %Y')}"


def fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return f"{fmt_date(value)} · {value.strftime('%H:%M')} IST"


def fmt_ts(ts: int) -> str:
    value = safe_datetime(ts)
    return fmt_date(value) if value else "—"


def fmt_hours(value: Decimal) -> str:
    if not value.is_finite() or value <= 0:
        return "0"
    if value > Decimal("100000"):
        return "100000+"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def safe_datetime(ts: int) -> datetime | None:
    """Convert a git timestamp without ever raising on extreme values."""
    try:
        value = datetime.fromtimestamp(int(ts), IST)
    except (OverflowError, OSError, ValueError):
        return None
    if not 1970 <= value.year <= 2100:
        return None
    return value


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count} {word}"


def md_cell(value: Any) -> str:
    text = clean_text(value)
    for char in ("\\", "`", "*", "_", "~"):
        text = text.replace(char, "\\" + char)
    text = html.escape(text, quote=False)
    return text.replace("|", "\\|")


def md_text(value: Any) -> str:
    text = clean_text(value)
    for char in ("\\", "`", "*", "_", "~"):
        text = text.replace(char, "\\" + char)
    text = html.escape(text, quote=False)
    return text.replace("[", "\\[").replace("]", "\\]").replace("|", "\\|")


def quote_path(path: str) -> str:
    return quote(clean_text(path), safe="/")


def progress_bar(fraction: float, width: int = 20) -> str:
    if not math.isfinite(fraction):
        fraction = 0.0
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    if fraction >= 0.999:
        filled = width
    return "█" * filled + "░" * (width - filled)


def html_attr(value: Any) -> str:
    return html.escape(CONTROL_RE.sub("", str(value)), quote=True)


def write_atomic(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        if isinstance(text, bytes):
            with open(tmp, "wb") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        else:
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _git_probe(*args: str) -> bool:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_git_repo() -> bool:
    return _git_probe("rev-parse", "--git-dir")


def has_head() -> bool:
    return _git_probe("rev-parse", "--verify", "HEAD")


def run_git(*args: str, quiet: bool = False) -> str:
    command = ["git", "-c", "core.quotePath=false", *args]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "GIT_PAGER": "cat", "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if not quiet:
            warn(f"could not run git: {exc}")
        return ""
    if result.returncode != 0:
        if not quiet and result.stderr.strip():
            warn(f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}")
        return ""
    return result.stdout


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


_GIT_ESCAPES = {
    "a": 7,
    "b": 8,
    "t": 9,
    "n": 10,
    "v": 11,
    "f": 12,
    "r": 13,
    "\\": 92,
    '"': 34,
}


def unquote_git_path(path: str) -> str:
    """Decode the C-style quoting git uses for unusual path names.

    git always quotes paths containing backslashes, quotes, or control
    characters even with core.quotePath=false. Without this, a folder like
    ``rails/back\\slash`` would leak stray quotes into a Markdown table.
    """
    path = path.strip()
    if len(path) < 2 or not (path.startswith('"') and path.endswith('"')):
        return path

    body = path[1:-1]
    data = bytearray()
    index = 0
    while index < len(body):
        char = body[index]
        if char != "\\":
            data.extend(char.encode("utf-8"))
            index += 1
            continue
        index += 1
        if index >= len(body):
            break
        escape = body[index]
        if escape in _GIT_ESCAPES:
            data.append(_GIT_ESCAPES[escape])
            index += 1
        elif escape in "01234567":
            end = index
            while end < len(body) and end < index + 3 and body[end] in "01234567":
                end += 1
            data.append(int(body[index:end], 8) & 0xFF)
            index = end
        else:
            data.extend(escape.encode("utf-8"))
            index += 1
    return data.decode("utf-8", "replace")


def alias_hit(alias: str, text: str) -> bool:
    """Match an alias as a word, never inside another word.

    Without the boundaries, the Rails alias "ror" would match "error" and the
    React alias "react" would match "reaction".
    """
    if not alias:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", text) is not None


def match_course(*texts: str) -> dict[str, Any] | None:
    """Find a course from a folder name or commit message. Folder wins."""
    normalized = [normalize_text(text) for text in texts if text]

    # Exact alias first: advanced-css must not fall into html-css.
    for text in normalized:
        for course in COURSES:
            if text == course["key"] or text in course["aliases"]:
                return course

    # Otherwise the longest alias wins: "ruby-on-rails" -> Rails, not Ruby.
    candidates: list[tuple[int, dict[str, Any]]] = []
    for text in normalized:
        for course in COURSES:
            for alias in course["aliases"]:
                if alias_hit(normalize_text(alias), text):
                    candidates.append((len(alias), course))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


# ---------------------------------------------------------------------------
# DATA MODEL
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Commit:
    sha: str
    ts: int
    dt: datetime
    subject: str
    files: tuple[str, ...]


@dataclass
class WorkFolder:
    rel: str
    course_key: str | None
    last_ts: int


@dataclass
class Course:
    index: int
    cfg: dict[str, Any]
    path: Path | None
    commits: set[str] = field(default_factory=set)
    folders: dict[str, int] = field(default_factory=dict)
    last_ts: int = 0
    status: str = "todo"
    progress: float = 0.0
    done_folders: int = 0
    total_folders: int = 0

    @property
    def name(self) -> str:
        return str(self.cfg["name"])

    @property
    def emoji(self) -> str:
        return str(self.cfg["emoji"])

    @property
    def top_url(self) -> str:
        return str(self.cfg["top_url"])

    @property
    def rel(self) -> str:
        return self.path.relative_to(ROOT).as_posix() if self.path else ""


@dataclass
class Stats:
    total_commits: int
    active_days: int
    current_streak: int
    best_streak: int
    study_hours: Decimal
    fixes: int
    last_dt: datetime | None
    date_counts: Counter[date]


@dataclass
class State:
    today: date
    repo_owner: str
    repo_name: str
    commits: list[Commit]
    courses: list[Course]
    work_folders: list[WorkFolder]
    stats: Stats
    critical_error: bool = False
    roadmap_version: str = ""
    banner_version: str = ""
    badges_version: str = ""
    branch: str = "main"

    @property
    def courses_done(self) -> int:
        return sum(1 for course in self.courses if course.status == "done")

# ---------------------------------------------------------------------------
# READ GIT
# ---------------------------------------------------------------------------


def detect_repo() -> tuple[str, str]:
    """Owner and repo name from Actions env, else the git remote."""
    env_repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in env_repo:
        owner, name = env_repo.split("/", 1)
        if REPO_PART_RE.match(owner) and REPO_PART_RE.match(name):
            return owner, name

    remote = run_git("remote", "get-url", "origin", quiet=True).strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
    if match:
        owner, name = match.group(1), match.group(2)
        if REPO_PART_RE.match(owner) and REPO_PART_RE.match(name):
            return owner, name

    return "zeditya", "Odin_RubyOnRails"


def detect_branch() -> str:
    """Default branch for raw image URLs, from Actions env or git."""
    env_branch = os.environ.get("GITHUB_REF_NAME", "").strip()
    if env_branch and re.fullmatch(r"[A-Za-z0-9._/-]+", env_branch) and ".." not in env_branch:
        return env_branch

    branch = run_git("branch", "--show-current", quiet=True).strip()
    if branch and re.fullmatch(r"[A-Za-z0-9._/-]+", branch) and ".." not in branch:
        return branch

    return "main"


def load_commits() -> list[Commit]:
    if not is_git_repo():
        raise RuntimeError("not a git repository")
    if not has_head():
        return []  # fresh repo: show zeros, not an error

    raw = run_git(
        "log",
        "--pretty=format:%x1e%H%x1f%at%x1f%an%x1f%ae%x1f%s",
        "--name-only",
        "HEAD",
        quiet=True,
    )
    if not raw.strip():
        raise RuntimeError("git log returned no data")

    commits: list[Commit] = []
    for chunk in raw.split("\x1e"):
        chunk = chunk.lstrip("\n")
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        header = lines[0].split("\x1f")
        if len(header) < 5:
            continue
        sha, ts_raw, author_name, author_email = header[:4]
        subject = "\x1f".join(header[4:])
        if (
            author_name.strip() in BOT_NAMES
            or author_email.strip().lower() in BOT_EMAILS
            or subject.startswith("docs: auto-update README")
        ):
            continue
        try:
            ts = int(ts_raw)
        except (TypeError, ValueError):
            continue
        dt = safe_datetime(ts)
        if dt is None:
            continue
        files = tuple(unquote_git_path(line) for line in lines[1:] if line.strip())
        commits.append(
            Commit(
                sha=sha,
                ts=ts,
                dt=dt,
                subject=subject,
                files=files,
            )
        )
    commits.sort(key=lambda commit: commit.ts, reverse=True)
    return commits


def work_folder_for(path: str) -> str | None:
    """rails/blog-app/app/models/user.rb -> rails/blog-app; ruby/a.rb -> ruby."""
    parts = path.split("/")
    if len(parts) < 2:
        return None  # root-level file, not daily code
    if parts[0].startswith(".") or parts[0] in IGNORED_TOP:
        return None
    if len(parts) >= 3 and parts[1].lower() not in IGNORED_WORK_SUBDIRS:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def discover_state(commits: list[Commit], today: date, owner: str, name: str) -> State:
    courses = [
        Course(index=index, cfg=cfg, path=None)
        for index, cfg in enumerate(COURSES)
    ]
    by_key = {course.cfg["key"]: course for course in courses}

    # Find course folders at the root, even if they have no commits yet.
    try:
        root_dirs = sorted(
            (path for path in ROOT.iterdir() if path.is_dir()),
            key=lambda path: path.name.lower(),
        )
    except OSError as exc:
        raise RuntimeError(f"could not scan repo root: {exc}") from exc

    for path in root_dirs:
        if path.name.startswith(".") or path.name in IGNORED_TOP:
            continue
        course_cfg = match_course(path.name)
        if course_cfg:
            course = by_key[course_cfg["key"]]
            if course.path is None:
                course.path = path

    folder_map: dict[str, WorkFolder] = {}
    for commit in commits:  # newest first
        for path in commit.files:
            rel = work_folder_for(path)
            if rel is None:
                continue
            top = rel.split("/")[0]
            course_cfg = match_course(top) or match_course(commit.subject)
            course_key = str(course_cfg["key"]) if course_cfg else None

            existing = folder_map.get(rel)
            if existing is None:
                folder_map[rel] = WorkFolder(rel=rel, course_key=course_key, last_ts=commit.ts)
            elif course_key and not existing.course_key:
                existing.course_key = course_key

            if course_key:
                course = by_key[course_key]
                course.commits.add(commit.sha)
                course.folders[rel] = max(course.folders.get(rel, 0), commit.ts)
                course.last_ts = max(course.last_ts, commit.ts)

    # The highest course with activity is "current". Earlier active courses are done.
    active = [course for course in courses if course.commits]
    frontier = max((course.index for course in active), default=-1)
    for course in courses:
        course.total_folders = len(course.folders)
        if course.index == frontier:
            course.status = "active"
            done = max(course.total_folders - 1, 0)
            course.done_folders = done
            course.progress = done / course.total_folders if course.total_folders else 0.0
        elif course.index < frontier:
            # The curriculum is linear: once you are further along, everything
            # before your current course counts as done, even if you skipped a
            # folder for it.
            course.status = "done"
            course.done_folders = course.total_folders
            course.progress = 1.0
        else:
            course.status = "todo"
            course.done_folders = 0
            course.progress = 0.0

    date_counts = Counter(commit.dt.date() for commit in commits)
    hours = Decimal("0")
    for commit in commits:
        for match in HOURS_RE.findall(commit.subject):
            try:
                hours += Decimal(match)
            except InvalidOperation:
                pass

    anchor: date | None = None
    if today in date_counts:
        anchor = today
    elif today - timedelta(days=1) in date_counts:
        anchor = today - timedelta(days=1)
    current_streak = 0
    if anchor:
        cursor = anchor
        while cursor in date_counts:
            current_streak += 1
            cursor -= timedelta(days=1)

    best = 0
    run = 0
    previous: date | None = None
    for day in sorted(date_counts):
        run = run + 1 if previous and (day - previous).days == 1 else 1
        best = max(best, run)
        previous = day

    stats = Stats(
        total_commits=len(commits),
        active_days=len(date_counts),
        current_streak=current_streak,
        best_streak=best,
        study_hours=hours,
        fixes=sum(1 for commit in commits if FIX_RE.search(commit.subject)),
        last_dt=commits[0].dt if commits else None,
        date_counts=date_counts,
    )

    folders = sorted(folder_map.values(), key=lambda item: (-item.last_ts, item.rel))
    return State(
        today=today,
        repo_owner=owner,
        repo_name=name,
        commits=commits,
        courses=courses,
        work_folders=folders,
        stats=stats,
    )

def build_state() -> State:
    owner, name = detect_repo()
    today = today_ist()
    branch = detect_branch()
    try:
        commits = load_commits()
    except Exception as exc:
        warn(f"could not read git history: {exc}")
        state = State(
            today=today,
            repo_owner=owner,
            repo_name=name,
            commits=[],
            courses=[Course(index=index, cfg=cfg, path=None) for index, cfg in enumerate(COURSES)],
            work_folders=[],
            stats=Stats(0, 0, 0, 0, Decimal("0"), 0, None, Counter()),
            critical_error=True,
            branch=branch,
        )
        return state

    try:
        state = discover_state(commits, today, owner, name)
        state.branch = branch
    except Exception as exc:
        warn(f"could not read course folders: {exc}")
        state = State(
            today=today,
            repo_owner=owner,
            repo_name=name,
            commits=[],
            courses=[Course(index=index, cfg=cfg, path=None) for index, cfg in enumerate(COURSES)],
            work_folders=[],
            stats=Stats(0, 0, 0, 0, Decimal("0"), 0, None, Counter()),
            critical_error=True,
            branch=branch,
        )
        return state

    return state

# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------


def asset_url(state: State, filename: str, version: str) -> str:
    return (
        f"https://raw.githubusercontent.com/{state.repo_owner}/{state.repo_name}"
        f"/{state.branch}/.github/readme/{filename}?v={version}"
    )


def build_banner_svg(state: State) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="200" viewBox="0 0 1200 200" role="img" aria-labelledby="bannerTitle bannerDesc" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif">
  <title id="bannerTitle">{html_attr(DISPLAY_NAME)}</title>
  <desc id="bannerDesc">{html_attr(TAGLINE)}</desc>
  <defs>
    <linearGradient id="bannerBg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0f172a" />
      <stop offset="50%" stop-color="#5b21b6" />
      <stop offset="100%" stop-color="#1d4ed8" />
    </linearGradient>
    <radialGradient id="bannerHalo" cx="18%" cy="10%" r="70%">
      <stop offset="0%" stop-color="#c4b5fd" stop-opacity="0.42" />
      <stop offset="100%" stop-color="#c4b5fd" stop-opacity="0" />
    </radialGradient>
    <pattern id="bannerDots" width="24" height="24" patternUnits="userSpaceOnUse">
      <circle cx="1.5" cy="1.5" r="1" fill="#ffffff" fill-opacity="0.06" />
    </pattern>
    <filter id="bannerBlur" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="18" />
    </filter>
    <clipPath id="bannerFrame">
      <rect width="1200" height="200" rx="0" />
    </clipPath>
  </defs>
  <g clip-path="url(#bannerFrame)">
    <rect width="1200" height="200" fill="url(#bannerBg)" />
    <rect width="1200" height="200" fill="url(#bannerDots)" />
    <rect width="1200" height="200" fill="url(#bannerHalo)" />
    <circle cx="120" cy="40" r="70" fill="#8b5cf6" opacity="0.35" filter="url(#bannerBlur)">
      <animate attributeName="opacity" values="0.35;0.6;0.35" dur="6s" repeatCount="indefinite" />
    </circle>
    <circle cx="1080" cy="180" r="90" fill="#38bdf8" opacity="0.22" filter="url(#bannerBlur)">
      <animate attributeName="opacity" values="0.22;0.45;0.22" dur="7s" repeatCount="indefinite" />
    </circle>
    <text x="600" y="103" text-anchor="middle" font-size="54" font-weight="800" letter-spacing="1" fill="#ffffff">{html_attr(DISPLAY_NAME)}</text>
    <text x="600" y="146" text-anchor="middle" font-size="17" fill="#ddd6fe">{html_attr(TAGLINE)}</text>
  </g>
  <rect x="1" y="1" width="1198" height="198" fill="none" stroke="#ffffff" stroke-opacity="0.14" />
</svg>
'''


def badge_width(label: str, value: str) -> int:
    return 64 + int(len(label) * 8.0 + len(value) * 9.0)


def build_badges_svg(state: State) -> str:
    stats = state.stats
    total = len(state.courses)
    done = state.courses_done
    last = fmt_date(stats.last_dt)
    items = [
        ("courses", f"{done}/{total}", "#8b5cf6"),
        ("streak", plural(stats.current_streak, "day"), "#3b82f6"),
        ("commits", str(stats.total_commits), "#14b8a6"),
        ("latest", last, "#64748b"),
    ]
    widths = [badge_width(label, value) for label, value, _ in items]
    gap = 12
    total_width = sum(widths) + gap * (len(items) - 1)
    svg_width = max(760, total_width + 24)
    x = max(12, (svg_width - total_width) // 2)
    y = 8
    height = 40
    pieces = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="56" viewBox="0 0 {svg_width} 56" role="img" aria-labelledby="badgesTitle badgesDesc" font-family="system-ui, -apple-system, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif">',
        f'  <title id="badgesTitle">Learning stats</title>',
        f'  <desc id="badgesDesc">{html_attr(f"{done} of {total} courses · {plural(stats.current_streak, 'day')} streak · {plural(stats.total_commits, 'commit')} · last {last}")}</desc>',
    ]
    for (label, value, color), width in zip(items, widths):
        pieces.extend(
            [
                f'  <g transform="translate({x}, {y})">',
                f'    <rect width="{width}" height="{height}" rx="20" fill="#111827" stroke="#334155" />',
                f'    <circle cx="20" cy="{height // 2}" r="4" fill="{color}">',
                '      <animate attributeName="opacity" values="1;0.35;1" dur="2.6s" repeatCount="indefinite" />',
                "    </circle>",
                f'    <text x="32" y="25" font-size="12" font-weight="700" letter-spacing="1" fill="#94a3b8">{html_attr(label.upper())}</text>',
                f'    <text x="{width - 16}" y="25" text-anchor="end" font-size="14" font-weight="700" fill="#f8fafc">{html_attr(value)}</text>',
                "  </g>",
            ]
        )
        x += width + gap
    pieces.append("</svg>")
    return "\n".join(pieces) + "\n"


def fallback_banner_svg(state: State) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="200" viewBox="0 0 1200 200" role="img" aria-labelledby="bannerTitle bannerDesc">
  <title id="bannerTitle">{html_attr(DISPLAY_NAME)}</title>
  <desc id="bannerDesc">{html_attr(TAGLINE)}</desc>
  <rect width="1200" height="200" fill="#111827" />
  <text x="600" y="103" text-anchor="middle" font-size="54" font-weight="800" fill="#ffffff">{html_attr(DISPLAY_NAME)}</text>
  <text x="600" y="146" text-anchor="middle" font-size="17" fill="#cbd5e1">{html_attr(TAGLINE)}</text>
</svg>
'''


def fallback_badges_svg(state: State) -> str:
    stats = state.stats
    text = f"{state.courses_done} of {len(state.courses)} courses · {plural(stats.current_streak, 'day')} streak · {plural(stats.total_commits, 'commit')}"
    label = f"COURSES {state.courses_done}/{len(state.courses)} · STREAK {plural(stats.current_streak, 'day')} · COMMITS {stats.total_commits}"
    width = max(760, 48 + int(len(label) * 9.2))
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="56" viewBox="0 0 {width} 56" role="img" aria-labelledby="badgesTitle badgesDesc">
  <title id="badgesTitle">Learning stats</title>
  <desc id="badgesDesc">{html_attr(text)}</desc>
  <text x="{width // 2}" y="35" text-anchor="middle" font-size="16" fill="#cbd5e1">{html_attr(label)}</text>
</svg>
'''


def section_header(state: State) -> str:
    stats = state.stats
    total = len(state.courses)
    done = state.courses_done
    last = fmt_date(stats.last_dt)
    title = JOURNEY_TITLE

    if not state.banner_version or not state.badges_version:
        raise RuntimeError("header images are unavailable")

    banner = asset_url(state, "banner.svg", state.banner_version)
    badges = asset_url(state, "badges.svg", state.badges_version)
    badge_alt = (
        f"Badge: {done} of {total} courses done · "
        f"{plural(stats.current_streak, 'day')} streak · "
        f"{plural(stats.total_commits, 'commit')} · last commit {last}"
    )

    active = next((course for course in state.courses if course.status == "active"), None)
    focus = f"{active.emoji} {active.name}" if active else "Getting started"

    lines = [
        '<p align="center">',
        f'  <img src="{html_attr(banner)}" alt="Banner: {html_attr(DISPLAY_NAME)}" width="100%" />',
        "</p>",
        "",
        f'<h1 align="center">{html.escape(title)}</h1>',
        "",
        f'<p align="center"><sub>{html.escape(TAGLINE)}</sub></p>',
        "",
        f'<p align="center">{html.escape(REPO_DESCRIPTION)}</p>',
        "",
        '<p align="center">',
        f'  <img src="{html_attr(badges)}" alt="{html_attr(badge_alt)}" width="100%" />',
        "</p>",
        "",
        '<p align="center">',
        f"  <strong>Currently learning:</strong> {md_text(focus)}<br />",
        f"  <sub>Last commit: {md_text(fmt_datetime(stats.last_dt))}</sub>",
        "</p>",
    ]
    return "\n".join(lines)


def section_about(state: State) -> str:
    return "\n".join(
        [
            "## About",
            "",
            "I am learning software development for the first time, in public, "
            "through the [Full Stack Ruby on Rails]"
            "(https://www.theodinproject.com/paths/full-stack-ruby-on-rails) "
            "path at The Odin Project. Everything in this repository is real "
            "practice: course folders, working code, and progress generated "
            "from the git history itself.",
            "",
            "### Why Ruby on Rails instead of MERN?",
            "",
            "I chose Rails deliberately. This is my first serious track, and I "
            "want to spend my time building complete, working products rather "
            "than assembling a stack from many separate pieces. Rails is "
            "opinionated and batteries-included: routing, the database layer, "
            "and the front-end conventions are already in place, so I can move "
            "from an idea to a deployed application much faster and start "
            "building real projects, and pursuing opportunities, sooner.",
            "",
            "MERN is a strong ecosystem, but it asks a beginner to make many "
            "architectural decisions up front. I would rather learn one "
            "coherent framework deeply first.",
            "",
            "### The plan",
            "",
            "I will stay on the Ruby on Rails track until I am genuinely strong "
            "in it. After that, I will pivot to the JavaScript track (Node, "
            "React, and the wider JS ecosystem) and add that stack on top of "
            "solid fundamentals. Depth first, breadth second.",
            "",
            "Happy building. 🚀",
        ]
    )


def svg_num(value: float) -> str:
    text = f"{value:.1f}"
    return text[:-2] if text.endswith(".0") else text


def build_roadmap_svg(state: State) -> str:
    """Build a self-contained animated SVG roadmap.

    The animation uses SMIL only (no scripts, no external assets), so GitHub can
    render it inside a normal README image tag.
    """
    total = len(state.courses)
    done = state.courses_done
    width = 1200
    center_x, top, step = 600, 150, 95
    node_xs = (440, 760)
    points = [(node_xs[index % 2], top + index * step) for index in range(total)]
    # Grow the canvas with the curriculum so no node or label can ever clip.
    height = max(920, top + max(total - 1, 0) * step + 104)
    tail_y = height - 55
    legend_y = height - 42

    route = f"M {center_x} 90"
    prev_x, prev_y = center_x, 90
    for x, y in points:
        dy = y - prev_y
        route += (
            f" C {svg_num(prev_x)} {svg_num(prev_y + dy * 0.45)},"
            f" {svg_num(x)} {svg_num(y - dy * 0.45)}, {svg_num(x)} {svg_num(y)}"
        )
        prev_x, prev_y = x, y
    dy = tail_y - prev_y
    route += (
        f" C {svg_num(prev_x)} {svg_num(prev_y + dy * 0.45)},"
        f" {svg_num(center_x)} {svg_num(tail_y - dy * 0.45)}, {center_x} {tail_y}"
    )

    if total and done == total:
        stops = [(0, "#22c55e"), (100, "#4ade80")]
    elif done:
        active = next((course for course in state.courses if course.status == "active"), None)
        frontier = (active.index if active else total - 1) / max(total - 1, 1)
        stops = [
            (0, "#22c55e"),
            (int(max(8, min(92, frontier * 100))), "#8b5cf6"),
            (100, "#334155"),
        ]
    else:
        stops = [(0, "#6366f1"), (55, "#8b5cf6"), (100, "#334155")]
    gradient_stops = "\n".join(
        f'      <stop offset="{offset}%" stop-color="{color}" />'
        for offset, color in stops
    )

    status_words = {"done": "done", "active": "in progress", "todo": "not started"}
    description = ". ".join(
        f"{course.name}: {status_words[course.status]}" for course in state.courses
    )

    nodes: list[str] = []
    for index, course in enumerate(state.courses):
        x, y = points[index]
        style = STATUS_STYLE[course.status]
        label_right = index % 2 == 1
        label_x = 820 if label_right else 380
        anchor = "start" if label_right else "end"
        name_fill = "#f8fafc" if course.status != "todo" else "#94a3b8"
        # Keep long titles inside the label column instead of overlapping.
        name_size = 20 if len(course.name) <= 28 else max(12, int(20 * 28 / max(len(course.name), 1)))

        if course.status == "done":
            status_label = "COMPLETE"
            progress_text = "100% · complete"
        elif course.status == "active":
            status_label = "IN PROGRESS"
            folder_word = "folder" if course.total_folders == 1 else "folders"
            progress_text = (
                f"{int(round(course.progress * 100))}% · "
                f"{course.done_folders} of {course.total_folders} {folder_word} done"
            )
        else:
            status_label = "NOT STARTED"
            progress_text = "0%"

        parts = [
            f'    <circle cx="{x}" cy="{y}" r="30" fill="{style["fill"]}" opacity="0.12" filter="url(#blur)" />'
        ]
        if course.status == "active":
            parts.extend(
                [
                    f'    <circle cx="{x}" cy="{y}" r="20" fill="none" stroke="{style["fill"]}" stroke-width="2">',
                    '      <animate attributeName="r" values="20;36;20" dur="3s" repeatCount="indefinite" />',
                    '      <animate attributeName="opacity" values="0.65;0;0.65" dur="3s" repeatCount="indefinite" />',
                    "    </circle>",
                    f'    <circle cx="{x}" cy="{y}" r="29" fill="none" stroke="{style["text"]}" stroke-width="1.3" stroke-dasharray="4 7" opacity="0.55">',
                    f'      <animateTransform attributeName="transform" type="rotate" from="0 {x} {y}" to="360 {x} {y}" dur="14s" repeatCount="indefinite" />',
                    "    </circle>",
                ]
            )
        parts.extend(
            [
                f'    <circle cx="{x}" cy="{y}" r="20" fill="#0b1120" stroke="{style["fill"]}" stroke-width="3" />',
                f'    <circle cx="{x}" cy="{y}" r="13" fill="{style["fill"]}" />',
            ]
        )
        if course.status == "done":
            parts.append(
                f'    <path d="M {x - 7} {y} L {x - 2} {y + 5} L {x + 8} {y - 6}" fill="none" stroke="#ffffff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />'
            )
        elif course.status == "active":
            parts.append(
                f'    <path d="M {x - 4} {y - 6} L {x + 6} {y} L {x - 4} {y + 6} Z" fill="#ffffff" />'
            )
        else:
            parts.append(
                f'    <text x="{x}" y="{y + 4}" text-anchor="middle" font-size="12" font-weight="700" fill="#cbd5e1">{index + 1}</text>'
            )

        parts.extend(
            [
                f'    <text x="{label_x}" y="{y - 16}" text-anchor="{anchor}" font-size="{name_size}" font-weight="700" fill="{name_fill}">{html_attr(course.name)}</text>',
                f'    <text x="{label_x}" y="{y + 6}" text-anchor="{anchor}" font-size="11.5" font-weight="700" letter-spacing="1.4" fill="{style["text"]}">{status_label}</text>',
                f'    <text x="{label_x}" y="{y + 28}" text-anchor="{anchor}" font-size="13" fill="#94a3b8">{progress_text}</text>',
            ]
        )
        if course.status == "active":
            bar_x = label_x - 180 if anchor == "end" else label_x
            bar_width = 180 * max(0.0, min(1.0, course.progress))
            parts.extend(
                [
                    f'    <rect x="{bar_x}" y="{y + 38}" width="180" height="6" rx="3" fill="#1e293b" />',
                    f'    <rect x="{bar_x}" y="{y + 38}" width="{svg_num(bar_width)}" height="6" rx="3" fill="url(#barGradient)">',
                    f'      <animate attributeName="width" from="0" to="{svg_num(bar_width)}" dur="1.2s" fill="freeze" />',
                    "    </rect>",
                ]
            )
        nodes.append("\n".join(parts))

    header = f'''    <text x="60" y="54" font-size="22" font-weight="700" fill="#f8fafc">Full Stack Ruby on Rails</text>
    <text x="60" y="80" font-size="14" fill="#94a3b8">{total} courses · {done} complete</text>
    <g>
      <rect x="1002" y="30" width="138" height="34" rx="17" fill="#111827" stroke="#334155" />
      <circle cx="1024" cy="47" r="4" fill="#a78bfa">
        <animate attributeName="opacity" values="1;0.25;1" dur="2s" repeatCount="indefinite" />
      </circle>
      <text x="1038" y="52" font-size="12" font-weight="700" letter-spacing="2" fill="#c4b5fd">ROADMAP</text>
    </g>'''

    legend = f'''    <g transform="translate(60, {legend_y})">
      <circle cx="6" cy="-4" r="5" fill="#22c55e" />
      <text x="18" y="0" font-size="13" fill="#94a3b8">Done</text>
      <circle cx="106" cy="-4" r="5" fill="#8b5cf6">
        <animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <text x="118" y="0" font-size="13" fill="#94a3b8">In progress</text>
      <circle cx="236" cy="-4" r="5" fill="#475569" />
      <text x="248" y="0" font-size="13" fill="#94a3b8">Not started</text>
    </g>
    <text x="1140" y="{legend_y}" text-anchor="end" font-size="13" fill="#64748b">{done} / {total} courses complete</text>'''

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="roadmapTitle roadmapDesc" font-family="system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif">
  <title id="roadmapTitle">Animated roadmap for the Full Stack Ruby on Rails path</title>
  <desc id="roadmapDesc">{html_attr(description)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1120" />
      <stop offset="55%" stop-color="#111827" />
      <stop offset="100%" stop-color="#1e1b4b" />
    </linearGradient>
    <radialGradient id="halo" cx="75%" cy="15%" r="65%">
      <stop offset="0%" stop-color="#6d28d9" stop-opacity="0.35" />
      <stop offset="100%" stop-color="#6d28d9" stop-opacity="0" />
    </radialGradient>
    <linearGradient id="routeGradient" gradientUnits="userSpaceOnUse" x1="0" y1="90" x2="0" y2="{tail_y}">
{gradient_stops}
    </linearGradient>
    <linearGradient id="barGradient" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#8b5cf6" />
      <stop offset="100%" stop-color="#c4b5fd" />
    </linearGradient>
    <pattern id="dots" width="26" height="26" patternUnits="userSpaceOnUse">
      <circle cx="1.5" cy="1.5" r="1.1" fill="#ffffff" fill-opacity="0.035" />
    </pattern>
    <filter id="blur" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="8" />
    </filter>
    <filter id="glow" x="-100%" y="-100%" width="300%" height="300%">
      <feGaussianBlur stdDeviation="3" result="blurred" />
      <feMerge>
        <feMergeNode in="blurred" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
    <clipPath id="frame">
      <rect width="{width}" height="{height}" rx="26" />
    </clipPath>
  </defs>
  <g clip-path="url(#frame)">
    <rect width="{width}" height="{height}" rx="26" fill="url(#bg)" />
    <rect width="{width}" height="{height}" rx="26" fill="url(#dots)" />
    <rect width="{width}" height="{height}" rx="26" fill="url(#halo)" />
    <path d="{route}" fill="none" stroke="#8b5cf6" stroke-width="18" opacity="0.12" filter="url(#blur)" />
    <path id="route" d="{route}" fill="none" stroke="url(#routeGradient)" stroke-width="4" stroke-linecap="round" />
    <path d="{route}" fill="none" stroke="#e2e8f0" stroke-width="2.5" stroke-dasharray="8 14" opacity="0.35" stroke-linecap="round">
      <animate attributeName="stroke-dashoffset" values="0;-44" dur="1.4s" repeatCount="indefinite" />
    </path>
    <g>
      <circle r="14" fill="#a78bfa" opacity="0.2" filter="url(#blur)" />
      <circle r="5" fill="#e9d5ff" filter="url(#glow)" />
      <animateMotion dur="10s" repeatCount="indefinite" rotate="auto">
        <mpath xlink:href="#route" />
      </animateMotion>
    </g>
{chr(10).join(nodes)}
{header}
{legend}
  </g>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="25" fill="none" stroke="#334155" stroke-opacity="0.7" stroke-width="1.5" />
</svg>
'''


def write_roadmap(state: State) -> str:
    svg = build_roadmap_svg(state)
    write_atomic(ROADMAP_FILE, svg)
    return hashlib.sha256(svg.encode("utf-8")).hexdigest()[:8]


def section_roadmap(state: State) -> str:
    if not state.roadmap_version:
        raise RuntimeError("roadmap image is unavailable")
    src = (
        f"https://raw.githubusercontent.com/{state.repo_owner}/{state.repo_name}"
        f"/{state.branch}/.github/readme/roadmap.svg?v={state.roadmap_version}"
    )
    alt = (
        "Animated roadmap for the Full Stack Ruby on Rails path: "
        f"{state.courses_done} of {len(state.courses)} courses complete."
    )
    return "\n".join(
        [
            "## Roadmap",
            "",
            '<p align="center">',
            f'  <img src="{html_attr(src)}" alt="{html_attr(alt)}" width="100%" />',
            "</p>",
        ]
    )


def section_courses(state: State) -> str:
    labels = {"done": "✅ Done", "active": "🚧 In progress", "todo": "⬜ Not started"}
    lines = [
        "## Course Progress",
        "",
        "| Course | Status | Work | Progress |",
        "|:--|:--:|:--|:--|",
    ]
    for course in state.courses:
        if course.path:
            name = f"[{course.emoji} **{md_text(course.name)}**]({quote_path(course.rel)})"
        else:
            name = f"[{course.emoji} **{md_text(course.name)}**]({course.top_url})"

        if course.commits:
            commits_word = "commit" if len(course.commits) == 1 else "commits"
            folders_word = "folder" if course.total_folders == 1 else "folders"
            work = (
                f"**{len(course.commits)}** {commits_word} · "
                f"**{course.total_folders}** {folders_word}"
                f"<br><sub>last {fmt_ts(course.last_ts)}</sub>"
            )
        else:
            work = "—"

        if course.status == "done":
            progress = f"`{progress_bar(1)}` 100%<br><sub>complete</sub>"
        elif course.status == "active":
            folder_word = "folder" if course.total_folders == 1 else "folders"
            progress = (
                f"`{progress_bar(course.progress)}` {int(round(course.progress * 100))}%"
                f"<br><sub>{course.done_folders} / {course.total_folders} {folder_word} done</sub>"
            )
        else:
            progress = f"`{progress_bar(0)}` 0%"

        lines.append(f"| {name} | {labels[course.status]} | {work} | {progress} |")

    lines.extend(
        [
            "",
            "<sub>The newest folder in a course is in progress; older folders count as done. "
            "Courses before your current course are done.</sub>",
        ]
    )
    return "\n".join(lines)


def section_stats(state: State) -> str:
    stats = state.stats
    return "\n".join(
        [
            "## Stats",
            "",
            "| Current streak | Best streak | Active days |",
            "|:---:|:---:|:---:|",
            f"| **{plural(stats.current_streak, 'day')}** | **{plural(stats.best_streak, 'day')}** | **{stats.active_days}** |",
            "| Commits | Study hours | Fixes |",
            f"| **{stats.total_commits}** | **{fmt_hours(stats.study_hours)} h** | **{stats.fixes}** |",
            "",
            "<sub>IST days, with a one-day grace for today. Add `[1h]` to a commit message "
            "to count study hours. Fixes are commits containing `fix`.</sub>",
        ]
    )


def section_heatmap(state: State) -> str:
    counts = state.stats.date_counts
    today = state.today
    start = today - timedelta(days=today.weekday() + 7 * 15)
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    rows: list[str] = []
    for weekday, label in enumerate(labels):
        cells: list[str] = []
        for week in range(16):
            day = start + timedelta(days=week * 7 + weekday)
            if day > today:
                cells.append("·")
                continue
            count = counts.get(day, 0)
            cells.append("⬜" if count == 0 else "🟩" if count <= 2 else "🟨" if count <= 5 else "🟧")
        rows.append(f"{label}  {''.join(cells)}")

    return "\n".join(
        [
            "## Activity",
            "",
            f"**Last 16 weeks** · {fmt_date(start)} → {fmt_date(today)}",
            "",
            "```text",
            *rows,
            "```",
            "",
            "<sub>⬜ none · 🟩 1–2 commits · 🟨 3–5 · 🟧 6+ · `·` future · one cell = one IST day</sub>",
        ]
    )


def section_recent(state: State) -> str:
    if not state.work_folders:
        return "\n".join(
            [
                "## Recent Work",
                "",
                "_No work folders yet. Push code inside a course folder and it appears here._",
            ]
        )

    lines = [
        "## Recent Work",
        "",
        "| Folder | Course | Last updated |",
        "|:--|:--|--:|",
    ]
    course_by_key = {course.cfg["key"]: course for course in state.courses}
    for folder in state.work_folders[:8]:
        course = course_by_key.get(folder.course_key or "")
        course_name = f"{course.emoji} {course.name}" if course else "—"
        when = fmt_ts(folder.last_ts)
        lines.append(
            f"| [{md_text(folder.rel)}]({quote_path(folder.rel)}) "
            f"| {md_cell(course_name)} | {when} |"
        )
    return "\n".join(lines)


def section_milestones(state: State) -> str:
    stats = state.stats
    lines = ["## Milestones", "", "### Courses"]
    for course in state.courses:
        lines.append(f"- [{'x' if course.status == 'done' else ' '}] {course.emoji} {md_text(course.name)}")
    if all(course.status == "done" for course in state.courses):
        lines.append("- [x] Full Stack Ruby on Rails path complete")

    lines.extend(["", "### Streaks"])
    for milestone in MILESTONE_STREAKS:
        lines.append(f"- [{'x' if stats.best_streak >= milestone else ' '}] {milestone}-day streak")

    lines.extend(
        [
            "",
            f"<sub>{state.courses_done}/{len(state.courses)} courses · "
            f"best streak {plural(stats.best_streak, 'day')}</sub>",
        ]
    )
    return "\n".join(lines)


def section_connect(state: State) -> str:
    return "\n".join(
        [
            "## Connect With Me",
            "",
            "I am open to internships, junior roles, collaborations, and "
            "conversations about Ruby on Rails and full-stack development.",
            "",
            "- **GitHub:** [@zeditya](https://github.com/zeditya)",
            "- **Email:** [adityabahuguna098@gmail.com]"
            "(mailto:adityabahuguna098@gmail.com)",
            "",
            "If you are building something and think I could help, or you have "
            "advice for someone learning in public, my inbox is open.",
        ]
    )


SECTION_BUILDERS: dict[str, Callable[[State], str]] = {
    "header": section_header,
    "about": section_about,
    "roadmap": section_roadmap,
    "courses": section_courses,
    "stats": section_stats,
    "heatmap": section_heatmap,
    "recent": section_recent,
    "milestones": section_milestones,
    "connect": section_connect,
}

# ---------------------------------------------------------------------------
# VALIDATION AND REPAIR
# ---------------------------------------------------------------------------

HEADINGS = {
    "about": "About",
    "roadmap": "Roadmap",
    "courses": "Course Progress",
    "stats": "Stats",
    "heatmap": "Activity",
    "recent": "Recent Work",
    "milestones": "Milestones",
    "connect": "Connect With Me",
}


class _TagBalance(HTMLParser):
    """Collect unclosed or mismatched HTML tags in generated Markdown."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        if not self.stack:
            self.errors.append(f"unexpected closing </{tag}>")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
            return
        self.errors.append(f"mismatched closing </{tag}>")
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
            if self.stack:
                self.stack.pop()

    def finish(self) -> list[str]:
        self.close()
        if self.stack:
            self.errors.append("unclosed " + ", ".join(f"<{tag}>" for tag in self.stack))
        return self.errors


def strip_code_fences(text: str) -> str:
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return "\n".join(lines)


def table_cell_count(row: str) -> int:
    pipes = 0
    escaped = False
    for char in row:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
        elif char == "|":
            pipes += 1
    return max(pipes - 1, 0)


def table_blocks(text: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("|"):
            current.append(line.strip())
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def generic_errors(text: str) -> list[str]:
    errors: list[str] = []

    if CONTROL_RE.search(text):
        errors.append("contains control characters")
    if not text.strip():
        errors.append("is empty")

    fences = sum(1 for line in text.splitlines() if line.lstrip().startswith("```"))
    if fences % 2:
        errors.append("has an unclosed code fence")

    visible = strip_code_fences(text)
    parser = _TagBalance()
    try:
        parser.feed(visible)
        html_errors = parser.finish()
    except Exception as exc:  # HTMLParser is forgiving, but never trust it
        html_errors = [f"could not parse HTML ({exc})"]
    errors.extend(html_errors)

    for match in re.finditer(r"<img\b([^>]*)>", visible, flags=re.IGNORECASE):
        attrs = {
            name.lower(): html.unescape(value)
            for name, value in re.findall(r'([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*"([^"]*)"', match.group(1))
        }
        src = attrs.get("src", "")
        alt = attrs.get("alt", "")
        if not src:
            errors.append("has an image without src")
        elif not src.startswith("https://") or not urlparse(src).netloc:
            errors.append("has an image with an invalid src")
        elif any(char.isspace() for char in src):
            errors.append("has an image with spaces in src")
        elif urlparse(src).netloc.lower() != "raw.githubusercontent.com":
            errors.append("has an image that is not self-hosted")
        if not alt.strip():
            errors.append("has an image without alt text")

    for match in re.finditer(r"\]\(([^)\n]*)\)", visible):
        target = match.group(1).strip()
        if not target:
            errors.append("has an empty link")
            continue
        if target.startswith(("https://", "http://")):
            if not urlparse(target).netloc:
                errors.append("has an invalid external link")
        elif target.startswith(("javascript:", "data:")):
            errors.append("has an unsafe link")
        elif target.startswith("#"):
            continue
        elif " " in target or "\\" in target:
            errors.append("has an invalid relative link")
        elif ".." in target.split("/"):
            errors.append("has a link outside the repository")

    for block in table_blocks(visible):
        if len(block) < 2:
            errors.append("has a table without a header separator")
            continue
        counts = {table_cell_count(row) for row in block}
        if len(counts) != 1:
            errors.append("has a table with inconsistent columns")
        if not all(row.startswith("|") and row.endswith("|") for row in block):
            errors.append("has a table row without edge pipes")
        separator = [cell.strip() for cell in block[1].strip("|").split("|")]
        if not separator or not all(re.fullmatch(r":?-{1,}:?", cell) for cell in separator):
            errors.append("has a malformed table separator")
        header = [cell.strip() for cell in block[0].strip("|").split("|")]
        if any(not cell for cell in header):
            errors.append("has an empty table header cell")

    if re.search(r"\b(?:None|NaN|Infinity)\b", visible):
        errors.append("contains a leaked Python value")
    if "{{" in visible or "}}" in visible:
        errors.append("contains an unrendered template")
    if "```mermaid" in text:
        errors.append("still contains a Mermaid diagram")

    return errors


def heading_errors(name: str, body: str) -> list[str]:
    errors: list[str] = []
    if name == "header":
        if not re.search(r"<h1\b[^>]*>.*?</h1>", body, flags=re.IGNORECASE | re.DOTALL):
            errors.append("header has no H1")
        if DISPLAY_NAME not in body:
            errors.append("header does not say Ruby on Rails")
        if "banner.svg?v=" not in body:
            errors.append("header has no banner image")
        if "badges.svg?v=" not in body:
            errors.append("header has no badges image")
        if REPO_DESCRIPTION not in body:
            errors.append("header has no repository description")
        return errors

    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    expected = f"## {HEADINGS[name]}"
    if first != expected:
        errors.append(f"heading is {first!r}, expected {expected!r}")

    if name == "courses":
        rows = [line for line in body.splitlines() if re.match(r"^\|\s*\[", line)]
        if len(rows) != len(COURSES):
            errors.append(f"has {len(rows)} course rows, expected {len(COURSES)}")
        for course in COURSES:
            name = str(course["name"])
            if name not in body and md_text(name) not in body:
                errors.append(f"is missing course {course['name']!r}")
    elif name == "roadmap":
        if not CACHE_BUSTER_RE.search(body):
            errors.append("has no roadmap cache buster")
        if "/.github/readme/roadmap.svg?v=" not in body:
            errors.append("has no roadmap image URL")
    elif name == "heatmap":
        if "```text" not in body:
            errors.append("has no heatmap code block")
    elif name == "milestones":
        boxes = sum(1 for line in body.splitlines() if re.match(r"^- \[[ x]\] ", line))
        if boxes < len(COURSES):
            errors.append("is missing course milestones")
    elif name == "about":
        if "Rails" not in body:
            errors.append("does not mention Ruby on Rails")
        if "MERN" not in body:
            errors.append("does not explain the MERN comparison")
        if "JavaScript" not in body:
            errors.append("does not mention the JavaScript pivot")
    elif name == "connect":
        if "https://github.com/" not in body:
            errors.append("has no GitHub link")
        if "mailto:" not in body:
            errors.append("has no email link")
    return errors


def section_errors(name: str, body: str) -> list[str]:
    errors: list[str] = []
    if not body.strip():
        return ["is empty"]
    if SECTION_MARKER_RE.search(body):
        errors.append("contains a section marker")
    errors.extend(heading_errors(name, body))
    errors.extend(generic_errors(body))
    return errors


def marker_sequence_errors(text: str) -> list[str]:
    found = [(match.group(1), match.group(2)) for match in SECTION_MARKER_RE.finditer(text)]
    expected = [(kind, name) for name in SECTION_ORDER for kind in ("START", "END")]
    if found == expected:
        return []
    return [
        "section markers are missing, duplicated, or out of order "
        f"(found {len(found)}, expected {len(expected)})"
    ]


def extract_sections(text: str) -> dict[str, str]:
    if marker_sequence_errors(text):
        return {}
    bodies: dict[str, str] = {}
    for name in SECTION_ORDER:
        start = f"<!--START_SECTION:{name}-->"
        end = f"<!--END_SECTION:{name}-->"
        left = text.find(start)
        right = text.find(end)
        if left < 0 or right < left:
            return {}
        bodies[name] = text[left + len(start) : right].strip()
    return bodies


def svg_labels(root: ET.Element) -> set[str]:
    return {
        (element.text or "").strip()
        for element in root.iter()
        if element.tag.endswith("text") and (element.text or "").strip()
    }


def validate_svg(svg: str) -> list[str]:
    errors: list[str] = []
    lowered = svg.lower()
    for needle in UNSAFE_SVG:
        if needle in lowered:
            errors.append(f"SVG contains unsafe content {needle!r}")
    if UNSAFE_SVG_RE.search(svg):
        errors.append("SVG contains a javascript URL")
    if re.search(r"\b(?:None|NaN|Infinity)\b", svg):
        errors.append("SVG contains a leaked value")

    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        return errors + [f"SVG is not valid XML ({exc})"]

    if root.tag != "{http://www.w3.org/2000/svg}svg":
        errors.append("SVG root element is not <svg>")
    if root.get("role") != "img":
        errors.append("SVG has no role=img")
    width = root.get("width", "")
    height = root.get("height", "")
    if not width.isdigit() or not height.isdigit():
        errors.append("SVG has no numeric size")
    labelled = root.get("aria-labelledby", "").split()
    ids = {element.get("id") for element in root.iter() if element.get("id")}
    for target in labelled:
        if target not in ids:
            errors.append(f"SVG aria-labelledby points to missing #{target}")
    if not any(element.tag.endswith("title") for element in root.iter()):
        errors.append("SVG has no title")
    if not any(element.tag.endswith("desc") for element in root.iter()):
        errors.append("SVG has no description")

    references = set(re.findall(r"url\(#([^)]+)\)", svg))
    references.update(re.findall(r"xlink:href=\"#([^\"]+)\"", svg))
    for target in references:
        if target not in ids:
            errors.append(f"SVG references missing #{target}")

    return errors


def validate_roadmap_svg(svg: str, state: State | None = None) -> list[str]:
    errors = validate_svg(svg)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return errors

    labels = svg_labels(root)
    courses = state.courses if state is not None else [
        Course(index=index, cfg=cfg, path=None) for index, cfg in enumerate(COURSES)
    ]
    for course in courses:
        if course.name.strip() not in labels:
            errors.append(f"SVG is missing course {course.name.strip()!r}")
    return errors


def validate_banner_svg(svg: str) -> list[str]:
    errors = validate_svg(svg)
    try:
        labels = svg_labels(ET.fromstring(svg))
    except ET.ParseError:
        return errors
    if DISPLAY_NAME not in labels:
        errors.append("banner is missing the Ruby on Rails title")
    if TAGLINE not in labels:
        errors.append("banner is missing the tagline")
    return errors


def validate_badges_svg(svg: str, state: State | None = None) -> list[str]:
    errors = validate_svg(svg)
    try:
        joined = " ".join(sorted(svg_labels(ET.fromstring(svg))))
    except ET.ParseError:
        return errors
    if "COURSES" not in joined:
        errors.append("badges are missing the courses badge")
    if "COMMITS" not in joined:
        errors.append("badges are missing the commits badge")
    return errors


def validate_readme(
    text: str,
    svg: str | dict[str, str] | None = None,
    state: State | None = None,
) -> list[str]:
    errors: list[str] = []
    if not text.startswith(README_COMMENT):
        errors.append("README has no generated-file header")
    if not text.endswith("\n"):
        errors.append("README does not end with a newline")

    marker_problems = marker_sequence_errors(text)
    errors.extend(marker_problems)
    if not marker_problems:
        bodies = extract_sections(text)
        if set(bodies) != set(SECTION_ORDER):
            errors.append("README is missing sections")
        for name in SECTION_ORDER:
            for problem in section_errors(name, bodies.get(name, "")):
                errors.append(f"{name}: {problem}")

    errors.extend(generic_errors(text))

    assets: dict[str, str] = {}
    if isinstance(svg, str):
        assets["roadmap.svg"] = svg
    elif isinstance(svg, dict):
        assets = svg

    for filename, content in assets.items():
        if filename == "roadmap.svg":
            errors.extend(validate_roadmap_svg(content, state))
        elif filename == "banner.svg":
            errors.extend(validate_banner_svg(content))
        elif filename == "badges.svg":
            errors.extend(validate_badges_svg(content, state))
        else:
            errors.append(f"unknown asset {filename!r}")
        version = hashlib.sha256(content.encode("utf-8")).hexdigest()[:8]
        src = re.compile(rf'src="[^"]*{re.escape(filename)}\?v={re.escape(version)}"')
        if len(src.findall(text)) != 1:
            errors.append(f"README must reference {filename} exactly once")

    return errors


def fallback_roadmap_svg(state: State) -> str:
    width = 1200
    height = max(200, 110 + max(len(state.courses) - 1, 0) * 42 + 70)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="roadmapTitle roadmapDesc">',
        '  <title id="roadmapTitle">Full Stack Ruby on Rails roadmap</title>',
        f'  <desc id="roadmapDesc">Roadmap for {len(state.courses)} courses.</desc>',
        f'  <rect width="{width}" height="{height}" fill="#0b1120" />',
        '  <text x="60" y="60" font-size="24" font-weight="700" fill="#f8fafc">Full Stack Ruby on Rails</text>',
    ]
    for index, course in enumerate(state.courses):
        y = 110 + index * 42
        lines.append(
            f'  <text x="60" y="{y}" font-size="18" font-weight="700" fill="#cbd5e1">'
            f"{html_attr(course.name)}</text>"
        )
        lines.append(
            f'  <text x="260" y="{y}" font-size="15" fill="#64748b">'
            f"{html_attr(course.status)}</text>"
        )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def fallback_body(name: str, state: State) -> str:
    if name == "header":
        if not state.banner_version or not state.badges_version:
            raise RuntimeError("cannot render the header without valid images")
        banner = asset_url(state, "banner.svg", state.banner_version)
        badges = asset_url(state, "badges.svg", state.badges_version)
        return "\n".join(
            [
                '<p align="center">',
                f'  <img src="{html_attr(banner)}" alt="Banner: {html_attr(DISPLAY_NAME)}" width="100%" />',
                "</p>",
                "",
                f'<h1 align="center">{html.escape(JOURNEY_TITLE)}</h1>',
                "",
                f'<p align="center"><sub>{html.escape(TAGLINE)}</sub></p>',
                "",
                f'<p align="center">{html.escape(REPO_DESCRIPTION)}</p>',
                "",
                '<p align="center">',
                f'  <img src="{html_attr(badges)}" alt="Learning stats" width="100%" />',
                "</p>",
            ]
        )
    if name == "roadmap":
        if state.roadmap_version:
            return section_roadmap(state)
        raise RuntimeError("cannot render a roadmap without a valid image")
    if name == "courses":
        lines = [
            "## Course Progress",
            "",
            "| Course | Status | Work | Progress |",
            "|:--|:--:|:--|:--|",
        ]
        for course in state.courses:
            lines.append(
                f"| [{course.emoji} **{md_text(course.name)}**]({course.top_url}) "
                "| ⬜ Not started | — | 0% |"
            )
        lines.extend(["", "<sub>Progress is temporarily unavailable.</sub>"])
        return "\n".join(lines)
    if name == "stats":
        return "\n".join(
            [
                "## Stats",
                "",
                "| Current streak | Best streak | Active days |",
                "|:---:|:---:|:---:|",
                "| **0 days** | **0 days** | **0** |",
                "| Commits | Study hours | Fixes |",
                "| **0** | **0 h** | **0** |",
            ]
        )
    if name == "heatmap":
        return "\n".join(
            [
                "## Activity",
                "",
                "```text",
                "Activity is temporarily unavailable.",
                "```",
            ]
        )
    if name == "recent":
        return "\n".join(
            [
                "## Recent Work",
                "",
                "_Recent work is temporarily unavailable._",
            ]
        )
    if name == "milestones":
        lines = ["## Milestones", "", "### Courses"]
        for course in state.courses:
            lines.append(f"- [ ] {course.emoji} {md_text(course.name)}")
        lines.extend(["", "### Streaks"])
        for milestone in MILESTONE_STREAKS:
            lines.append(f"- [ ] {milestone}-day streak")
        return "\n".join(lines)
    if name == "about":
        return "\n".join(
            [
                "## About",
                "",
                "I am learning software development for the first time, in "
                "public, through The Odin Project Full Stack Ruby on Rails "
                "path. I chose Rails over MERN because I want to build real "
                "projects and pursue opportunities as soon as possible. After "
                "becoming genuinely strong in Rails, I will pivot to the "
                "JavaScript track.",
                "",
                "Happy building. 🚀",
            ]
        )
    if name == "connect":
        return "\n".join(
            [
                "## Connect With Me",
                "",
                "- **GitHub:** [@zeditya](https://github.com/zeditya)",
                "- **Email:** [adityabahuguna098@gmail.com]"
                "(mailto:adityabahuguna098@gmail.com)",
            ]
        )
    raise RuntimeError(f"unknown section {name!r}")


def compose_readme(bodies: dict[str, str]) -> str:
    blocks: list[str] = []
    for name in SECTION_ORDER:
        body = bodies[name].strip()
        if not body:
            raise RuntimeError(f"section {name!r} is empty")
        blocks.append(f"<!--START_SECTION:{name}-->\n{body}\n<!--END_SECTION:{name}-->")
    return README_COMMENT + "\n\n" + "\n\n".join(blocks) + "\n"


def prepare_assets(state: State) -> dict[str, str]:
    specs = [
        ("roadmap.svg", ROADMAP_FILE, build_roadmap_svg, lambda svg: validate_roadmap_svg(svg, state), fallback_roadmap_svg, "roadmap_version"),
        ("banner.svg", BANNER_FILE, build_banner_svg, validate_banner_svg, fallback_banner_svg, "banner_version"),
        ("badges.svg", BADGES_FILE, build_badges_svg, lambda svg: validate_badges_svg(svg, state), fallback_badges_svg, "badges_version"),
    ]
    assets: dict[str, str] = {}
    for filename, path, builder, validator, fallback, version_attr in specs:
        existing = ""
        try:
            existing = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError, UnicodeError):
            pass

        candidates: list[str] = []
        try:
            candidates.append(builder(state))
        except Exception as exc:
            warn(f"could not build {filename}: {exc}")
        if existing:
            candidates.append(existing)
        try:
            candidates.append(fallback(state))
        except Exception as exc:
            warn(f"could not build fallback {filename}: {exc}")

        for candidate in candidates:
            problems = validator(candidate)
            if not problems:
                setattr(state, version_attr, hashlib.sha256(candidate.encode("utf-8")).hexdigest()[:8])
                assets[filename] = candidate
                break
            warn(f"rejected {filename}: " + "; ".join(problems))
        else:
            raise RuntimeError(f"no valid image could be produced for {filename}")

    return assets


def build_readme(state: State, previous: str, assets: dict[str, str]) -> str:
    previous_sections = extract_sections(previous)
    bodies: dict[str, str] = {}

    for name in SECTION_ORDER:
        chosen = ""
        try:
            candidate = SECTION_BUILDERS[name](state)
            problems = section_errors(name, candidate)
            if problems:
                warn(f"section {name!r} was invalid ({'; '.join(problems)})")
            else:
                chosen = candidate
        except Exception as exc:
            warn(f"section {name!r} failed ({exc})")

        if not chosen:
            old = previous_sections.get(name, "")
            if old and not section_errors(name, old):
                warn(f"keeping the previous {name!r} section")
                chosen = old

        if not chosen:
            try:
                fallback = fallback_body(name, state)
                problems = section_errors(name, fallback)
                if problems:
                    warn(f"fallback {name!r} was invalid ({'; '.join(problems)})")
                else:
                    chosen = fallback
            except Exception as exc:
                warn(f"fallback {name!r} failed ({exc})")

        if not chosen:
            raise RuntimeError(f"no valid content for section {name!r}")
        bodies[name] = chosen

    text = compose_readme(bodies)
    problems = validate_readme(text, assets, state)
    if not problems:
        return text

    warn("generated README failed validation: " + "; ".join(problems))
    safe_bodies = {name: fallback_body(name, state) for name in SECTION_ORDER}
    safe = compose_readme(safe_bodies)
    safe_problems = validate_readme(safe, assets, state)
    if safe_problems:
        raise RuntimeError("safe README failed validation: " + "; ".join(safe_problems))
    warn("using the safe README fallback")
    return safe


def restore_file(path: Path, data: bytes | None) -> None:
    try:
        if data is None:
            path.unlink(missing_ok=True)
        else:
            write_atomic(path, data)
    except OSError as exc:
        warn(f"could not restore {path.name}: {exc}")


def read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def write_outputs(readme: str, assets: dict[str, str], state: State) -> None:
    asset_paths = {
        "roadmap.svg": ROADMAP_FILE,
        "banner.svg": BANNER_FILE,
        "badges.svg": BADGES_FILE,
    }
    old_assets = {path: read_bytes(path) for path in asset_paths.values()}
    old_readme = read_bytes(README_FILE)
    new_readme = readme.encode("utf-8")

    try:
        for filename, path in asset_paths.items():
            if filename not in assets:
                raise RuntimeError(f"missing generated asset {filename}")
            new_data = assets[filename].encode("utf-8")
            if old_assets[path] != new_data:
                write_atomic(path, new_data)
        if old_readme != new_readme:
            write_atomic(README_FILE, new_readme)

        written_readme = README_FILE.read_text(encoding="utf-8")
        written_assets = {
            filename: path.read_text(encoding="utf-8")
            for filename, path in asset_paths.items()
        }
        problems = validate_readme(written_readme, written_assets, state)
        if problems:
            raise RuntimeError("written files failed validation: " + "; ".join(problems))
    except Exception:
        for path, data in old_assets.items():
            restore_file(path, data)
        restore_file(README_FILE, old_readme)
        raise


def outputs_changed(readme: str, assets: dict[str, str]) -> bool:
    try:
        if read_bytes(README_FILE) != readme.encode("utf-8"):
            return True
        paths = {
            "roadmap.svg": ROADMAP_FILE,
            "banner.svg": BANNER_FILE,
            "badges.svg": BADGES_FILE,
        }
        return any(read_bytes(paths[name]) != text.encode("utf-8") for name, text in assets.items())
    except OSError:
        return True


# ---------------------------------------------------------------------------
# README ENGINE
# ---------------------------------------------------------------------------


def check_files() -> int:
    errors: list[str] = []
    asset_paths = {
        "roadmap.svg": ROADMAP_FILE,
        "banner.svg": BANNER_FILE,
        "badges.svg": BADGES_FILE,
    }
    validators = {
        "roadmap.svg": validate_roadmap_svg,
        "banner.svg": validate_banner_svg,
        "badges.svg": validate_badges_svg,
    }
    assets: dict[str, str] = {}
    for filename, path in asset_paths.items():
        if not path.is_file():
            errors.append(f"{filename} is missing")
            continue
        try:
            content = path.read_text(encoding="utf-8")
            assets[filename] = content
            errors.extend(f"{filename}: {problem}" for problem in validators[filename](content))
        except (OSError, UnicodeError) as exc:
            errors.append(f"{filename}: {exc}")

    if not README_FILE.is_file():
        errors.append("README.md is missing")
    else:
        try:
            text = README_FILE.read_text(encoding="utf-8")
            errors.extend(f"README.md: {problem}" for problem in validate_readme(text, assets))
        except (OSError, UnicodeError) as exc:
            errors.append(f"README.md: {exc}")

    if errors:
        print("Generated files are invalid:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("README.md, banner.svg, badges.svg and roadmap.svg are valid.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update README from git history.")
    parser.add_argument("--check", action="store_true", help="validate the generated files without writing")
    args = parser.parse_args(argv)

    if args.check:
        return check_files()

    previous: str | None = None
    if README_FILE.exists():
        try:
            previous = README_FILE.read_text(encoding="utf-8")
        except UnicodeError as exc:
            warn(f"README.md is not valid UTF-8 ({exc}); regenerating it")
            previous = None
        except OSError as exc:
            warn(f"could not read README.md: {exc}")
            return 1
    else:
        warn("README.md is missing; creating a complete README")

    state = build_state()
    if state.critical_error and previous is not None:
        warn("core input failed; keeping the previous README unchanged")
        print("README unchanged.")
        return 0

    try:
        assets = prepare_assets(state)
    except Exception as exc:
        warn(f"could not prepare the README images: {exc}")
        if previous is not None:
            warn("keeping the previous README unchanged")
            print("README unchanged.")
            return 0
        return 1

    try:
        readme = build_readme(state, previous or "", assets)
    except Exception as exc:
        warn(f"could not build a valid README: {exc}")
        if previous is not None:
            warn("keeping the previous README unchanged")
            print("README unchanged.")
            return 0
        return 1

    if previous is not None and not outputs_changed(readme, assets):
        print("README already up to date.")
        return 0

    try:
        write_outputs(readme, assets, state)
    except Exception as exc:
        warn(f"could not write the generated files: {exc}")
        warn("the previous files were restored")
        return 1

    print("README changed." if readme != previous else "README already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
