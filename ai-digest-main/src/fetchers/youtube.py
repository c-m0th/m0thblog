"""
fetchers/youtube.py — 抓取 YouTube 频道最新视频及字幕

1. feedparser 携带真实浏览器 User-Agent 请求 YouTube RSS
2. 字幕优先用 yt-dlp（内置反爬，支持 cookies），其次 youtube-transcript-api
3. 两者均失败则用视频描述作为内容
4. 请求间随机延迟，避免触发频率限制
"""
from __future__ import annotations

import os
import re
import time
import random
import tempfile
import subprocess
import json
import feedparser
import requests
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

from src.utils.logger import get_logger
from src.utils.database import is_processed

logger = get_logger("youtube")

YOUTUBE_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

# 模拟真实浏览器请求头
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _get_video_id(url: str) -> str | None:
    match = re.search(r"[?&]v=([^&]+)", url)
    return match.group(1) if match else None


# ─────────────────────────────────────────────────────────────
# 方法一：yt-dlp 获取字幕（最稳，内置反爬）
# ─────────────────────────────────────────────────────────────

def _get_transcript_ytdlp(video_id: str) -> str | None:
    """
    用 yt-dlp 下载字幕（仅元数据，不下载视频）。
    支持通过环境变量 YT_COOKIES_FILE 传入 cookies 文件路径以绕过登录限制。
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    cookies_file = os.environ.get("YT_COOKIES_FILE", "")

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = [
            "yt-dlp",
            "--skip-download",              # 不下载视频
            "--write-auto-sub",             # 自动生成字幕
            "--write-sub",                  # 手动字幕
            "--sub-langs", "zh-Hans,zh,en", # 语言优先级
            "--sub-format", "json3",        # JSON 格式方便解析
            "--output", f"{tmpdir}/%(id)s", # 输出路径
            "--no-playlist",
            "--quiet",
            "--no-warnings",
            "--extractor-retries", "3",
            "--sleep-interval", "2",        # 请求间隔，避免限流
        ]

        if cookies_file and os.path.exists(cookies_file):
            cmd += ["--cookies", cookies_file]
            logger.info(f"[yt-dlp] 使用 cookies 文件: {cookies_file}")

        cmd.append(url)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"[yt-dlp] 字幕下载超时: {video_id}")
            return None
        except FileNotFoundError:
            logger.warning("[yt-dlp] yt-dlp 未安装，跳过")
            return None

        # 查找下载的字幕文件（支持多语言后缀）
        import glob
        sub_files = (
            glob.glob(f"{tmpdir}/*.zh-Hans.json3")
            + glob.glob(f"{tmpdir}/*.zh.json3")
            + glob.glob(f"{tmpdir}/*.en.json3")
        )

        if not sub_files:
            logger.warning(f"[yt-dlp] 未找到字幕文件: {video_id}")
            return None

        # 解析 json3 格式字幕
        try:
            with open(sub_files[0], encoding="utf-8") as f:
                data = json.load(f)
            texts = []
            for event in data.get("events", []):
                for seg in event.get("segs", []):
                    t = seg.get("utf8", "").strip()
                    if t and t != "\n":
                        texts.append(t)
            transcript = " ".join(texts).strip()
            if transcript:
                logger.info(f"[yt-dlp] 字幕获取成功: {video_id}，{len(transcript)} 字符")
                return transcript
        except Exception as e:
            logger.warning(f"[yt-dlp] 字幕解析失败: {e}")

    return None


# ─────────────────────────────────────────────────────────────
# 方法二：youtube-transcript-api（备用）
# ─────────────────────────────────────────────────────────────

def _get_transcript_api(video_id: str) -> str | None:
    """备用：youtube-transcript-api，GitHub Actions IP 可能被限"""
    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
        )
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        for lang in ["zh-Hans", "zh", "en"]:
            try:
                transcript = transcript_list.find_transcript([lang])
                segments = transcript.fetch()
                return " ".join(s["text"] for s in segments)
            except Exception:
                continue
        # 兜底任意语言
        transcript = next(iter(transcript_list))
        segments = transcript.fetch()
        return " ".join(s["text"] for s in segments)
    except Exception as e:
        logger.warning(f"[transcript-api] 失败: {video_id}: {e}")
        return None


def _get_transcript(video_id: str) -> str | None:
    """字幕获取总入口：yt-dlp → transcript-api → None"""
    transcript = _get_transcript_ytdlp(video_id)
    if transcript:
        return transcript
    logger.info(f"[YouTube] yt-dlp 失败，尝试 transcript-api: {video_id}")
    return _get_transcript_api(video_id)


# ─────────────────────────────────────────────────────────────
# RSS 抓取（带真实浏览器 User-Agent）
# ─────────────────────────────────────────────────────────────

def _fetch_rss(channel_id: str) -> feedparser.FeedParserDict:
    """
    feedparser 默认 User-Agent 会被 YouTube 识别为爬虫。
    改用 requests 先下载 XML，再交给 feedparser 解析。
    """
    url = YOUTUBE_RSS.format(channel_id=channel_id)
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        resp.raise_for_status()
        return feedparser.parse(resp.text)
    except Exception as e:
        logger.warning(f"[YouTube RSS] requests 失败（{e}），尝试直接 feedparser")
        # 兜底：直接用 feedparser（可能被拦截）
        feedparser.USER_AGENT = BROWSER_HEADERS["User-Agent"]
        return feedparser.parse(url)


# ─────────────────────────────────────────────────────────────
# 主入口
# ─────────────────────────────────────────────────────────────

def fetch_channel(channel_config: dict, days_lookback: int, max_items: int) -> list[dict]:
    channel_id = channel_config["channel_id"]
    name = channel_config["name"]
    results = []

    feed = _fetch_rss(channel_id)

    if not feed.entries:
        logger.warning(f"[YouTube] {name} RSS 为空（可能被拦截，见文档说明）")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback + 1)
    count = 0

    for entry in feed.entries:
        if count >= max_items:
            break

        video_url = entry.get("link", "")
        video_id = _get_video_id(video_url)
        if not video_id:
            continue

        published = entry.get("published_parsed")
        if published:
            pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
            if pub_dt < cutoff:
                continue

        if is_processed(video_url):
            logger.info(f"[YouTube] 已处理，跳过: {entry.get('title', '')}")
            continue

        logger.info(f"[YouTube] 处理: {entry.get('title', '')} ({name})")

        # 随机延迟 1-3 秒，避免频繁请求触发限流
        time.sleep(random.uniform(1, 3))

        transcript = _get_transcript(video_id)
        description = entry.get("summary", "")
        content_text = transcript or description or ""

        if not content_text.strip():
            continue

        thumbnail = ""
        media = entry.get("media_thumbnail", [])
        if media:
            thumbnail = media[0].get("url", "")

        results.append({
            "platform": "YouTube",
            "source_name": name,
            "title": entry.get("title", "无标题"),
            "url": video_url,
            "thumbnail": thumbnail,
            "published": entry.get("published", ""),
            "content": content_text,
            "content_type": "video_transcript" if transcript else "description",
        })
        count += 1

    logger.info(f"[YouTube] {name} 获取 {len(results)} 条")
    return results
