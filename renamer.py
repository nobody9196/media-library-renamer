#!/usr/bin/env python3
"""
media-library-renamer
---------------------
Rename and organize movies, TV shows, and anime into a clean
Plex / Jellyfin / Emby compatible folder structure using the
TMDB API (free) — or fall back to pattern-only renaming when
no API key is provided.

Folder output:
  Movies/
    The Dark Knight (2008)/
      The Dark Knight (2008).mkv

  TV Shows/
    Breaking Bad/
      Season 01/
        Breaking Bad - S01E01 - Pilot.mkv

  Anime/
    Attack on Titan/
      Season 01/
        Attack on Titan - S01E01 - To You, in 2000 Years.mkv

Usage:
  # Dry run (default — nothing is moved):
  python3 renamer.py --source /path/to/messy/files

  # Dry run with TMDB metadata:
  python3 renamer.py --source /path/to/messy/files --api-key YOUR_TMDB_KEY

  # Actually rename/move files:
  python3 renamer.py --source /path/to/messy/files --dest /path/to/library --execute

Get a free TMDB API key at: https://www.themoviedb.org/settings/api
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv",
                    ".ts", ".m2ts", ".mpg", ".mpeg", ".webm"}

# Noise tokens to strip from filenames before searching
NOISE_RE = re.compile(
    r"\b("
    r"bluray|blu[\-\s]?ray|bdrip|brrip|"
    r"webrip|web[\-\s]?dl|hdtv|hdrip|dvdrip|dvdscr|"
    r"4k|2160p|1080p|1080i|720p|480p|360p|"
    r"x264|x265|h264|h265|hevc|avc|xvid|divx|"
    r"aac|ac3|dts|mp3|flac|dd5[\.\s]1|truehd|"
    r"yify|yts|rarbg|ettv|eztv|"
    r"extended|theatrical|directors[\.\s]cut|remastered|"
    r"proper|repack|readnfo|"
    r"10bit|hdr|dolby|vision|atmos"
    r")\b",
    re.IGNORECASE,
)

# Season + episode patterns — ordered most-specific first
EPISODE_PATTERNS = [
    # S01E02, S01E02E03
    re.compile(r"[Ss](\d{1,2})[Ee](\d{2,3})(?:[Ee]\d{2,3})?"),
    # 1x02
    re.compile(r"(\d{1,2})[xX](\d{2,3})"),
    # Season 1 Episode 2
    re.compile(r"[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,3})", re.IGNORECASE),
    # E02 (episode only — assume season 1)
    re.compile(r"(?<!\d)[Ee](\d{2,3})(?!\d)"),
]

# Year pattern
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[012]\d)\b")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class MediaInfo:
    original_path: Path
    media_type: str          # 'movie', 'tv', 'anime', 'unknown'
    raw_title: str           # cleaned title string used for API search
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    # Filled in after API lookup:
    resolved_title: Optional[str] = None
    resolved_year: Optional[int] = None
    resolved_episode_title: Optional[str] = None

@dataclass
class RenameAction:
    source: Path
    destination: Path
    dry_run: bool = True


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

def clean_title(raw: str) -> str:
    """Strip noise tokens and normalise separators."""
    s = re.sub(r"[._\-]", " ", raw)
    s = NOISE_RE.sub(" ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def parse_filename(path: Path) -> MediaInfo:
    """Extract all available info from a filename alone."""
    stem = path.stem

    # Try episode patterns
    season, episode = None, None
    ep_match_pos = len(stem)
    for pat in EPISODE_PATTERNS:
        m = pat.search(stem)
        if m:
            groups = m.groups()
            if len(groups) == 2:
                season, episode = int(groups[0]), int(groups[1])
            else:
                season, episode = 1, int(groups[0])
            ep_match_pos = m.start()
            break

    # Title is everything before the episode marker (or before the year)
    title_raw = stem[:ep_match_pos]

    # Year
    year = None
    ym = YEAR_RE.search(title_raw)
    if ym:
        year = int(ym.group(1))
        title_raw = title_raw[:ym.start()]

    title = clean_title(title_raw).title()

    # Guess media type
    if season is not None or episode is not None:
        media_type = "tv"
    elif year is not None:
        media_type = "movie"
    else:
        media_type = "unknown"

    return MediaInfo(
        original_path=path,
        media_type=media_type,
        raw_title=title,
        year=year,
        season=season,
        episode=episode,
    )


# ---------------------------------------------------------------------------
# TMDB API client
# ---------------------------------------------------------------------------

TMDB_BASE = "https://api.themoviedb.org/3"


def tmdb_get(endpoint: str, api_key: str, params: dict) -> dict:
    params["api_key"] = api_key
    url = f"{TMDB_BASE}{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  [TMDB] HTTP {e.code} for {url}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"  [TMDB] Error: {e}", file=sys.stderr)
        return {}


def tmdb_search_movie(title: str, year: Optional[int], api_key: str) -> Optional[dict]:
    params: dict = {"query": title, "include_adult": "false"}
    if year:
        params["year"] = year
    data = tmdb_get("/search/movie", api_key, params)
    results = data.get("results", [])
    return results[0] if results else None


def tmdb_search_tv(title: str, api_key: str) -> Optional[dict]:
    data = tmdb_get("/search/tv", api_key, {"query": title})
    results = data.get("results", [])
    return results[0] if results else None


def tmdb_get_episode(show_id: int, season: int, episode: int, api_key: str) -> Optional[dict]:
    data = tmdb_get(f"/tv/{show_id}/season/{season}/episode/{episode}", api_key, {})
    return data if data.get("name") else None


def resolve_with_tmdb(info: MediaInfo, api_key: str) -> MediaInfo:
    if info.media_type in ("tv", "anime"):
        result = tmdb_search_tv(info.raw_title, api_key)
        if result:
            info.resolved_title = result.get("name", info.raw_title)
            first_air = result.get("first_air_date", "")
            info.resolved_year = int(first_air[:4]) if first_air else None
            if info.season and info.episode:
                ep = tmdb_get_episode(result["id"], info.season, info.episode, api_key)
                if ep:
                    info.resolved_episode_title = ep.get("name")
    else:
        result = tmdb_search_movie(info.raw_title, info.year, api_key)
        if result:
            info.resolved_title = result.get("title", info.raw_title)
            release = result.get("release_date", "")
            info.resolved_year = int(release[:4]) if release else None
            info.media_type = "movie"
    return info


# ---------------------------------------------------------------------------
# Destination path builders
# ---------------------------------------------------------------------------

SAFE_CHARS_RE = re.compile(r'[<>:"/\\|?*]')


def safe(s: str) -> str:
    """Strip characters that are illegal in filenames on most OSes."""
    return SAFE_CHARS_RE.sub("", s).strip(" .")


def build_destination(info: MediaInfo, library_root: Path) -> Path:
    ext = info.original_path.suffix
    title = safe(info.resolved_title or info.raw_title)
    year = info.resolved_year or info.year

    if info.media_type == "movie":
        folder_name = f"{title} ({year})" if year else title
        return library_root / "Movies" / folder_name / f"{folder_name}{ext}"

    # TV or anime
    category = "Anime" if info.media_type == "anime" else "TV Shows"
    season_num = info.season or 1
    episode_num = info.episode or 1
    season_folder = f"Season {season_num:02d}"

    ep_tag = f"S{season_num:02d}E{episode_num:02d}"
    if info.resolved_episode_title:
        ep_title = safe(info.resolved_episode_title)
        filename = f"{title} - {ep_tag} - {ep_title}{ext}"
    else:
        filename = f"{title} - {ep_tag}{ext}"

    return library_root / category / title / season_folder / filename


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def collect_video_files(source: Path) -> list[Path]:
    files = []
    for f in sorted(source.rglob("*")):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            files.append(f)
    return files


def plan_renames(
    files: list[Path],
    library_root: Path,
    api_key: Optional[str],
    force_type: Optional[str],
) -> list[RenameAction]:
    actions = []
    for f in files:
        info = parse_filename(f)
        if force_type:
            info.media_type = force_type
        if api_key:
            info = resolve_with_tmdb(info, api_key)
        dest = build_destination(info, library_root)
        actions.append(RenameAction(source=f, destination=dest))
    return actions


def print_plan(actions: list[RenameAction]) -> None:
    print(f"\n{'DRY RUN — no files will be moved':^60}")
    print("=" * 60)
    for a in actions:
        print(f"\n  FROM  {a.source}")
        print(f"  TO    {a.destination}")
    print(f"\n{len(actions)} file(s) would be renamed/moved.")
    print("Re-run with --execute to apply changes.\n")


def execute_renames(actions: list[RenameAction]) -> None:
    moved, skipped = 0, 0
    for a in actions:
        try:
            a.destination.parent.mkdir(parents=True, exist_ok=True)
            if a.destination.exists():
                print(f"  SKIP (already exists): {a.destination.name}")
                skipped += 1
                continue
            shutil.move(str(a.source), str(a.destination))
            print(f"  OK  {a.source.name}")
            print(f"   -> {a.destination}")
            moved += 1
        except Exception as e:
            print(f"  ERROR moving {a.source.name}: {e}", file=sys.stderr)
    print(f"\nDone. {moved} moved, {skipped} skipped.\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="renamer",
        description=(
            "Rename and organize movies/TV shows/anime into a "
            "Plex/Jellyfin/Emby-compatible library structure."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--source", "-s",
        required=True,
        help="Folder containing the messy video files to rename.",
    )
    p.add_argument(
        "--dest", "-d",
        default=None,
        help=(
            "Root of the organised library. "
            "Defaults to the source folder if omitted."
        ),
    )
    p.add_argument(
        "--api-key", "-k",
        default=os.environ.get("TMDB_API_KEY"),
        help=(
            "TMDB API key for metadata lookup. "
            "Can also be set via the TMDB_API_KEY environment variable. "
            "Get a free key at https://www.themoviedb.org/settings/api"
        ),
    )
    p.add_argument(
        "--type", "-t",
        choices=["movie", "tv", "anime"],
        default=None,
        dest="force_type",
        help="Force all files in --source to be treated as this type.",
    )
    p.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help=(
            "Actually move/rename files. "
            "Without this flag the script runs in dry-run mode "
            "and only prints what it would do."
        ),
    )
    return p


def main() -> None:
    args = build_parser().parse_args()

    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        sys.exit(f"Error: --source '{source}' is not a directory.")

    dest = Path(args.dest).expanduser().resolve() if args.dest else source

    if not args.api_key:
        print(
            "Note: no TMDB API key provided. Running in pattern-only mode "
            "(titles are cleaned from filenames, not verified against TMDB).\n"
            "Get a free key at https://www.themoviedb.org/settings/api\n"
        )

    print(f"Scanning:  {source}")
    print(f"Library:   {dest}")
    print(f"TMDB API:  {'yes' if args.api_key else 'no (pattern-only)'}")
    print(f"Mode:      {'EXECUTE' if args.execute else 'DRY RUN'}\n")

    files = collect_video_files(source)
    if not files:
        sys.exit("No video files found.")

    print(f"Found {len(files)} video file(s). Planning renames...")
    actions = plan_renames(files, dest, args.api_key, args.force_type)

    if args.execute:
        execute_renames(actions)
    else:
        print_plan(actions)


if __name__ == "__main__":
    main()
