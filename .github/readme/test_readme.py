#!/usr/bin/env python3
"""End-to-end tests for the project-free, modern README generator."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SOURCE = Path(__file__).resolve().with_name("update_readme.py")
TODAY = "2026-11-06"

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASS.append(name)
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))


BASE_ENV = os.environ.copy()
for key in ("GITHUB_TOKEN", "GH_TOKEN", "ODIN_TODAY", "GITHUB_REPOSITORY", "GITHUB_REF_NAME"):
    BASE_ENV.pop(key, None)


def git(repo: Path, *args: str, env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**BASE_ENV, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def new_repo(name: str) -> Path:
    repo = Path(tempfile.mkdtemp(prefix=f"odin2-{name}-"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    dest = repo / ".github" / "readme"
    dest.mkdir(parents=True)
    shutil.copy2(SOURCE, dest / "update_readme.py")
    return repo


def commit(
    repo: Path,
    message: str,
    files: dict[str, str],
    when: str,
    author: str = "Test User",
    email: str = "test@example.com",
) -> None:
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    env = {
        "GIT_AUTHOR_NAME": author,
        "GIT_AUTHOR_EMAIL": email,
        "GIT_COMMITTER_NAME": author,
        "GIT_COMMITTER_EMAIL": email,
        "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_DATE": when,
    }
    git(repo, "commit", "-q", "-m", message, env_extra=env)


def run_script(repo: Path, *, today: str = TODAY, repo_slug: str = "acme/odin-learning") -> subprocess.CompletedProcess:
    env = {**BASE_ENV}
    env["GITHUB_REPOSITORY"] = repo_slug
    env["ODIN_TODAY"] = today
    return subprocess.run(
        [sys.executable, str(repo / ".github" / "readme" / "update_readme.py")],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def readme_text(repo: Path) -> str:
    return (repo / "README.md").read_text(encoding="utf-8")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def roadmap_text(repo: Path) -> str:
    return (repo / ".github" / "readme" / "roadmap.svg").read_text(encoding="utf-8")


def readme_assets(repo: Path) -> dict[str, str]:
    return {
        name: (repo / ".github" / "readme" / name).read_text(encoding="utf-8")
        for name in ("roadmap.svg", "banner.svg", "badges.svg")
    }


def svg_root(text: str) -> ET.Element:
    return ET.fromstring(text)


def section(text: str, name: str) -> str:
    match = re.search(
        rf"<!--START_SECTION:{name}-->(.*?)<!--END_SECTION:{name}-->",
        text,
        flags=re.S,
    )
    if match is None:
        raise AssertionError(f"missing section {name}")
    return match.group(1)


def course_row(text: str, course_name: str) -> str:
    for line in section(text, "courses").splitlines():
        if f"**{course_name}**" in line:
            return line
    raise AssertionError(f"missing course row {course_name}")


def row_status(row: str) -> str:
    if "✅ Done" in row:
        return "done"
    if "🚧 In progress" in row:
        return "active"
    if "⬜ Not started" in row:
        return "todo"
    return "?"


def row_commits(row: str) -> int:
    match = re.search(r"\*\*(\d+)\*\* commits?", row)
    return int(match.group(1)) if match else 0


def test_normal_repo() -> None:
    print("\n[1] normal repo: new heading, no projects, course inference")
    repo = new_repo("normal")
    commit(repo, "ruby basics [2h]", {"ruby/basics/hello.rb": "puts 'hi'\n"}, "2026-11-01T10:00:00+05:30")
    commit(repo, "ruby exercises", {"ruby/exercises/ex1.rb": "x = 1\n"}, "2026-11-02T10:00:00+05:30")
    commit(repo, "html css landing", {"html-css/landing-page/index.html": "<h1>hi</h1>\n"}, "2026-11-03T10:00:00+05:30")
    commit(
        repo,
        "rails blog app",
        {"rails/blog-app/app/models/user.rb": "class User; end\n", "rails/blog-app/db/schema.rb": "x\n"},
        "2026-11-04T10:00:00+05:30",
    )
    commit(
        repo,
        "rails odin book",
        {"rails/odin-book/app/models/post.rb": "class Post; end\n", "rails/odin-book/db/schema.rb": "y\n"},
        "2026-11-05T10:00:00+05:30",
    )
    commit(
        repo,
        "docs: auto-update README [skip ci]",
        {"ruby/bot/evil.rb": "ignored\n"},
        "2026-11-06T10:00:00+05:30",
        author="github-actions[bot]",
        email="41898282+github-actions[bot]@users.noreply.github.com",
    )

    result = run_script(repo)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0, str(result.returncode))

    text = readme_text(repo)
    check(
        "simple heading",
        "banner.svg?v=" in text and '<h1 align="center">Learning Journey</h1>' in text,
        text[:200],
    )
    check("no personal name", "Aditya" not in text)
    check("no third-party images", "capsule-render" not in text and "img.shields.io" not in text)
    check("tagline", "The Odin Project · Learning in public · India (IST)" in text)
    check(
        "repository description",
        "Learning full-stack Ruby on Rails in public, one course at a time." in text,
    )
    about = section(text, "about")
    check("about mentions first-time learning", "first time" in about)
    check("about compares Rails and MERN", "instead of MERN" in about)
    check("about mentions JavaScript pivot", "JavaScript track" in about)
    check("about ends with happy building", "Happy building" in about)
    connect = section(text, "connect")
    check("connect has GitHub", "https://github.com/zeditya" in connect)
    check("connect has email", "mailto:adityabahuguna098@gmail.com" in connect)
    check("currently learning Rails", "Currently learning:</strong> 🛤️ Ruby on Rails" in text)
    check("no projects section", "<!--START_SECTION:projects-->" not in text)
    check("no projects heading", "## Projects" not in text)
    check("no project cache mention", "projects-cache" not in text)
    check("no project count badge", "Badge: 6 projects" not in text)

    check("8 course rows", section(text, "courses").count("| [") == 8)
    check("ruby done", row_status(course_row(text, "Ruby")) == "done")
    check("html-css done", row_status(course_row(text, "Intermediate HTML and CSS")) == "done")
    check("databases done (linear path)", row_status(course_row(text, "Databases")) == "done")
    check("rails active", row_status(course_row(text, "Ruby on Rails")) == "active")
    check("javascript todo", row_status(course_row(text, "JavaScript")) == "todo")
    check("rails 2 folders", "2** folders" in course_row(text, "Ruby on Rails"), course_row(text, "Ruby on Rails"))
    check("rails 50 percent", "50%" in course_row(text, "Ruby on Rails"), course_row(text, "Ruby on Rails"))

    check("ruby sees 2 commits", row_commits(course_row(text, "Ruby")) == 2)
    check("rails sees 2 commits", row_commits(course_row(text, "Ruby on Rails")) == 2)
    check("bot commit ignored in stats", "**5**" in section(text, "stats"), section(text, "stats"))
    check("bot folder hidden from recent", "bot/evil" not in section(text, "recent"))

    recent = section(text, "recent")
    check("recent is a table", "| Folder | Course | Last updated |" in recent)
    check("newest folder first", recent.find("rails/odin-book") < recent.find("rails/blog-app") < recent.find("html-css/landing-page"), recent)
    check("rails label in recent", "Ruby on Rails" in recent)

    check("streak grace works", "**5 days**" in section(text, "stats"), section(text, "stats"))
    check("study hours counted", "**2 h**" in section(text, "stats"), section(text, "stats"))
    check("heatmap exists", "Last 16 weeks" in section(text, "heatmap"))
    check("no shipping milestones", "Shipping" not in section(text, "milestones"))
    check("milestones no projects", "project" not in section(text, "milestones").lower())

    svg_path = repo / ".github" / "readme" / "roadmap.svg"
    check("roadmap svg exists", svg_path.is_file())
    svg = roadmap_text(repo)
    try:
        root = svg_root(svg)
        valid = True
    except ET.ParseError as exc:
        valid = False
        print(f"  svg parse error: {exc}")
    check("roadmap svg well formed", valid)
    check("svg is namespaced", valid and root.tag == "{http://www.w3.org/2000/svg}svg")
    check("svg is accessible", 'role="img"' in svg and "<title" in svg and "<desc" in svg)
    check("svg uses smil only", "<animate" in svg and "<animateMotion" in svg and "<script" not in svg)
    check("svg animates active node", "<animateTransform" in svg and 'repeatCount="indefinite"' in svg)
    check("svg has every course", all(name in svg for name in ("Ruby", "Databases", "JavaScript", "Getting Hired")))
    check("svg shows active course", "IN PROGRESS" in svg and "50%" in svg)

    roadmap = section(text, "roadmap")
    check("roadmap is an image", '<img src="https://raw.githubusercontent.com/' in roadmap)
    check("roadmap not mermaid", "```mermaid" not in text and "flowchart TD" not in text)
    check("roadmap cache buster matches svg", f"?v={digest(svg)[:8]}" in roadmap, roadmap)
    check("roadmap alt text", 'alt="Animated roadmap' in roadmap)
    check("readme references committed svg path", "/main/.github/readme/roadmap.svg" in roadmap)

    for filename in ("banner.svg", "badges.svg"):
        path = repo / ".github" / "readme" / filename
        check(f"{filename} exists", path.is_file())
        content = path.read_text(encoding="utf-8")
        try:
            root = svg_root(content)
            parsed = True
        except ET.ParseError:
            parsed = False
        check(f"{filename} is valid xml", parsed)
        check(f"{filename} is accessible", 'role="img"' in content and "<title" in content and "<desc" in content)
        check(f"{filename} has no scripts", "<script" not in content.lower())
        check(
            f"README {filename} cache buster matches",
            f"{filename}?v={digest(content)[:8]}" in text,
        )
    check(
        "badges show stats",
        "COURSES" in (repo / ".github" / "readme" / "badges.svg").read_text(encoding="utf-8").upper()
        and "COMMITS" in (repo / ".github" / "readme" / "badges.svg").read_text(encoding="utf-8").upper(),
    )
    check("header has local images", "banner.svg?v=" in section(text, "header") and "badges.svg?v=" in section(text, "header"))

    first = digest(text)
    first_svg = digest(svg)
    first_banner = digest((repo / ".github" / "readme" / "banner.svg").read_text(encoding="utf-8"))
    first_badges = digest((repo / ".github" / "readme" / "badges.svg").read_text(encoding="utf-8"))
    again = run_script(repo)
    print(again.stdout, end="")
    check("second run exit 0", again.returncode == 0)
    check("idempotent README", digest(readme_text(repo)) == first)
    check("idempotent roadmap svg", digest(roadmap_text(repo)) == first_svg)
    check("idempotent banner svg", digest((repo / ".github" / "readme" / "banner.svg").read_text(encoding="utf-8")) == first_banner)
    check("idempotent badges svg", digest((repo / ".github" / "readme" / "badges.svg").read_text(encoding="utf-8")) == first_badges)
    check("second run reports no change", "already up to date" in again.stdout)


def test_empty_repo() -> None:
    print("\n[2] empty repo: zeros, no crash")
    repo = new_repo("empty")
    result = run_script(repo)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0)
    text = readme_text(repo)
    check("zero courses", "Badge: 0 of 8 courses done" in text)
    check("zero commits", "**0**" in section(text, "stats"), section(text, "stats"))
    check("no projects badge", "projects-" not in text.lower())
    check("all courses todo", section(text, "courses").count("⬜ Not started") == 8)
    check("empty recent note", "No work folders yet" in section(text, "recent"))
    check("nine sections", text.count("<!--START_SECTION:") == 9)


def test_non_git() -> None:
    print("\n[3] non-git directory: keep previous README")
    repo = Path(tempfile.mkdtemp(prefix="odin2-nogit-"))
    (repo / ".github" / "readme").mkdir(parents=True)
    shutil.copy2(SOURCE, repo / ".github" / "readme" / "update_readme.py")
    original = "<!--START_SECTION:header-->\nOLD\n<!--END_SECTION:header-->\n"
    (repo / "README.md").write_text(original, encoding="utf-8")
    result = run_script(repo)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0)
    check("README untouched", (repo / "README.md").read_text(encoding="utf-8") == original)
    check("critical warning", "not a git repository" in result.stderr, result.stderr)
    check("reports unchanged", "README unchanged" in result.stdout)


def test_no_course_folder() -> None:
    print("\n[4] folders without a course name")
    repo = new_repo("nocourse")
    commit(repo, "add scratch notes", {"scratch/foo.txt": "hello\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0)
    text = readme_text(repo)
    check("all courses todo", section(text, "courses").count("⬜ Not started") == 8)
    check("scratch in recent", "scratch" in section(text, "recent"))
    check("one commit", "**1**" in section(text, "stats"), section(text, "stats"))


def test_streak_grace() -> None:
    print("\n[5] IST one-day streak grace")
    repo = new_repo("streak")
    commit(repo, "ruby one", {"ruby/a.rb": "1\n"}, "2026-11-10T22:00:00+05:30")
    run_script(repo, today="2026-11-11")
    check("one day later streak 1", "**1 day**" in section(readme_text(repo), "stats"))
    run_script(repo, today="2026-11-12")
    text = readme_text(repo)
    check("two days later streak 0", "**0 days**" in section(text, "stats"), section(text, "stats"))
    check("best streak kept", "**0 days** | **1 day**" in section(text, "stats"), section(text, "stats"))


def test_aliases() -> None:
    print("\n[6] course aliases and advanced-css precedence")
    repo = new_repo("aliases")
    day = 1
    for folder, course_word in [
        ("advanced-css/animations", "advanced css"),
        ("javascript/loops", "javascript"),
        ("react/components", "react"),
        ("job/resume", "job"),
        ("databases/sql", "databases"),
        ("html/responsive", "html"),
    ]:
        commit(repo, course_word, {f"{folder}/file.txt": "x\n"}, f"2026-11-{day:02d}T10:00:00+05:30")
        day += 1
    result = run_script(repo, today="2026-11-06")
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0)
    text = readme_text(repo)
    check("advanced-css is not html-css", row_commits(course_row(text, "Advanced HTML and CSS")) == 1)
    check("html alias maps to intermediate", row_commits(course_row(text, "Intermediate HTML and CSS")) == 1)
    check("javascript mapped", row_commits(course_row(text, "JavaScript")) == 1)
    check("react mapped", row_commits(course_row(text, "React")) == 1)
    check("job active", row_status(course_row(text, "Getting Hired")) == "active")
    check("databases mapped", row_commits(course_row(text, "Databases")) == 1)


def test_commit_fallback() -> None:
    print("\n[7] commit message fallback for an unnamed folder")
    repo = new_repo("fallback")
    commit(repo, "start rails app", {"misc/file.txt": "x\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    check("exit 0", result.returncode == 0)
    text = readme_text(repo)
    check("rails sees fallback commit", row_commits(course_row(text, "Ruby on Rails")) == 1)
    check("rails is active", row_status(course_row(text, "Ruby on Rails")) == "active")


def test_ror_does_not_match_error() -> None:
    print("\n[8] 'error' must not match the Rails alias 'ror'")
    repo = new_repo("ror")
    commit(repo, "fix error handling", {"scratch/file.txt": "x\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    check("exit 0", result.returncode == 0)
    text = readme_text(repo)
    check("rails has no commits", row_commits(course_row(text, "Ruby on Rails")) == 0, course_row(text, "Ruby on Rails"))


def test_static_no_projects() -> None:
    print("\n[9] source has no project/API/cache code")
    source = SOURCE.read_text(encoding="utf-8")
    for needle in ("projects-cache", "section_projects", "urllib.request", "api.github.com", "PROJECT_EXCLUDE"):
        check(f"source has no {needle}", needle not in source)
    check("source still has course config", "COURSES:" in source)
    check("source still has personal heading", "JOURNEY_TITLE" in source)
    check("source generates roadmap svg", "def build_roadmap_svg" in source and "ROADMAP_FILE" in source)
    check("source has no mermaid output", 'lines = ["## Roadmap", "", "```mermaid"' not in source)
    check("source validates against mermaid", "```mermaid" in source)
    check("source uses smil animation", "animateMotion" in source and "mpath" in source)


def run_check(repo: Path) -> subprocess.CompletedProcess:
    env = {**BASE_ENV, "GITHUB_REPOSITORY": "acme/odin-learning"}
    return subprocess.run(
        [sys.executable, str(repo / ".github" / "readme" / "update_readme.py"), "--check"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


def load_generator():
    spec = importlib.util.spec_from_file_location("readme_generator", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["readme_generator"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_validator_rejects_broken_output() -> None:
    print("\n[10] validator rejects every kind of broken output")
    repo = new_repo("validator")
    commit(repo, "rails app", {"rails/app/app/models/user.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    check("generator exit 0", result.returncode == 0)
    text = readme_text(repo)
    svg = roadmap_text(repo)
    module = load_generator()

    check("valid README passes", module.validate_readme(text, svg) == [], module.validate_readme(text, svg))
    check("valid SVG passes", module.validate_roadmap_svg(svg) == [], module.validate_roadmap_svg(svg))

    broken = {
        "missing end marker": text.replace("<!--END_SECTION:courses-->", "", 1),
        "missing all markers": re.sub(r"<!--(?:START|END)_SECTION:[a-z-]+-->", "", text),
        "truncated file": text[:120],
        "unclosed paragraph": text.replace("</p>", "", 1),
        "broken table": text.replace("|:--|:--:|:--|:--|", "|:--|:--|", 1),
        "missing image alt": re.sub(r'alt="[^"]*"', "", text, count=1),
        "bad version": re.sub(r"roadmap\.svg\?v=[a-f0-9]{8}", "roadmap.svg?v=deadbeef", text),
        "wrong heading": text.replace("## Stats", "## Stat", 1),
        "wrong about heading": text.replace("## About", "## About Me", 1),
        "about missing MERN": re.sub(r"MERN", "another stack", text),
        "connect missing email": text.replace("mailto:adityabahuguna098@gmail.com", "https://example.com", 1),
        "leaked value": text.replace("## Stats", "## Stats None", 1),
        "external image": text.replace("raw.githubusercontent.com", "img.shields.io"),
    }
    for label, candidate in broken.items():
        check(f"rejects {label}", bool(module.validate_readme(candidate, svg)), label)

    for label, candidate in {
        "invalid xml": "<svg>",
        "script": svg.replace("</svg>", "<script>alert(1)</script></svg>"),
        "missing desc": re.sub(r"<desc[^>]*>.*?</desc>", "", svg, flags=re.S),
        "missing course": svg.replace(">Ruby<", ">Gone<"),
    }.items():
        check(f"rejects svg {label}", bool(module.validate_roadmap_svg(candidate)), label)

    banner = (repo / ".github" / "readme" / "banner.svg").read_text(encoding="utf-8")
    badges = (repo / ".github" / "readme" / "badges.svg").read_text(encoding="utf-8")
    check("valid banner passes", module.validate_banner_svg(banner) == [], module.validate_banner_svg(banner))
    check("valid badges pass", module.validate_badges_svg(badges) == [], module.validate_badges_svg(badges))
    check("rejects banner without tagline", bool(module.validate_banner_svg(re.sub(r">The Odin Project[^<]*<", "><", banner))))
    check("rejects badges without stats", bool(module.validate_badges_svg(re.sub(r">COURSES[^<]*<", "><", badges))))
    check(
        "rejects banner version mismatch",
        bool(module.validate_readme(text.replace("banner.svg?v=", "banner.svg?v=deadbeef"), readme_assets(repo))),
    )


def test_repairs_corrupted_readme() -> None:
    print("\n[11] corrupted README and SVG are repaired, never committed broken")
    repo = new_repo("repair")
    commit(repo, "rails app", {"rails/app/app/models/user.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    run_script(repo)
    good = readme_text(repo)

    check("check accepts good files", run_check(repo).returncode == 0)

    corruptions = {
        "missing marker": good.replace("<!--END_SECTION:courses-->", "", 1),
        "no markers": re.sub(r"<!--(?:START|END)_SECTION:[a-z-]+-->", "", good),
        "truncated": good[:150],
        "unclosed html": good.replace("</p>", "", 1),
        "broken table": good.replace("|:--|:--:|:--|:--|", "|:--|:--|", 1),
    }
    for label, broken in corruptions.items():
        (repo / "README.md").write_text(broken, encoding="utf-8")
        check(f"check rejects {label}", run_check(repo).returncode == 1, label)
        result = run_script(repo)
        check(f"repairs {label}", result.returncode == 0, result.stderr)
        repaired = readme_text(repo)
        check(
            f"repaired {label} is valid",
            load_generator().validate_readme(repaired, readme_assets(repo)) == [],
            label,
        )
        check(f"repaired {label} has all sections", repaired.count("<!--START_SECTION:") == 9, label)

    (repo / "README.md").write_bytes(b"\xff\xfe\x00broken")
    check("check rejects invalid utf-8", run_check(repo).returncode == 1)
    result = run_script(repo)
    check("repairs invalid utf-8", result.returncode == 0, result.stderr)
    check(
        "repaired utf-8 is valid",
        load_generator().validate_readme(readme_text(repo), readme_assets(repo)) == [],
    )

    (repo / ".github" / "readme" / "roadmap.svg").write_text("<svg>", encoding="utf-8")
    check("check rejects broken svg", run_check(repo).returncode == 1)
    result = run_script(repo)
    check("repairs broken svg", result.returncode == 0, result.stderr)
    svg = roadmap_text(repo)
    check("repaired svg is valid", load_generator().validate_roadmap_svg(svg) == [])
    check("repaired svg is animated", "<animateMotion" in svg)

    for filename in ("banner.svg", "badges.svg"):
        (repo / ".github" / "readme" / filename).write_text("<svg>", encoding="utf-8")
        check(f"check rejects broken {filename}", run_check(repo).returncode == 1)
        result = run_script(repo)
        check(f"repairs {filename}", result.returncode == 0, result.stderr)
        repaired = (repo / ".github" / "readme" / filename).read_text(encoding="utf-8")
        check(f"repaired {filename} is valid", not load_generator().validate_svg(repaired), repaired[:200])


def test_pipe_in_folder_name() -> None:
    print("\n[12] table-breaking characters in folders stay escaped")
    repo = new_repo("pipes")
    commit(repo, "rails pipes", {"rails/a|b/app.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    check("exit 0", result.returncode == 0, result.stderr)
    text = readme_text(repo)
    check("pipe is escaped", r"a\|b" in text, section(text, "recent"))
    check("README is still valid", load_generator().validate_readme(text, readme_assets(repo)) == [])

    tricky = {
        "asterisk_and_tilde": "rails/a*b_c~d/app.rb",
        "brackets": "rails/[x]/app.rb",
        "backtick": "rails/back`tick/app.rb",
        "backslash": "rails/back\\slash/app.rb",
        "hash_and_question": "rails/a#b?c/app.rb",
        "percent": "rails/100%25/app.rb",
        "quotes": 'rails/quo"te/app.rb',
        "unicode": "rails/日本語-アプリ/app.rb",
    }
    for label, path in tricky.items():
        commit(repo, f"rails {label}", {path: "x\n"}, "2026-11-06T10:00:00+05:30")
    result = run_script(repo)
    check("tricky exit 0", result.returncode == 0, result.stderr)
    text = readme_text(repo)
    problems = load_generator().validate_readme(text, readme_assets(repo))
    check("tricky README is valid", problems == [], problems)
    recent = section(text, "recent")
    for label in ("back\\`tick", "back\\\\slash", "a\\*b\\_c\\~d"):
        check(f"{label} is escaped", label in recent, recent)

    module = load_generator()
    quoting = {
        "plain/path": "plain/path",
        '"rails/back\\\\slash"': "rails/back\\slash",
        '"rails/quo\\"te"': 'rails/quo"te',
        '"rails/tab\\there"': "rails/tab\there",
        '"rails/\\346\\227\\245"': "rails/日",
    }
    for quoted, expected in quoting.items():
        actual = module.unquote_git_path(quoted)
        check(f"unquotes {expected!r}", actual == expected, actual)


def test_bad_repo_env_is_ignored() -> None:
    print("\n[13] unsafe repository names never reach image URLs")
    repo = new_repo("badrepo")
    commit(repo, "ruby", {"ruby/a.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    env = {**BASE_ENV, "GITHUB_REPOSITORY": "bad name/../evil", "ODIN_TODAY": TODAY}
    result = subprocess.run(
        [sys.executable, str(repo / ".github" / "readme" / "update_readme.py")],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    check("exit 0", result.returncode == 0, result.stderr)
    text = readme_text(repo)
    check("unsafe name not used", "../evil" not in text and "bad name" not in text)
    check("README is valid", load_generator().validate_readme(text, readme_assets(repo)) == [])


def test_write_rollback() -> None:
    print("\n[14] a failed README write rolls back every image")
    module = load_generator()
    root = Path(tempfile.mkdtemp(prefix="odin2-rollback-"))
    asset_dir = root / ".github" / "readme"
    asset_dir.mkdir(parents=True)
    module.README_FILE = root / "README.md"
    module.ROADMAP_FILE = asset_dir / "roadmap.svg"
    module.BANNER_FILE = asset_dir / "banner.svg"
    module.BADGES_FILE = asset_dir / "badges.svg"

    state = module.State(
        today=module.today_ist(),
        repo_owner="acme",
        repo_name="odin-learning",
        commits=[],
        courses=[module.Course(index=index, cfg=cfg, path=None) for index, cfg in enumerate(module.COURSES)],
        work_folders=[],
        stats=module.Stats(0, 0, 0, 0, module.Decimal("0"), 0, None, module.Counter()),
    )
    assets = {
        "roadmap.svg": module.fallback_roadmap_svg(state),
        "banner.svg": module.fallback_banner_svg(state),
        "badges.svg": module.fallback_badges_svg(state),
    }
    for name, var in (
        ("roadmap.svg", "roadmap_version"),
        ("banner.svg", "banner_version"),
        ("badges.svg", "badges_version"),
    ):
        setattr(state, var, digest(assets[name])[:8])
    readme = module.compose_readme({name: module.fallback_body(name, state) for name in module.SECTION_ORDER})

    original = module.write_atomic

    def flaky(path: Path, data) -> None:
        if Path(path) == module.README_FILE:
            raise OSError("simulated disk failure")
        return original(path, data)

    module.write_atomic = flaky
    try:
        try:
            module.write_outputs(readme, assets, state)
            failed = False
        except OSError:
            failed = True
    finally:
        module.write_atomic = original

    check("write failure is reported", failed)
    check("README was not left behind", not module.README_FILE.exists())
    check(
        "images were rolled back",
        not any((asset_dir / name).exists() for name in ("roadmap.svg", "banner.svg", "badges.svg")),
    )


def test_svg_growth_and_escaping() -> None:
    print("\n[15] visuals grow safely and escape unusual names")
    module = load_generator()
    courses = []
    for index in range(14):
        name = f'Course {index} & <tag> "quoted"'
        course = module.Course(
            index=index,
            cfg={
                "key": f"c{index}",
                "name": name,
                "emoji": "📘",
                "aliases": (),
                "top_url": "https://example.com",
            },
            path=None,
        )
        course.status = "done" if index < 3 else "active" if index == 3 else "todo"
        course.total_folders = 4
        course.done_folders = 2
        course.progress = 0.5
        courses.append(course)
    state = module.State(
        today=module.today_ist(),
        repo_owner="acme",
        repo_name="odin",
        commits=[],
        courses=courses,
        work_folders=[],
        stats=module.Stats(
            1_234_567,
            900,
            4321,
            5000,
            module.Decimal("12345.5"),
            99,
            module.datetime(2026, 11, 15, 10, 0),
            module.Counter(),
        ),
    )

    svg = module.build_roadmap_svg(state)
    root = ET.fromstring(svg)
    height = int(root.get("height"))
    check("roadmap grows for extra courses", height > 920, height)
    outside = [
        element
        for element in root.iter()
        if element.tag.endswith(("text", "circle", "rect"))
        and float(element.get("y", element.get("cy", 0)) or 0) > height
    ]
    check("roadmap stays inside its canvas", not outside, outside[:2])
    check("roadmap validates with unusual names", module.validate_roadmap_svg(svg, state) == [])
    check("roadmap escapes ampersands", "&amp;" in svg)
    check("roadmap escapes angle brackets", "&lt;tag&gt;" in svg)

    badges = module.build_badges_svg(state)
    badge_root = ET.fromstring(badges)
    badge_width = int(badge_root.get("width"))
    check("badges grow for large stats", badge_width > 760, badge_width)
    check("badges validate with large stats", module.validate_badges_svg(badges, state) == [])
    check("huge study hours are capped", module.fmt_hours(module.Decimal("999999999")) == "100000+")
    for group in badge_root.iter("{http://www.w3.org/2000/svg}g"):
        match = re.match(r"translate\(([\d.]+), ([\d.]+)\)", group.get("transform", ""))
        if not match:
            continue
        group_x = float(match.group(1))
        for rect in group.iter("{http://www.w3.org/2000/svg}rect"):
            check(
                "badge stays inside its canvas",
                group_x + float(rect.get("width")) <= badge_width,
            )


def test_branch_aware_urls() -> None:
    print("\n[16] image URLs follow the actual default branch")
    repo = new_repo("branch")
    git(repo, "branch", "-m", "master")
    commit(repo, "ruby basics", {"ruby/a.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    result = run_script(repo)
    check("exit 0", result.returncode == 0, result.stderr)
    text = readme_text(repo)
    check("uses master in image URLs", "/master/.github/readme/" in text)
    check("does not hard-code main", "/main/.github/readme/" not in text)
    check("README is valid", load_generator().validate_readme(text, readme_assets(repo)) == [])

    env = {**BASE_ENV, "GITHUB_REPOSITORY": "acme/odin-learning", "ODIN_TODAY": TODAY, "GITHUB_REF_NAME": "release"}
    result = subprocess.run(
        [sys.executable, str(repo / ".github" / "readme" / "update_readme.py")],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    check("env branch exit 0", result.returncode == 0, result.stderr)
    check("env branch wins", "/release/.github/readme/" in readme_text(repo))


def test_safe_mode_always_valid() -> None:
    print("\n[17] the safe-mode README and fallbacks are always valid")
    module = load_generator()
    state = module.build_state()
    assets = {
        "roadmap.svg": module.fallback_roadmap_svg(state),
        "banner.svg": module.fallback_banner_svg(state),
        "badges.svg": module.fallback_badges_svg(state),
    }
    for filename, attr in (
        ("roadmap.svg", "roadmap_version"),
        ("banner.svg", "banner_version"),
        ("badges.svg", "badges_version"),
    ):
        setattr(state, attr, hashlib.sha256(assets[filename].encode("utf-8")).hexdigest()[:8])

    for name in module.SECTION_ORDER:
        body = module.fallback_body(name, state)
        problems = module.section_errors(name, body)
        check(f"fallback {name} is valid", problems == [], problems)
        check(f"fallback {name} is not empty", bool(body.strip()))

    readme = module.compose_readme({name: module.fallback_body(name, state) for name in module.SECTION_ORDER})
    problems = module.validate_readme(readme, assets, state)
    check("safe-mode README passes validation", problems == [], problems)
    check("safe-mode README has 9 sections", readme.count("<!--START_SECTION:") == 9)


def test_clone_and_shallow_clone() -> None:
    print("\n[18] generator works in a fresh shallow clone")
    repo = new_repo("clone")
    commit(repo, "rails first", {"rails/blog/app/models/post.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    commit(repo, "ruby fix [1.5h]", {"ruby/fix.rb": "x\n"}, "2026-11-06T10:00:00+05:30")
    check("source repo generation ok", run_script(repo).returncode == 0)

    clone = Path(tempfile.mkdtemp(prefix="odin2-clone-dest-")) / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", str(repo), str(clone)], check=True)
    env = {**BASE_ENV, "ODIN_TODAY": TODAY}
    result = subprocess.run(
        [sys.executable, str(clone / ".github" / "readme" / "update_readme.py")],
        cwd=clone,
        capture_output=True,
        text=True,
        env=env,
    )
    check("shallow clone exit 0", result.returncode == 0, result.stderr)
    text = readme_text(clone)
    check("shallow clone README is valid", load_generator().validate_readme(text, readme_assets(clone)) == [])
    check("falls back to known repo URLs", "/zeditya/Odin_RubyOnRails/main/.github/readme/" in text)
    check("shallow clone has no external images", "capsule-render" not in text and "img.shields.io" not in text)


def test_deleted_folder_not_counted() -> None:
    print("\n[19] deleted or renamed folders stop inflating progress")
    repo = new_repo("deleted")
    commit(repo, "rails old", {"rails/old/app.rb": "x\n"}, "2026-11-05T10:00:00+05:30")
    commit(repo, "rails new", {"rails/new/app.rb": "x\n"}, "2026-11-06T10:00:00+05:30")
    shutil.rmtree(repo / "rails" / "old")
    git(repo, "add", "-A")
    git(
        repo,
        "commit",
        "-q",
        "-m",
        "remove old",
        env_extra={
            "GIT_AUTHOR_DATE": "2026-11-07T10:00:00+05:30",
            "GIT_COMMITTER_DATE": "2026-11-07T10:00:00+05:30",
        },
    )
    result = run_script(repo)
    check("exit 0", result.returncode == 0, result.stderr)
    text = readme_text(repo)
    row = course_row(text, "Ruby on Rails")
    check("only the surviving folder is counted", "**1** folder" in row, row)
    check("deleted folder is not in Recent Work", "rails/old" not in section(text, "recent"))
    check("README is valid", load_generator().validate_readme(text, readme_assets(repo)) == [])


def main() -> int:
    test_normal_repo()
    test_empty_repo()
    test_non_git()
    test_no_course_folder()
    test_streak_grace()
    test_aliases()
    test_commit_fallback()
    test_ror_does_not_match_error()
    test_static_no_projects()
    test_validator_rejects_broken_output()
    test_repairs_corrupted_readme()
    test_pipe_in_folder_name()
    test_bad_repo_env_is_ignored()
    test_write_rollback()
    test_svg_growth_and_escaping()
    test_branch_aware_urls()
    test_safe_mode_always_valid()
    test_clone_and_shallow_clone()
    test_deleted_folder_not_counted()

    print("\n" + "=" * 70)
    print(f"{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED: " + ", ".join(FAIL))
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
