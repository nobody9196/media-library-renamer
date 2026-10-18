#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renamer_zh.py v2 — 群晖 Video Station + TMDB 中文/综艺优化版
在 media-library-renamer 基础上新增：
  SxxExx / SE01.01 / 1x02 / 第X集 / 第X话 / 第X期 / 纯数字集数(01、001、01-4K、23.4K、12~4K)
  从目录名识别"第X季"；标题缺失时回退到父目录；识别综艺(日期前缀/综艺目录)。
只生成"改名对照表"（dry-run，绝不移动文件）。
"""
import argparse, json, re
from pathlib import Path

VIDEO_EXT = {".mkv",".mp4",".avi",".mov",".m4v",".wmv",".flv",".ts",".m2ts",".mpg",".mpeg",".webm"}

NOISE = re.compile(
    r"(?:\b|[-._])(bluray|blu[\-\s]?ray|bdrip|brrip|webrip|web[\-\s]?dl|hdtv|hdrip|dvdrip|dvdscr|"
    r"4k|2160p|1080p|1080i|720p|480p|360p|x264|x265|h264|h265|hevc|avc|xvid|divx|"
    r"aac|ac3|dts|mp3|flac|dd5[\d.\s]?1|truehd|yify|yts|rarbg|ettv|eztv|extended|theatrical|"
    r"directors[\s.\-]?cut|remastered|proper|repack|readnfo|10bit|hdr|dolby|vision|atmos|"
    r"complete|web|xunlei|seeweb|multi|rar|download|高清|高码率|内嵌)(?:\b|[-._])",
    re.IGNORECASE)

# (名称, 正则, 是否为"仅集数无季"模式)
EP_PATTERNS = [
    ("SxxExx",   re.compile(r"[Ss](\d{1,2})[Ee](\d{2,3})(?:[Ee](\d{2,3}))?"), False),
    ("SE.dot",   re.compile(r"[Ss][Ee](\d{1,2})[\._\-](\d{2,3})"), False),
    ("NxN",      re.compile(r"(?<!\d)(\d{1,2})[xX](\d{2,3})"), False),
    ("SeasonEp", re.compile(r"[Ss]eason\s*(\d{1,2})\s*[Ee]pisode\s*(\d{1,3})", re.IGNORECASE), False),
    ("第X集",    re.compile(r"第\s*(\d{1,3})\s*集"), True),
    ("第X话",    re.compile(r"第\s*(\d{1,3})\s*[话話]"), True),
    ("第X期",    re.compile(r"第\s*(\d{1,3})\s*期"), True),
    ("EPdigit",  re.compile(r"(?<!\d)[Ee][Pp]?\s*(\d{2,3})(?!\d)"), True),
    ("数字集",   re.compile(r"(?:^(\d{1,3})[\s._~\-]|^(\d{1,3})$|\s(\d{1,3})$|(?<![A-Za-z\d])(\d{1,3})\s+[A-Za-z])"), True),
    ("Eonly",    re.compile(r"(?<!\d)[Ee](\d{2,3})(?!\d)"), True),
]

YEAR_RE = re.compile(r"\b(19[5-9]\d|20[012]\d)\b")
SPECIAL_HINT = re.compile(r"特别篇|番外|剧场版|特典|特辑|超前|彩蛋|花絮|纯享|直拍|vlog|sp\b|ova\b|oad\b|special|pilot|\bS00", re.IGNORECASE)
DATE_PREFIX = re.compile(r"^(20\d{6})[\s._\-]")

def season_from_folders(path):
    for part in reversed(list(path.parts)):
        m = re.search(r"第\s*(\d{1,2})\s*季", part)
        if m:
            return int(m.group(1))
    for part in reversed(list(path.parts)):
        m = re.search(r"[Ss](\d{2})", part)
        if m:
            return int(m.group(1))
    return None

def clean_title(s):
    s = re.sub(r"[._\-]+", " ", s)
    s = NOISE.sub(" ", s)
    s = re.sub(r"\[.*?\]", " ", s)
    s = re.sub(r"（.*?）", " ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip(" .-_")
    return s

def parse(path):
    stem = path.stem
    season = episode = None
    patname = None
    mpos = len(stem)
    for name, pat, ep_only in EP_PATTERNS:
        m = pat.search(stem)
        if m:
            g = m.groups()
            if ep_only:
                # 取第一个非 None 的组作为集数
                for v in g:
                    if v is not None:
                        episode = int(v); break
                season = None
            else:
                season = int(g[0]); episode = int(g[1])
            patname = name
            mpos = m.start()
            break
    if season is None and episode is not None:
        season = season_from_folders(path)
    title_raw = stem[:mpos] if (season or episode) else stem
    year = None
    ym = YEAR_RE.search(title_raw)
    if ym:
        year = int(ym.group(1)); title_raw = title_raw[:ym.start()]
    title = clean_title(title_raw)
    # 标题缺失 → 回退到父目录
    if not title:
        title = clean_title(path.parent.name)
    # 类型
    is_variety = (path.parts and "综艺" in path.parts) or bool(DATE_PREFIX.search(stem))
    if season is not None or episode is not None:
        kind = "variety" if is_variety else "tv"
    elif year is not None:
        kind = "movie"
    else:
        kind = "unknown"
    is_special = bool(SPECIAL_HINT.search(stem)) or season == 0
    return dict(file=str(path), title=title, year=year, season=season, episode=episode,
                kind=kind, pat=patname, special=is_special)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source","-s", required=True)
    ap.add_argument("--out","-o", default="rename_plan.json")
    args = ap.parse_args()
    src = Path(args.source).expanduser().resolve()
    files = [f for f in sorted(src.rglob("*")) if f.is_file() and f.suffix.lower() in VIDEO_EXT]
    rows = [parse(f) for f in files]
    kinds = {}; pats = {}; specials = 0; unparsed = []
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"],0)+1
        pats[r["pat"] or "(无匹配)"] = pats.get(r["pat"] or "(无匹配)",0)+1
        if r["special"]: specials += 1
        if r["season"] is None and r["episode"] is None and r["year"] is None:
            unparsed.append(r["file"])
    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"扫描文件: {len(files)}")
    print(f"类型分布: {kinds}")
    print(f"集数解析方式: {pats}")
    print(f"番外/特别篇/花絮等: {specials}")
    print(f"完全无法解析: {len(unparsed)}")
    for u in unparsed[:50]:
        print("  ?", u.replace("/volume4/影视/",""))
    print(f"明细已写入: {args.out}")

if __name__ == "__main__":
    main()
