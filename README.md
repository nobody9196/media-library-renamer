# media-library-renamer

Rename and organise messy movie / TV show / anime files into a clean, **Plex / Jellyfin / Emby-compatible** folder structure — in one command.

Uses the free [TMDB API](https://www.themoviedb.org/settings/api) to fetch proper titles, years, and episode names. Works offline too (pattern-only mode, no API key needed).

---

## The problem it solves

Your downloads folder probably looks like this:

```
The.Dark.Knight.2008.1080p.BluRay.x264-YIFY.mkv
breaking.bad.s01e01.720p.HDTV.mkv
Attack.on.Titan.S03E22.HEVC.mkv
```

After running this script your library looks like this:

```
Movies/
  The Dark Knight (2008)/
    The Dark Knight (2008).mkv

TV Shows/
  Breaking Bad/
    Season 01/
      Breaking Bad - S01E01 - Pilot.mkv

Anime/
  Attack on Titan/
    Season 03/
      Attack on Titan - S03E22 - The Walls.mkv
```

Works perfectly as the first step before adding your library to Plex, Jellyfin, or Emby.

---

## Features

- **TMDB metadata** — resolves proper titles, release years, and episode names via the free TMDB API
- **Pattern-only fallback** — works with no API key; cleans filenames using regex alone
- **Auto-detects media type** — movie vs TV episode vs anime from filename patterns
- **Episode detection** — handles `S01E02`, `1x02`, `Season 1 Episode 2`, `E02`, and more
- **Noise stripping** — removes release group tags: `BluRay`, `x264`, `HEVC`, `YIFY`, `RARBG`, etc.
- **Dry-run by default** — shows exactly what would happen before touching a single file
- **Plex / Jellyfin / Emby naming spec** — output structure matches what all major media servers expect
- **No dependencies** — pure Python standard library, nothing to install

---

## Requirements

- Python 3.8 or newer
- No third-party packages required
- A free [TMDB API key](https://www.themoviedb.org/settings/api) *(optional but recommended)*

---

## Getting a free TMDB API key

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/signup)
2. Go to **Settings → API**
3. Request a key (Developer / Personal use)
4. Copy the **API Key (v3 auth)** value

---

## Usage

### Dry run (safe — shows what would happen, moves nothing)

```bash
python3 renamer.py --source /path/to/messy/files
```

### Dry run with TMDB metadata

```bash
python3 renamer.py --source /path/to/messy/files --api-key YOUR_TMDB_KEY
```

Or set your key as an environment variable so you never have to type it:

```bash
export TMDB_API_KEY=your_key_here
python3 renamer.py --source /path/to/messy/files
```

### Actually rename and move the files

```bash
python3 renamer.py --source /path/to/messy/files --dest /path/to/library --execute
```

### Force all files to be treated as a specific type

```bash
# All files are anime
python3 renamer.py --source /path/to/anime --type anime --execute

# All files are movies
python3 renamer.py --source /path/to/movies --type movie --execute
```

### Move files into a separate library root

```bash
python3 renamer.py \
  --source ~/Downloads/new-stuff \
  --dest ~/Media/Library \
  --api-key YOUR_TMDB_KEY \
  --execute
```

---

## Output structure

```
<library-root>/
├── Movies/
│   └── Movie Title (Year)/
│       └── Movie Title (Year).mkv
├── TV Shows/
│   └── Show Name/
│       └── Season 01/
│           └── Show Name - S01E02 - Episode Title.mkv
└── Anime/
    └── Anime Name/
        └── Season 01/
            └── Anime Name - S01E01 - Episode Title.mkv
```

This matches the naming conventions expected by **Plex**, **Jellyfin**, and **Emby** out of the box, so your metadata and artwork will load automatically after you point your media server at the library root.

---

## All flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--source` | `-s` | *(required)* | Folder of messy video files to rename |
| `--dest` | `-d` | same as `--source` | Root of the organised library output |
| `--api-key` | `-k` | `$TMDB_API_KEY` env var | TMDB API key for metadata lookup |
| `--type` | `-t` | auto-detect | Force type: `movie`, `tv`, or `anime` |
| `--execute` | | `False` | Actually move files (default is dry-run) |

---

## Supported episode filename patterns

| Pattern | Example |
|---|---|
| `S01E02` | `Show.S01E02.mkv` |
| `s01e02` | `show.s01e02.mkv` |
| `1x02` | `Show.1x02.mkv` |
| `Season 1 Episode 2` | `Show Season 1 Episode 2.mkv` |
| `E02` (episode only) | `Show.E02.mkv` → Season 1 assumed |

---

## Supported video formats

`.mkv` `.mp4` `.avi` `.mov` `.m4v` `.wmv` `.flv` `.ts` `.m2ts` `.mpg` `.mpeg` `.webm`

---

## License

[MIT](LICENSE) — free to use, modify, and distribute.

---

## Contributing

Issues and PRs welcome. If a filename pattern isn't being detected correctly, open an issue and paste the filename — I'll add support for it.
