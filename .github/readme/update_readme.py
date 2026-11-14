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

import html
import json
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
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# CONFIG — edit only this block if the curriculum changes.
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
README_FILE = ROOT / "README.md"
CACHE_FILE = ROOT / ".github" / "readme" / "projects-cache.json"

IST = timezone(timedelta(hours=5, minutes=30))

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

# Project showcase: public repos are discovered from the API.
MAX_PROJECTS = 6
PROJECT_EXCLUDE: set[str] = set()  # e.g. {"dotfiles", "old-test-repo"}

MILESTONE_STREAKS = (7, 30, 100)
MILESTONE_PROJECTS = (1, 3, 5, 10)

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
    "projects",
    "milestones",
]

API_BASE = os.environ.get("GITHUB_API_BASE", "https://api.github.com").rstrip("/")
API_TIMEOUT = float(os.environ.get("ODIN_API_TIMEOUT", "10"))
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


def md_url(url: str) -> str:
    return quote(url, safe=":/?#@!$&'*,;=%")


def is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


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
class Project:
    name: str
    repo_url: str
    live: str
    language: str
    stars: int | None
    updated: str


@dataclass
class State:
    today: date
    repo_owner: str
    repo_name: str
    commits: list[Commit]
    courses: list[Course]
    work_folders: list[WorkFolder]
    stats: Stats
    projects: list[Project]
    project_count: int
    critical_error: bool = False

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
        projects=[],
        project_count=0,
    )

# ---------------------------------------------------------------------------
# PROJECTS — auto-discovered from public GitHub repos
# ---------------------------------------------------------------------------


def load_cache(owner: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict) or data.get("owner") != owner:
        return []
    projects = data.get("projects")
    return [item for item in projects if isinstance(item, dict)] if isinstance(projects, list) else []


def save_cache(owner: str, projects: list[dict[str, Any]]) -> None:
    payload = {"version": 1, "owner": owner, "projects": projects}
    try:
        write_atomic(CACHE_FILE, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except OSError as exc:
        warn(f"could not write project cache: {exc}")


def fetch_repos(owner: str) -> list[dict[str, Any]]:
    url = (
        f"{API_BASE}/users/{quote(owner, safe='')}/repos"
        "?per_page=100&sort=pushed&direction=desc&type=owner"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "odin-learning-readme-bot",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        with urlopen(Request(url, headers=headers), timeout=API_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("invalid JSON") from exc

    if not isinstance(payload, list):
        raise RuntimeError("unexpected API payload")
    return [item for item in payload if isinstance(item, dict)]


def fmt_iso_date(raw: Any) -> str:
    if not isinstance(raw, str) or not raw:
        return "—"
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    return fmt_date(moment.astimezone(IST))


def normalize_repo(repo: dict[str, Any]) -> dict[str, Any]:
    """Turn an API repo, or an already-normalized cache entry, into our shape.

    The output keeps fork/archived/size so the cached copy can be filtered the
    same way as a fresh API response.
    """
    homepage = repo.get("homepage")
    if not (isinstance(homepage, str) and is_http_url(homepage)):
        homepage = repo.get("live")
    live = homepage if isinstance(homepage, str) and is_http_url(homepage) else ""

    stars = repo.get("stargazers_count")
    if isinstance(stars, bool) or not isinstance(stars, int):
        stars = repo.get("stars")
    if isinstance(stars, bool) or not isinstance(stars, int):
        stars = None

    size = repo.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        size = None

    language = repo.get("language")
    full_name = str(repo.get("full_name") or "")
    return {
        "name": str(repo.get("name") or full_name.split("/")[-1]),
        "full_name": full_name,
        "html_url": str(repo.get("html_url") or f"https://github.com/{full_name}"),
        "live": live,
        "language": str(language) if language else "",
        "stars": stars,
        "pushed_at": repo.get("pushed_at") or repo.get("updated_at") or "",
        "fork": bool(repo.get("fork")),
        "archived": bool(repo.get("archived")),
        "size": size,
    }


def resolve_projects(state: State, offline: bool = False) -> None:
    owner = state.repo_owner
    cached = load_cache(owner)
    fresh: list[dict[str, Any]] | None = None

    if not offline:
        try:
            fresh = fetch_repos(owner)
        except Exception as exc:
            warn(f"GitHub project API failed: {exc}")
            if cached:
                warn("using cached project data")

    raw_projects = fresh if fresh is not None else cached
    selected: list[dict[str, Any]] = []
    for repo in raw_projects:
        if repo.get("fork") or repo.get("archived"):
            continue
        name = str(repo.get("name") or "")
        if not name or name == state.repo_name or name in PROJECT_EXCLUDE:
            continue
        if isinstance(repo.get("size"), int) and repo.get("size") == 0:
            continue
        selected.append(normalize_repo(repo))
        if len(selected) >= MAX_PROJECTS:
            break

    if fresh is not None:
        # Cache every normalized candidate, not only the visible six, so the
        # same stable order survives an API outage.
        cache_items = [normalize_repo(repo) for repo in fresh]
        if cache_items != cached:
            save_cache(owner, cache_items)

    state.projects = [
        Project(
            name=item["name"],
            repo_url=item["html_url"],
            live=item["live"],
            language=item["language"],
            stars=item["stars"],
            updated=fmt_iso_date(item["pushed_at"]),
        )
        for item in selected
    ]
    state.project_count = len(state.projects)


def build_state(offline: bool = False) -> State:
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
            projects=[],
            project_count=0,
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
            projects=[],
            project_count=0,
            critical_error=True,
        )
        return state

    resolve_projects(state, offline)
    return state

# ---------------------------------------------------------------------------
# RENDER
# ---------------------------------------------------------------------------


def section_header(state: State) -> str:
    stats = state.stats
    total = len(state.courses)
    done = state.courses_done
    last = fmt_date(stats.last_dt)
    name = state.repo_name

    banner = (
        "https://capsule-render.vercel.app/api?type=waving"
        "&color=0:6f42c1,100:2ea043&height=170&section=header"
        f"&text={quote(name)}&fontSize=44&fontColor=ffffff&fontAlignY=40"
        "&desc=Ruby%20on%20Rails%20%C2%B7%20The%20Odin%20Project"
        "&descAlignY=62&animation=fadeIn"
    )
    typing = (
        "https://readme-typing-svg.vercel.app/?font=Fira+Code&weight=600&size=22"
        "&pause=1000&color=8957E5&center=true&vCenter=true&width=760"
        "&lines=Learning+Ruby+on+Rails+in+public;"
        "Commit+code%2C+push%2C+README+updates+itself;"
        "One+commit+at+a+time+%C2%B7+IST"
    )
    badges = [
        (badge_url("courses", f"{done}/{total}", "6f42c1"), f"Badge: {done} of {total} courses done"),
        (badge_url("projects", str(state.project_count), "2ea043"), f"Badge: {state.project_count} projects"),
        (badge_url("streak", plural(stats.current_streak, "day"), "db6d28"), f"Badge: {plural(stats.current_streak, 'day')} current streak"),
        (badge_url("commits", str(stats.total_commits), "0969da"), f"Badge: {plural(stats.total_commits, 'commit')} in total"),
        (badge_url("last commit", last, "57606a"), f"Badge: last commit {last}"),
    ]

    lines = [
        '<p align="center">',
        f'  <img src="{html_attr(banner)}" alt="Waving banner for {html_attr(name)}: Ruby on Rails and The Odin Project" width="100%" />',
        "</p>",
        "",
        f'<h1 align="center">{html.escape(name)} 🛤️</h1>',
        "",
        '<p align="center">',
        f'  <img src="{html_attr(typing)}" alt="Animated text: learning Ruby on Rails in public; commit code, push, and the README updates itself." />',
        "</p>",
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
            f"  <sub><strong>{done}/{total} courses</strong> · "
            f"<strong>{state.project_count} projects</strong> · "
            f"<strong>{plural(stats.current_streak, 'day')} streak</strong> · "
            f"<strong>{plural(stats.total_commits, 'commit')}</strong><br />",
            f"  Last commit: {md_text(fmt_datetime(stats.last_dt))} · no README editing required</sub>",
            "</p>",
        ]
    )
    return "\n".join(lines)


def section_roadmap(state: State) -> str:
    class_for = {"done": "done", "active": "current", "todo": "todo"}
    lines = ["## 🗺️ Roadmap", "", "```mermaid", "flowchart TD"]
    for course in state.courses:
        node = f"C{course.index + 1:02d}"
        label = f"{course.emoji} {course.name}".replace('"', "'")
        lines.append(f'  {node}["{label}"]')
    for course in state.courses[:-1]:
        lines.append(f"  C{course.index + 1:02d} --> C{course.index + 2:02d}")
    lines.extend(
        [
            "  classDef done fill:#1a7f37,stroke:#2ea043,color:#ffffff,stroke-width:2px",
            "  classDef current fill:#9e6a03,stroke:#d29922,color:#ffffff,stroke-width:2px",
            "  classDef todo fill:#57606a,stroke:#8c959f,color:#ffffff,stroke-width:2px",
        ]
    )
    for course in state.courses:
        lines.append(f"  class C{course.index + 1:02d} {class_for[course.status]}")
    lines.extend(
        [
            "```",
            "",
            "<sub>✅ Done · 🚧 Current · ⬜ Not started</sub>",
            "",
            "<sub>Order: "
            + " → ".join(f"{course.index + 1:02d} {course.name}" for course in state.courses)
            + "</sub>",
        ]
    )
    return "\n".join(lines)


def section_courses(state: State) -> str:
    labels = {"done": "✅ Done", "active": "🚧 In progress", "todo": "⬜ Not started"}
    lines = [
        "## 📊 Courses",
        "",
        "| Course | Status | Activity | Progress |",
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
            activity = (
                f"**{len(course.commits)}** {commits_word} · "
                f"**{course.total_folders}** {folders_word}"
                f"<br><sub>last {fmt_date(datetime.fromtimestamp(course.last_ts, IST))}</sub>"
            )
        else:
            activity = "—"

        if course.status == "done":
            progress = f"`{progress_bar(1)}` 100%<br><sub>course complete</sub>"
        elif course.status == "active":
            folder_word = "folder" if course.total_folders == 1 else "folders"
            progress = (
                f"`{progress_bar(course.progress)}` {int(round(course.progress * 100))}%"
                f"<br><sub>{course.done_folders} / {course.total_folders} {folder_word} done</sub>"
            )
        else:
            progress = f"`{progress_bar(0)}` 0%"

        lines.append(f"| {name} | {labels[course.status]} | {activity} | {progress} |")

    lines.extend(
        [
            "",
            "<sub>No extra files needed. The folder you touched most recently in a course is "
            "in progress; older folders count as done. Courses before your current course are done.</sub>",
        ]
    )
    return "\n".join(lines)


def section_stats(state: State) -> str:
    stats = state.stats
    return "\n".join(
        [
            "## 📈 Stats",
            "",
            "| 🔥 Current streak | 🏆 Best streak | 📅 Active days |",
            "|:---:|:---:|:---:|",
            f"| **{plural(stats.current_streak, 'day')}** | **{plural(stats.best_streak, 'day')}** | **{stats.active_days}** |",
            "| 💬 Commits | ⏱️ Study hours | 🛠️ Fixes |",
            f"| **{stats.total_commits}** | **{fmt_hours(stats.study_hours)} h** | **{stats.fixes}** |",
            "",
            "<sub>IST days, with a 1-day grace for today. Study hours are optional: put `[1h]` "
            "in a commit message if you want them counted. Fixes are commits containing `fix`.</sub>",
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
            "## 🌱 Activity",
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
    lines = ["## 🕒 Recently active", ""]
    if not state.work_folders:
        lines.append("_Push your first code folder and it appears here._")
        return "\n".join(lines)

    course_by_key = {course.cfg["key"]: course for course in state.courses}
    for folder in state.work_folders[:7]:
        label = folder.rel.split("/")[-1] if "/" in folder.rel else folder.rel
        course = course_by_key.get(folder.course_key or "")
        suffix = f" · {course.emoji} {md_text(course.name)}" if course else ""
        when = fmt_date(datetime.fromtimestamp(folder.last_ts, IST))
        lines.append(f"- 🕒 **[{md_text(label)}]({quote_path(folder.rel)})**{suffix} · {when}")
    return "\n".join(lines)


def section_projects(state: State) -> str:
    lines = ["## 🚀 Projects", ""]
    if not state.projects:
        lines.append(
            "_Public repos appear here automatically. If GitHub's API is down, the last "
            "good list is kept in `.github/readme/projects-cache.json`._"
        )
        return "\n".join(lines)

    language_emoji = {
        "ruby": "💎",
        "javascript": "⚡",
        "typescript": "🔷",
        "python": "🐍",
        "html": "🌐",
        "css": "🎨",
        "gdscript": "🎮",
        "c": "🔧",
        "c++": "🔧",
    }
    lines.extend(
        [
            "| Project | Language | Stars | Updated |",
            "|:--|:--:|:--:|:--:|",
        ]
    )
    for project in state.projects:
        name = f"🚀 **[{md_text(project.name)}]({md_url(project.repo_url)})**"
        if project.live:
            name += f" · [Live ↗]({md_url(project.live)})"
        language = (
            f"{language_emoji.get(project.language.lower(), '🧩')} {md_cell(project.language)}"
            if project.language
            else "—"
        )
        stars = f"⭐ {project.stars:,}" if project.stars is not None else "—"
        lines.append(f"| {name} | {language} | {stars} | {project.updated} |")

    lines.extend(
        [
            "",
            "<sub>Discovered from your public GitHub repos · forks and this repo are skipped · "
            "edit `PROJECT_EXCLUDE` in the script to hide one.</sub>",
        ]
    )
    return "\n".join(lines)


def section_milestones(state: State) -> str:
    stats = state.stats
    lines = ["## 🎯 Milestones", "", "### 🎓 Courses"]
    for course in state.courses:
        lines.append(f"- [{'x' if course.status == 'done' else ' '}] {course.emoji} {md_text(course.name)}")
    if all(course.status == "done" for course in state.courses):
        lines.append("- [x] 🏆 Full Stack Ruby on Rails path complete")

    lines.extend(["", "### 🔥 Streaks"])
    for milestone in MILESTONE_STREAKS:
        lines.append(f"- [{'x' if stats.best_streak >= milestone else ' '}] {milestone}-day streak")

    lines.extend(["", "### 📦 Shipping"])
    for milestone in MILESTONE_PROJECTS:
        label = "First project" if milestone == 1 else f"{milestone} projects"
        lines.append(f"- [{'x' if state.project_count >= milestone else ' '}] {label}")

    lines.extend(
        [
            "",
            f"<sub>{state.courses_done}/{len(state.courses)} courses · "
            f"best streak {plural(stats.best_streak, 'day')} · "
            f"{state.project_count} projects</sub>",
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
    "projects": section_projects,
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
    import argparse

    parser = argparse.ArgumentParser(description="Update README from git history.")
    parser.add_argument("--offline", action="store_true", help="skip the GitHub API")
    args = parser.parse_args()

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

    state = build_state(offline=args.offline)
    if state.critical_error:
        warn("core input failed; keeping every generated section unchanged")
        if README_FILE.exists():
            print("README unchanged.")
            return 0
        warn("no previous README to preserve")
        return 1

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
