"""
Render and send the daily digest email.
"""
from __future__ import annotations

import os
import re
import smtplib
from collections import defaultdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from src.utils.logger import get_logger

logger = get_logger("email")

TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates"

PLATFORM_ICONS = {
    "YouTube": "🎬",
    "Blog/Newsletter": "📝",
    "ArXiv": "📄",
    "Podcast": "🎧",
    "Hacker News": "🔥",
    "Hacker News AI": "🔥",
}

PLATFORM_BADGE_CLASS = {
    "YouTube": "youtube",
    "Blog/Newsletter": "blog",
    "ArXiv": "arxiv",
    "Podcast": "podcast",
    "Hacker News": "hn",
}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_recipients(raw: str) -> list[str]:
    """Parse comma, semicolon, or newline separated email addresses."""
    recipients: list[str] = []
    seen: set[str] = set()
    for addr in re.split(r"[,;\n]+", raw or ""):
        cleaned = addr.strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            recipients.append(cleaned)
            seen.add(key)
    return recipients


def _get_recipients(email_from: str) -> list[str]:
    raw = "\n".join(
        value
        for value in [
            os.environ.get("EMAIL_TO", ""),
            os.environ.get("EMAIL_RECIPIENTS", ""),
        ]
        if value
    )
    return parse_recipients(raw) or [email_from]


def _group_by_platform(items: list[dict]) -> dict[str, list[dict]]:
    grouped = defaultdict(list)
    for item in items:
        grouped[item["platform"]].append(item)
    return dict(grouped)


def render_email(items: list[dict]) -> str:
    """Render the digest HTML email."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("email.html")

    return template.render(
        date=datetime.now().strftime("%Y年%m月%d日"),
        total_items=len(items),
        grouped_items=_group_by_platform(items),
        platform_icons=PLATFORM_ICONS,
        platform_badge=PLATFORM_BADGE_CLASS,
    )


def _build_message(email_from: str, recipients: list[str], html_body: str, today: str, count: int) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"每日学术摘要 | {today} | {count} 篇精选"
    msg["From"] = f"AI Digest <{email_from}>"
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def send_email(items: list[dict]) -> bool:
    """
    Send the digest email.

    Multiple recipients are supported through EMAIL_TO and/or EMAIL_RECIPIENTS:
      EMAIL_TO=a@gmail.com,b@qq.com
      EMAIL_RECIPIENTS=lab@163.com;friend@outlook.com

    Set EMAIL_SEND_INDIVIDUALLY=true to send one message per recipient.
    """
    if not items:
        logger.info("[Email] 没有新内容，跳过发送")
        return False

    email_from = os.environ.get("EMAIL_ADDRESS", "").strip()
    email_password = os.environ.get("EMAIL_PASSWORD", "").strip()
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    recipients = _get_recipients(email_from)
    send_individually = _as_bool(os.environ.get("EMAIL_SEND_INDIVIDUALLY"), default=False)

    if not email_from or not email_password:
        logger.error("[Email] 未设置 EMAIL_ADDRESS 或 EMAIL_PASSWORD 环境变量")
        return False

    html_body = render_email(items)
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        if smtp_port == 465:
            server_context = smtplib.SMTP_SSL(smtp_host, smtp_port)
        else:
            server_context = smtplib.SMTP(smtp_host, smtp_port)

        with server_context as server:
            if smtp_port != 465:
                server.starttls()
            server.login(email_from, email_password)

            if send_individually:
                failed: list[str] = []
                for recipient in recipients:
                    msg = _build_message(email_from, [recipient], html_body, today, len(items))
                    try:
                        server.sendmail(email_from, [recipient], msg.as_string())
                    except Exception as exc:
                        failed.append(recipient)
                        logger.error(f"[Email] 发送给 {recipient} 失败: {exc}")
                if failed:
                    logger.error(f"[Email] {len(failed)} 位收件人发送失败: {failed}")
                    return False
            else:
                msg = _build_message(email_from, recipients, html_body, today, len(items))
                server.sendmail(email_from, recipients, msg.as_string())

        logger.info(f"[Email] 成功发送至 {len(recipients)} 位收件人: {recipients}")
        return True
    except Exception as e:
        logger.error(f"[Email] 发送失败: {e}")
        return False
