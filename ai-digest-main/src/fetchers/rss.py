"""
fetchers/rss.py — 通用 RSS 抓取器
覆盖：Substack、Medium、博客、播客、ArXiv
"""
from __future__ import annotations

import re
import time
import requests
import feedparser
import trafilatura
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

from src.utils.logger import get_logger
from src.utils.database import is_processed

logger = get_logger("rss")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AcademicDigestBot/1.0)"
}


def _clean_html(html_text: str) -> str:
    """简单去除 HTML 标签"""
    clean = re.sub(r"<[^>]+>", " ", html_text or "")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def _fetch_full_article(url: str) -> str | None:
    """用 trafilatura 提取网页正文"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            text = trafilatura.extract(
                resp.text,
                include_comments=False,
                include_tables=True,
                no_fallback=False,
            )
            return text
    except Exception as e:
        logger.warning(f"[RSS] 全文提取失败 {url}: {e}")
    return None


def _parse_entry_time(entry) -> datetime | None:
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if published:
        return datetime(*published[:6], tzinfo=timezone.utc)
    return None


# ─────────────────────────────────────────────
# 博客 / Substack / Medium
# ─────────────────────────────────────────────

def fetch_blog(source_config: dict, days_lookback: int, max_items: int) -> list[dict]:
    name = source_config["name"]
    url = source_config["url"]
    results = []

    feed = feedparser.parse(url)
    if not feed.entries:
        logger.warning(f"[Blog] {name} RSS 为空或无法访问")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback + 1)
    count = 0

    for entry in feed.entries:
        if count >= max_items:
            break

        link = entry.get("link", "")
        if not link:
            continue

        pub_dt = _parse_entry_time(entry)
        if pub_dt and pub_dt < cutoff:
            continue

        if is_processed(link):
            logger.info(f"[Blog] 已处理，跳过: {entry.get('title', '')}")
            continue

        logger.info(f"[Blog] 抓取: {entry.get('title', '')} ({name})")

        # 优先 RSS 全文，次选 trafilatura 抓全文，再选摘要
        content = ""
        rss_content = entry.get("content", [{}])[0].get("value", "") \
                      or entry.get("summary", "")
        rss_text = _clean_html(rss_content)

        if len(rss_text) > 500:
            content = rss_text
        else:
            full = _fetch_full_article(link)
            content = full or rss_text

        if not content.strip():
            continue

        results.append({
            "platform": "Blog/Newsletter",
            "source_name": name,
            "title": entry.get("title", "无标题"),
            "url": link,
            "thumbnail": "",
            "published": entry.get("published", ""),
            "content": content,
            "content_type": "article",
        })
        count += 1
        time.sleep(0.5)  # 礼貌爬取

    logger.info(f"[Blog] {name} 获取 {len(results)} 条")
    return results


# ─────────────────────────────────────────────
# 播客（RSS → 文字描述）
# ─────────────────────────────────────────────

def fetch_podcast(source_config: dict, days_lookback: int, max_items: int) -> list[dict]:
    name = source_config["name"]
    url = source_config["url"]
    transcribe = source_config.get("transcribe", False)
    results = []

    feed = feedparser.parse(url)
    if not feed.entries:
        logger.warning(f"[Podcast] {name} RSS 为空")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback + 1)
    count = 0

    for entry in feed.entries[:max_items * 2]:
        if count >= max_items:
            break

        link = entry.get("link", entry.get("id", ""))
        if not link:
            continue

        pub_dt = _parse_entry_time(entry)
        if pub_dt and pub_dt < cutoff:
            continue

        if is_processed(link):
            continue

        logger.info(f"[Podcast] 处理: {entry.get('title', '')} ({name})")

        # 提取节目说明
        summary = _clean_html(
            entry.get("content", [{}])[0].get("value", "")
            or entry.get("summary", "")
            or entry.get("itunes_summary", "")
        )

        audio_url = ""
        for enc in entry.get("enclosures", []):
            if "audio" in enc.get("type", ""):
                audio_url = enc.get("href", "")
                break

        # 如果开启 Whisper 且有音频 URL
        transcript = None
        if transcribe and audio_url:
            transcript = _whisper_transcribe(audio_url)

        content = transcript or summary
        if not content.strip():
            continue

        # 提取封面
        thumbnail = ""
        img = entry.get("image", {})
        if img:
            thumbnail = img.get("href", "")

        results.append({
            "platform": "Podcast",
            "source_name": name,
            "title": entry.get("title", "无标题"),
            "url": link,
            "thumbnail": thumbnail,
            "published": entry.get("published", ""),
            "content": content,
            "content_type": "podcast_transcript" if transcript else "podcast_summary",
            "audio_url": audio_url,
        })
        count += 1

    logger.info(f"[Podcast] {name} 获取 {len(results)} 条")
    return results


def _whisper_transcribe(audio_url: str) -> str | None:
    """下载音频并用 Whisper 转录（需 GPU/较长时间）"""
    try:
        import whisper
        import tempfile
        import os

        logger.info(f"[Whisper] 下载音频: {audio_url[:60]}...")
        resp = requests.get(audio_url, timeout=60, stream=True)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
            tmp_path = f.name

        logger.info("[Whisper] 开始转录...")
        model = whisper.load_model("base")
        result = model.transcribe(tmp_path, language="en")
        os.unlink(tmp_path)
        return result["text"]
    except Exception as e:
        logger.warning(f"[Whisper] 转录失败: {e}")
        return None


# ─────────────────────────────────────────────
# ArXiv 论文
# ─────────────────────────────────────────────

ARXIV_API = "http://export.arxiv.org/api/query"


def fetch_arxiv(source_config: dict, days_lookback: int) -> list[dict]:
    name = source_config["name"]
    query = source_config["query"]
    max_results = source_config.get("max_results", 5)
    results = []

    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results * 2,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    try:
        resp = requests.get(ARXIV_API, params=params, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[ArXiv] {name} 请求失败: {e}")
        return []

    feed = feedparser.parse(resp.text)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback + 1)
    count = 0

    for entry in feed.entries:
        if count >= max_results:
            break

        link = entry.get("link", "")
        pub_dt = _parse_entry_time(entry)
        if pub_dt and pub_dt < cutoff:
            continue

        if is_processed(link):
            continue

        # ArXiv 摘要直接可用
        abstract = _clean_html(entry.get("summary", ""))
        authors = ", ".join(
            a.get("name", "") for a in entry.get("authors", [])[:3]
        )
        if len(entry.get("authors", [])) > 3:
            authors += " et al."

        content = f"Authors: {authors}\n\nAbstract: {abstract}"

        results.append({
            "platform": "ArXiv",
            "source_name": name,
            "title": entry.get("title", "").replace("\n", " ").strip(),
            "url": link,
            "thumbnail": "",
            "published": entry.get("published", ""),
            "content": content,
            "content_type": "paper_abstract",
            "authors": authors,
        })
        count += 1

    logger.info(f"[ArXiv] {name} 获取 {len(results)} 条")
    return results
