"""
fetchers/hackernews.py — 抓取 HN 中与 AI/ML 相关的高分帖子

使用官方 Firebase API，完全免费无需账号
"""
from __future__ import annotations

import time
import requests
from datetime import datetime, timezone, timedelta

from src.utils.logger import get_logger
from src.utils.database import is_processed

logger = get_logger("hackernews")

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_NEW_STORIES = "https://hacker-news.firebaseio.com/v0/newstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_URL = "https://news.ycombinator.com/item?id={}"


def fetch_hn(config: dict, days_lookback: int) -> list[dict]:
    """抓取 HN 中符合关键词的高分帖子"""
    keywords = [k.lower() for k in config.get("keywords", [])]
    min_score = config.get("min_score", 100)
    max_items = config.get("max_items", 5)
    results = []

    try:
        story_ids = requests.get(HN_TOP_STORIES, timeout=10).json()
    except Exception as e:
        logger.warning(f"[HN] 获取故事列表失败: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days_lookback + 1)
    checked = 0

    for story_id in story_ids[:200]:  # 只检查前 200 条热帖
        if len(results) >= max_items:
            break
        if checked > 0 and checked % 20 == 0:
            time.sleep(0.5)

        try:
            item = requests.get(HN_ITEM.format(story_id), timeout=8).json()
        except Exception:
            continue

        checked += 1
        if not item or item.get("type") != "story":
            continue

        score = item.get("score", 0)
        if score < min_score:
            continue

        # 时间过滤
        ts = item.get("time", 0)
        pub_dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if pub_dt < cutoff:
            continue

        title = item.get("title", "")
        title_lower = title.lower()

        # 关键词过滤
        if keywords and not any(kw in title_lower for kw in keywords):
            continue

        url = item.get("url", HN_URL.format(story_id))
        hn_url = HN_URL.format(story_id)

        if is_processed(hn_url):
            continue

        # 评论文字作为内容
        text = item.get("text", "") or f"Score: {score} | Comments: {item.get('descendants', 0)}"
        content = f"Score: {score} | Comments: {item.get('descendants', 0)}\nURL: {url}\n\n{text}"

        results.append({
            "platform": "Hacker News",
            "source_name": "Hacker News AI",
            "title": title,
            "url": hn_url,
            "original_url": url,
            "thumbnail": "",
            "published": pub_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "content": content,
            "content_type": "hn_post",
            "score": score,
        })

    logger.info(f"[HN] 获取 {len(results)} 条")
    return results
