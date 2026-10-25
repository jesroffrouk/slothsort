"""
SlothSort - a lazy, fully local file tidier powered by an open-weight model.

Point it at a messy folder (default: ~/Downloads). A local LLM running in
Ollama reads each file's name + a snippet of its contents, picks a category,
and (optionally) suggests a clean filename. Old files get archived by year.

Everything runs on your machine: no cloud, no API keys, no internet needed.
Only the Python standard library is used.

Setup (once):
    1. Install Ollama            https://ollama.com
    2. ollama pull llama3.2:3b   (any small open-weight model works)
    3. python slothsort.py

Usage:
    python slothsort.py                      # dry run on ~/Downloads
    python slothsort.py ~/Desktop --apply    # actually move files
    python slothsort.py --apply --rename     # also give files clean names
    python slothsort.py --undo               # revert the last run
    python slothsort.py --apply --watch      # sloth mode: check every 5 min
    python slothsort.py --no-llm             # extension rules only
"""

import argparse
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("SLOTH_MODEL", "llama3.2:3b")
LOG_NAME = ".slothsort_log.json"

CATEGORIES = [
    "Documents", "Images", "Videos", "Audio", "Code", "Archives",
    "Installers", "Spreadsheets", "Presentations", "Books", "Misc",
]

# Fallback / hint rules based on extension alone.
EXT_MAP = {
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".md", ".rtf", ".odt"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".heic", ".bmp"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
    "Audio": {".mp3", ".wav", ".flac", ".m4a", ".ogg"},
    "Code": {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".html",
             ".css", ".json", ".yaml", ".yml", ".sh", ".ipynb"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".apk"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods"},
    "Presentations": {".ppt", ".pptx", ".key", ".odp"},
    "Books": {".epub", ".mobi", ".azw3"},
}

# Files we can safely read as text to give the model some context.
TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".log",
             ".yaml", ".yml", ".rtf", ".sh", ".ts", ".java", ".c", ".cpp"}

SKIP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download"}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def category_from_ext(path: Path) -> str:
    ext = path.suffix.lower()
    for cat, exts in EXT_MAP.items():
        if ext in exts:
            return cat
    return "Misc"


def read_snippet(path: Path, limit: int = 600) -> str:
    if path.suffix.lower() not in TEXT_EXTS:
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limit).strip()
    except OSError:
        return ""


def slugify(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name).strip().lower()
    name = re.sub(r"[\s_-]+", "-", name)
    return name[:60].strip("-")


def unique_path(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix, i = dest.stem, dest.suffix, 1
    while True:
        candidate = dest.with_name(f"{stem}-{i}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


# --------------------------------------------------------------------------
# Local LLM (Ollama)
# --------------------------------------------------------------------------
def ollama_alive() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3)
        return True
    except (urllib.error.URLError, OSError):
        return False


def ask_model(model: str, path: Path, want_rename: bool) -> dict:
    snippet = read_snippet(path)
    hint = category_from_ext(path)
    prompt = (
        "You are a tidy file organizer. Classify this file.\n"
        f"Filename: {path.name}\n"
        f"Extension hint suggests: {hint}\n"
        f"Content preview: {snippet or '(not available)'}\n\n"
        f"Choose ONE category from: {', '.join(CATEGORIES)}.\n"
        + ("Also suggest a short, descriptive, lowercase-hyphenated "
           "filename WITHOUT extension (max 6 words) as 'new_name'.\n"
           if want_rename else "")
        + 'Reply ONLY with JSON like {"category": "...", "new_name": "..."}'
    )
    body = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = json.loads(resp.read())["response"]
    data = json.loads(raw)
    cat = str(data.get("category", "")).strip().title()
    if cat not in CATEGORIES:
        cat = hint
    return {"category": cat, "new_name": str(data.get("new_name", "") or "")}


# --------------------------------------------------------------------------
# Core logic
# --------------------------------------------------------------------------
def plan_moves(root: Path, args, use_llm: bool) -> list:
    moves = []
    now = time.time()
    for entry in sorted(root.iterdir()):
        if not entry.is_file() or entry.name.startswith("."):
            continue
        if entry.suffix.lower() in SKIP_SUFFIXES:
            continue

        # Don't touch files still being written (modified in last 2 minutes).
        age_secs = now - entry.stat().st_mtime
        if age_secs < 120:
            continue

        category, new_stem = category_from_ext(entry), ""
        if use_llm:
            try:
                result = ask_model(args.model, entry, args.rename)
                category, new_stem = result["category"], slugify(result["new_name"])
            except Exception as e:  # model hiccup -> fall back, never crash
                print(f"  ! model failed on {entry.name} ({e}); using extension rule")

        dest_dir = root / category
        if age_secs > args.archive_days * 86400:
            year = datetime.fromtimestamp(entry.stat().st_mtime).year
            dest_dir = root / "Archive" / str(year) / category

        new_name = f"{new_stem}{entry.suffix.lower()}" if (args.rename and new_stem) else entry.name
        moves.append((entry, dest_dir / new_name))
    return moves


def run_once(root: Path, args) -> None:
    use_llm = not args.no_llm
    if use_llm and not ollama_alive():
        print("Ollama isn't running - falling back to extension rules. "
              "(Start it with `ollama serve`, or pass --no-llm to silence this.)")
        use_llm = False

    print(f"SlothSort looking at {root} "
          f"[{'model: ' + args.model if use_llm else 'rules only'}]")
    moves = plan_moves(root, args, use_llm)

    if not moves:
        print("Nothing to tidy. Sloth approves.")
        return

    performed = []
    for src, dst in moves:
        print(f"  {src.name}  ->  {dst.relative_to(root)}")
        if args.apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            final = unique_path(dst)
            shutil.move(str(src), str(final))
            performed.append({"src": str(src), "dst": str(final)})

    if args.apply:
        save_log(root, performed)
        print(f"\nMoved {len(performed)} file(s). Undo with: "
              f"python {Path(sys.argv[0]).name} {root} --undo")
    else:
        print(f"\nDry run: {len(moves)} file(s) would move. Add --apply to do it.")


# --------------------------------------------------------------------------
# Undo log
# --------------------------------------------------------------------------
def save_log(root: Path, performed: list) -> None:
    log_path = root / LOG_NAME
    runs = []
    if log_path.exists():
        try:
            runs = json.loads(log_path.read_text())
        except json.JSONDecodeError:
            runs = []
    runs.append({"time": datetime.now().isoformat(timespec="seconds"),
                 "moves": performed})
    log_path.write_text(json.dumps(runs, indent=2))


def undo_last(root: Path) -> None:
    log_path = root / LOG_NAME
    if not log_path.exists():
        print("No history found - nothing to undo.")
        return
    runs = json.loads(log_path.read_text())
    if not runs:
        print("History is empty - nothing to undo.")
        return
    last = runs.pop()
    restored = 0
    for m in reversed(last["moves"]):
        src, dst = Path(m["src"]), Path(m["dst"])
        if dst.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(unique_path(src)))
            restored += 1
    log_path.write_text(json.dumps(runs, indent=2))
    print(f"Restored {restored} file(s) from run at {last['time']}.")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description="Lazy local AI file tidier.")
    p.add_argument("folder", nargs="?", default=str(Path.home() / "Downloads"),
                   help="folder to tidy (default: ~/Downloads)")
    p.add_argument("--apply", action="store_true", help="actually move files")
    p.add_argument("--rename", action="store_true", help="let the model rename files")
    p.add_argument("--undo", action="store_true", help="revert the last run")
    p.add_argument("--watch", action="store_true", help="keep running, tidy periodically")
    p.add_argument("--interval", type=int, default=300, help="watch interval in seconds")
    p.add_argument("--archive-days", type=int, default=90,
                   help="files older than this go to Archive/<year>/ (default 90)")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    p.add_argument("--no-llm", action="store_true", help="skip the model, use extension rules")
    args = p.parse_args()

    root = Path(args.folder).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"Not a folder: {root}")

    if args.undo:
        undo_last(root)
        return

    if args.watch:
        print(f"Sloth mode on. Checking every {args.interval}s. Ctrl+C to nap.")
        try:
            while True:
                run_once(root, args)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nGoing back to sleep. Zzz...")
    else:
        run_once(root, args)


if __name__ == "__main__":
    main()
