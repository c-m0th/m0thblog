"""
Publish the daily digest into the Astro/Decap CMS papers collection.

Decap CMS stores entries as files in the repository, so creating an MDX file in
src/content/papers is equivalent to adding an entry through the admin UI.
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from src.utils.logger import get_logger

logger = get_logger("blog")

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_BLOG_ROOT = ROOT.parent
DEFAULT_PAPERS_DIR = DEFAULT_BLOG_ROOT / "src" / "content" / "papers"
DEFAULT_ADMIN_URL = "http://127.0.0.1:4321/admin/#/collections/papers/new"
DEFAULT_DAILY_TAG = "每日摘要"


def _as_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in re.split(r"[,;\n]+", str(value)) if part.strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _resolve_path(raw_path: str | None, *, base: Path = ROOT) -> Path:
    if not raw_path:
        return DEFAULT_PAPERS_DIR
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _setting(settings: dict | None, key: str, env_key: str, default: Any = None) -> Any:
    if os.environ.get(env_key) is not None:
        return os.environ[env_key]
    if settings and key in settings:
        return settings[key]
    return default


def _resolve_papers_dir(settings: dict | None = None) -> Path:
    papers_dir = _setting(settings, "blog_papers_dir", "BLOG_PAPERS_DIR")
    if papers_dir:
        return _resolve_path(str(papers_dir))

    blog_root = _setting(settings, "blog_root", "BLOG_ROOT")
    if blog_root:
        root = _resolve_path(str(blog_root))
        return root / "src" / "content" / "papers"

    return DEFAULT_PAPERS_DIR


def _escape_mdx(text: Any) -> str:
    value = "" if text is None else str(text)
    return (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .strip()
    )


def _platform_counts(items: list[dict]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for item in items:
        counts[item.get("platform", "Unknown")] += 1
    return "，".join(f"{name} {count} 篇" for name, count in counts.items())


def _render_body(items: list[dict], generated_at: datetime) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        grouped[item.get("platform", "Unknown")].append(item)

    lines: list[str] = [
        f"> 本条目由 AI Daily Digest 在 {generated_at.strftime('%Y-%m-%d %H:%M')} 自动生成。",
        "",
        "## 概览",
        "",
        f"- 本次共处理 {len(items)} 条内容。",
        f"- 平台分布：{_platform_counts(items)}。",
        "",
    ]

    for platform, platform_items in grouped.items():
        lines.extend([f"## {_escape_mdx(platform)}", ""])
        for index, item in enumerate(platform_items, 1):
            title = _escape_mdx(item.get("title", "Untitled"))
            source = _escape_mdx(item.get("source_name", ""))
            published = _escape_mdx(str(item.get("published", ""))[:10])
            url = str(item.get("url", "")).strip()
            authors = _escape_mdx(item.get("authors", ""))
            summary = _escape_mdx(item.get("summary") or item.get("content", ""))

            lines.extend([f"### {index}. {title}", ""])
            if source:
                lines.append(f"- 来源：{source}")
            if authors:
                lines.append(f"- 作者：{authors}")
            if published:
                lines.append(f"- 发布：{published}")
            if url:
                lines.append(f"- 原文：[打开链接](<{url}>)")
            if item.get("audio_url"):
                lines.append(f"- 音频：[收听](<{item['audio_url']}>)")
            lines.extend(["", summary or "暂无摘要。", ""])

    return "\n".join(lines).rstrip() + "\n"


def publish_daily_digest(
    items: list[dict],
    settings: dict | None = None,
    *,
    generated_at: datetime | None = None,
    dry_run: bool = False,
) -> Path | None:
    """Write one public papers entry for the current digest run."""
    if not items:
        logger.info("[Blog] 没有内容，跳过博客发布")
        return None

    enabled = _as_bool(_setting(settings, "blog_publish_enabled", "BLOG_PUBLISH_ENABLED", True))
    if not enabled:
        logger.info("[Blog] 博客发布已关闭，跳过")
        return None

    generated_at = generated_at or datetime.now()
    day = generated_at.strftime("%Y-%m-%d")
    papers_dir = _resolve_papers_dir(settings)
    admin_url = _setting(settings, "blog_admin_url", "BLOG_ADMIN_URL", DEFAULT_ADMIN_URL)

    if dry_run:
        logger.info(f"[Blog] [Dry Run] 将写入: {papers_dir / f'daily-digest-{day}.mdx'}")
        return None

    papers_dir.mkdir(parents=True, exist_ok=True)

    daily_tag = str(_setting(settings, "blog_daily_digest_tag", "BLOG_DAILY_DIGEST_TAG", DEFAULT_DAILY_TAG))
    extra_tags = _as_list(_setting(settings, "blog_extra_tags", "BLOG_EXTRA_TAGS", []))
    cover = str(_setting(settings, "blog_cover", "BLOG_COVER", "") or "").strip()

    frontmatter = {
        "title": f"每日文献摘要：{day}",
        "description": f"AI Daily Digest 自动汇总 {len(items)} 条文献与技术内容。",
        "date": day,
        "tags": _unique([daily_tag, *extra_tags]),
        "authors": ["AI Daily Digest"],
        "venue": "AI Daily Digest",
        "year": generated_at.year,
        "readingStatus": "read",
        "draft": False,
    }
    if cover:
        frontmatter["cover"] = cover

    body = _render_body(items, generated_at)
    content = (
        "---\n"
        + yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
        + "\n---\n\n"
        + body
    )

    output_path = papers_dir / f"daily-digest-{day}.mdx"
    output_path.write_text(content, encoding="utf-8")
    logger.info(f"[Blog] 已发布论文阅读条目: {output_path}")
    logger.info(f"[Blog] 后台入口: {admin_url}")
    return output_path
