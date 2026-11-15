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

import hashlib
import html
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

# ---------------------------------------------------------------------------
# CONFIG — edit only this block if the curriculum changes.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
README_FILE = ROOT / "README.md"
ROADMAP_FILE = ROOT / ".github" / "readme" / "roadmap.svg"

IST = timezone(timedelta(hours=5, minutes=30))

# Simple, personal heading shown at the top of the README.
DISPLAY_NAME = "Ruby on Rails"
JOURNEY_TITLE = "Learning Journey"
TAGLINE = "The Odin Project · Learning in public · India (IST)"

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
    "roadmap",
    "courses",
    "stats",
    "heatmap",
    "recent",
    "milestones",
]

HOURS_RE = re.compile(r"\[(\d+(?:\.\d+)?)\s*h\]", re.IGNORECASE)
FIX_RE = re.compile(r"\bfix(?:es|ed)?\b", re.IGNORECASE)

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


def fmt_date(value: datetime | date | None) -> str:
    if value is None:
        return "—"
    return f"{value.day} {value.strftime('%b %Y')}"


def fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    return f"{fmt_date(value)} · {value.strftime('%H:%M')} IST"


def fmt_hours(value: Decimal) -> str:
    if value <= 0:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count} {word}"


def md_cell(value: Any) -> str:
    text = html.escape(str(value), quote=False)
    return text.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def md_text(value: Any) -> str:
    text = html.escape(str(value), quote=False)
    return text.replace("[", "\\[").replace("]", "\\]")


def quote_path(path: str) -> str:
    return quote(path, safe="/")


def progress_bar(fraction: float, width: int = 20) -> str:
    fraction = max(0.0, min(1.0, fraction))
    filled = int(round(fraction * width))
    if fraction >= 0.999:
        filled = width
    return "█" * filled + "░" * (width - filled)


def badge_url(label: str, value: str, color: str) -> str:
    safe_value = str(value).replace("-", "--")
    return (
        f"https://img.shields.io/badge/{quote(label, safe='')}"
        f"-{quote(safe_value, safe='')}-{color}"
        "?style=flat-square&labelColor=1f2328"
    )


def html_attr(value: Any) -> str:
    return html.escape(str(value), quote=True)


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
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
        return owner, name

    remote = run_git("remote", "get-url", "origin", quiet=True).strip()
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
    if match:
        return match.group(1), match.group(2)

    return "zeditya", "odin-learning"


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
        sha, ts_raw, author_name, author_email, subject = header[:5]
        if (
            author_name.strip() in BOT_NAMES
            or author_email.strip().lower() in BOT_EMAILS
            or subject.startswith("docs: auto-update README")
        ):
            continue
        try:
            ts = int(ts_raw)
        except ValueError:
            continue
        files = tuple(line.strip() for line in lines[1:] if line.strip())
        commits.append(
            Commit(
                sha=sha,
                ts=ts,
                dt=datetime.fromtimestamp(ts, IST),
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
    try:
        commits = load_commits()
    except Exception as exc:
        warn(f"could not read git history: {exc}")
        state = State(
            today=today,
            repo_owner=owner,
            repo_name=name,
            commits=[],
            courses=[],
            work_folders=[],
            stats=Stats(0, 0, 0, 0, Decimal("0"), 0, None, Counter()),
            critical_error=True,
        )
        return state

    try:
        state = discover_state(commits, today, owner, name)
    except Exception as exc:
        warn(f"could not read course folders: {exc}")
        state = State(
            today=today,
            repo_owner=owner,
            repo_name=name,
            commits=commits,
            courses=[],
            work_folders=[],
            stats=Stats(0, 0, 0, 0, Decimal("0"), 0, None, Counter()),
            critical_error=True,
        )
        return state

    return state

# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------


def section_header(state: State) -> str:
    stats = state.stats
    total = len(state.courses)
    done = state.courses_done
    last = fmt_date(stats.last_dt)
    title = JOURNEY_TITLE

    banner = (
        "https://capsule-render.vercel.app/api?type=waving"
        "&color=0:0f172a,50:6d28d9,100:2563eb&height=180&section=header"
        f"&text={quote(DISPLAY_NAME)}&fontSize=42&fontColor=ffffff&fontAlignY=50"
        "&animation=fadeIn"
    )

    active = next((course for course in state.courses if course.status == "active"), None)
    focus = f"{active.emoji} {active.name}" if active else "Getting started"

    badges = [
        (
            badge_url("courses", f"{done}/{total}", "6d28d9"),
            f"Badge: {done} of {total} courses done",
        ),
        (
            badge_url("streak", plural(stats.current_streak, "day"), "2563eb"),
            f"Badge: {plural(stats.current_streak, 'day')} current streak",
        ),
        (
            badge_url("commits", str(stats.total_commits), "0f766e"),
            f"Badge: {plural(stats.total_commits, 'commit')} in total",
        ),
        (
            badge_url("last commit", last, "475569"),
            f"Badge: last commit {last}",
        ),
    ]

    lines = [
        '<p align="center">',
        f'  <img src="{html_attr(banner)}" alt="Banner: {html_attr(DISPLAY_NAME)}" width="100%" />',
        "</p>",
        "",
        f'<h1 align="center">{html.escape(title)}</h1>',
        "",
        f'<p align="center"><sub>{html.escape(TAGLINE)}</sub></p>',
        "",
        '<p align="center">',
    ]
    for url, alt in badges:
        lines.append(f'  <img src="{html_attr(url)}" alt="{html_attr(alt)}" />')
    lines.extend(
        [
            "</p>",
            "",
            '<p align="center">',
            f"  <strong>Currently learning:</strong> {md_text(focus)}<br />",
            f"  <sub>Last commit: {md_text(fmt_datetime(stats.last_dt))}</sub>",
            "</p>",
        ]
    )
    return "\n".join(lines)


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
    width, height = 1200, 920
    center_x, top, step = 600, 150, 95
    node_xs = (440, 760)
    points = [(node_xs[index % 2], top + index * step) for index in range(total)]

    route = f"M {center_x} 90"
    prev_x, prev_y = center_x, 90
    for x, y in points:
        dy = y - prev_y
        route += (
            f" C {svg_num(prev_x)} {svg_num(prev_y + dy * 0.45)},"
            f" {svg_num(x)} {svg_num(y - dy * 0.45)}, {svg_num(x)} {svg_num(y)}"
        )
        prev_x, prev_y = x, y
    tail_y = 865
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
                f'    <text x="{label_x}" y="{y - 16}" text-anchor="{anchor}" font-size="20" font-weight="700" fill="{name_fill}">{html_attr(course.name)}</text>',
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

    legend = f'''    <g transform="translate(60, 878)">
      <circle cx="6" cy="-4" r="5" fill="#22c55e" />
      <text x="18" y="0" font-size="13" fill="#94a3b8">Done</text>
      <circle cx="106" cy="-4" r="5" fill="#8b5cf6">
        <animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite" />
      </circle>
      <text x="118" y="0" font-size="13" fill="#94a3b8">In progress</text>
      <circle cx="236" cy="-4" r="5" fill="#475569" />
      <text x="248" y="0" font-size="13" fill="#94a3b8">Not started</text>
    </g>
    <text x="1140" y="878" text-anchor="end" font-size="13" fill="#64748b">{done} / {total} courses complete</text>'''

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
    <linearGradient id="routeGradient" gradientUnits="userSpaceOnUse" x1="0" y1="90" x2="0" y2="865">
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
        f"/main/.github/readme/roadmap.svg?v={state.roadmap_version}"
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
                f"<br><sub>last {fmt_date(datetime.fromtimestamp(course.last_ts, IST))}</sub>"
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
        when = fmt_date(datetime.fromtimestamp(folder.last_ts, IST))
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


SECTION_BUILDERS: dict[str, Callable[[State], str]] = {
    "header": section_header,
    "roadmap": section_roadmap,
    "courses": section_courses,
    "stats": section_stats,
    "heatmap": section_heatmap,
    "recent": section_recent,
    "milestones": section_milestones,
}

# ---------------------------------------------------------------------------
# README ENGINE
# ---------------------------------------------------------------------------


def replace_section(text: str, name: str, body: str) -> str | None:
    start = f"<!--START_SECTION:{name}-->"
    end = f"<!--END_SECTION:{name}-->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), flags=re.S)
    match = pattern.search(text)
    if match is None:
        return None
    clean = body.strip()
    if not clean:
        raise ValueError("section body is empty")
    if "<!--START_SECTION:" in clean or "<!--END_SECTION:" in clean:
        raise ValueError("section body contains a marker")
    return text[: match.start()] + f"{start}\n{clean}\n{end}" + text[match.end() :]


def scaffold_readme() -> str:
    blocks = "\n\n".join(
        f"<!--START_SECTION:{name}-->\n<!--END_SECTION:{name}-->"
        for name in SECTION_ORDER
    )
    return (
        "<!-- README is generated from git history. Push code; do not edit this file. -->\n\n"
        + blocks
        + "\n"
    )


def main() -> int:
    if not README_FILE.exists():
        warn("README.md is missing; creating a marker scaffold")
        original = scaffold_readme()
        readme = original
    else:
        try:
            readme = README_FILE.read_text(encoding="utf-8")
        except OSError as exc:
            warn(f"could not read README.md: {exc}")
            return 1
        original = readme

    state = build_state()
    if state.critical_error:
        warn("core input failed; keeping every generated section unchanged")
        if README_FILE.exists():
            print("README unchanged.")
            return 0
        warn("no previous README to preserve")
        return 1

    try:
        state.roadmap_version = write_roadmap(state)
    except Exception as exc:
        warn(f"could not write roadmap image: {exc}")

    updated: list[str] = []
    kept: list[str] = []
    for name in SECTION_ORDER:
        if f"<!--START_SECTION:{name}-->" not in readme:
            warn(f"section {name!r} has no markers; leaving it alone")
            kept.append(name)
            continue
        try:
            body = SECTION_BUILDERS[name](state)
            replaced = replace_section(readme, name, body)
            if replaced is None:
                warn(f"section {name!r} could not be located; leaving it alone")
                kept.append(name)
                continue
            readme = replaced
            updated.append(name)
        except Exception as exc:
            warn(f"section {name!r} failed ({exc}); keeping previous content")
            kept.append(name)

    if not readme.endswith("\n"):
        readme += "\n"
    if readme != original:
        try:
            write_atomic(README_FILE, readme)
        except OSError as exc:
            warn(f"could not write README.md: {exc}")
            return 1

    print(f"Updated sections: {', '.join(updated) if updated else 'none'}")
    if kept:
        print(f"Kept previous content: {', '.join(kept)}")
    print("README changed." if readme != original else "README already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
