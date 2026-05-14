#!/usr/bin/env python3
"""
main.py — AI Daily Digest 入口

用法:
  python main.py --run-now          # 立即运行一次
  python main.py --schedule         # 按配置时间每天定时运行
  python main.py --dry-run          # 只抓取不发邮件（调试用）
  python main.py --preview          # 生成 preview.html 本地预览
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import schedule
from pathlib import Path

import yaml
from dotenv import load_dotenv

# 把项目根目录加入 sys.path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.fetchers.youtube import fetch_channel
from src.fetchers.rss import fetch_blog, fetch_podcast, fetch_arxiv
from src.fetchers.hackernews import fetch_hn
from src.processors.summarizer import batch_summarize
from src.processors.blog_publisher import publish_daily_digest
from src.processors.email_sender import send_email, render_email
from src.utils.database import init_db, mark_processed, record_run
from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("main")

CONFIG_PATH = ROOT / "config" / "sources.yaml"
PROVIDER_ENV_KEYS = (
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GROQ_API_KEY",
)


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        example = ROOT / "config" / "sources.example.yaml"
        if example.exists():
            import shutil
            shutil.copy(example, CONFIG_PATH)
            logger.info(f"已从示例文件创建配置: {CONFIG_PATH}")
        else:
            raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_all(config: dict) -> list[dict]:
    """从所有来源抓取内容"""
    settings = config.get("settings", {})
    days = settings.get("days_lookback", 1)
    max_items = settings.get("max_items_per_source", 5)
    all_items = []

    # ── YouTube ──────────────────────────────
    for ch in config.get("youtube", []):
        try:
            items = fetch_channel(ch, days_lookback=days, max_items=max_items)
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[YouTube] {ch.get('name')} 抓取异常: {e}")

    # ── 博客 / Substack / Medium ─────────────
    for src in config.get("rss_blogs", []):
        try:
            items = fetch_blog(src, days_lookback=days, max_items=max_items)
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[Blog] {src.get('name')} 抓取异常: {e}")

    # ── 播客 ─────────────────────────────────
    for src in config.get("podcasts", []):
        try:
            items = fetch_podcast(src, days_lookback=days, max_items=1)
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[Podcast] {src.get('name')} 抓取异常: {e}")

    # ── ArXiv ─────────────────────────────────
    for src in config.get("arxiv", []):
        try:
            items = fetch_arxiv(src, days_lookback=days)
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[ArXiv] {src.get('name')} 抓取异常: {e}")

    # ── Hacker News ───────────────────────────
    hn_config = config.get("hackernews", {})
    if hn_config.get("enabled", False):
        try:
            items = fetch_hn(hn_config, days_lookback=days)
            all_items.extend(items)
        except Exception as e:
            logger.error(f"[HN] 抓取异常: {e}")

    logger.info(f"[Main] 共抓取到 {len(all_items)} 条新内容")
    return all_items


def run(dry_run: bool = False, preview: bool = False, publish_blog: bool = True):
    """主流程"""
    logger.info("=" * 50)
    logger.info("🚀 AI Daily Digest 开始运行")
    logger.info("=" * 50)

    # 检查 API Key
    if not any(os.environ.get(key) for key in PROVIDER_ENV_KEYS):
        logger.error("❌ 未设置任何 AI provider API key，请至少配置一个：%s", ", ".join(PROVIDER_ENV_KEYS))
        sys.exit(1)

    init_db()
    config = load_config()
    settings = config.get("settings", {})

    # 1. 抓取
    items = fetch_all(config)
    if not items:
        logger.info("📭 今日没有新内容，任务结束")
        return

    # 2. AI 总结
    logger.info(f"🤖 开始 AI 总结 {len(items)} 条内容...")
    items = batch_summarize(items, settings)

    # 3. 发邮件 / 预览
    if preview:
        html = render_email(items)
        preview_path = ROOT / "preview.html"
        with open(preview_path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.info(f"🖥  预览文件已生成: {preview_path}")

    email_sent = False
    if not dry_run and not preview:
        email_sent = send_email(items)
    elif dry_run:
        logger.info("🔍 [Dry Run] 跳过发送邮件")

    blog_path = None
    if publish_blog and not preview:
        blog_path = publish_daily_digest(items, settings, dry_run=dry_run)
    elif not publish_blog:
        logger.info("[Blog] 已通过 --no-blog 跳过博客发布")

    # 4. 标记已处理
    for item in items:
        mark_processed(
            url=item["url"],
            title=item["title"],
            source_name=item["source_name"],
            platform=item["platform"],
        )

    # 5. 记录运行
    record_run(len(items), email_sent)

    logger.info(f"✅ 任务完成！处理 {len(items)} 条，邮件{'已发送' if email_sent else '未发送'}")
    if blog_path:
        logger.info(f"[Blog] 本次摘要条目: {blog_path}")


def main():
    parser = argparse.ArgumentParser(description="AI Daily Digest — 每日学术摘要助理")
    parser.add_argument("--run-now", action="store_true", help="立即运行一次")
    parser.add_argument("--schedule", action="store_true", help="每天定时运行")
    parser.add_argument("--dry-run", action="store_true", help="运行但不发邮件")
    parser.add_argument("--preview", action="store_true", help="生成本地预览 HTML")
    parser.add_argument("--no-blog", action="store_true", help="不写入博客论文阅读条目")
    parser.add_argument("--time", default="08:00", help="定时运行时间，格式 HH:MM（默认 08:00）")
    args = parser.parse_args()

    if args.run_now or args.dry_run or args.preview:
        run(dry_run=args.dry_run, preview=args.preview, publish_blog=not args.no_blog)

    elif args.schedule:
        logger.info(f"⏰ 定时模式启动，每天 {args.time} 运行")
        schedule.every().day.at(args.time).do(run, publish_blog=not args.no_blog)
        # 启动时也先跑一次
        run(publish_blog=not args.no_blog)
        while True:
            schedule.run_pending()
            time.sleep(30)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
