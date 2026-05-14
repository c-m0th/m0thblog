"""
processors/summarizer.py — 多 API Provider 支持，自动轮换降级
支持：Claude / OpenAI GPT / Google Gemini / Groq / DeepSeek
"""
import os
import time
import socket
import anthropic
import requests
from src.utils.logger import get_logger

logger = get_logger("summarizer")

# ─────────────────────────────────────────────────────────
# Provider 配置
# 在 .env 或 GitHub Secrets 中设置对应的 key
# 没有设置的 key 会自动跳过
# ─────────────────────────────────────────────────────────
PROVIDERS = [
    {
        "name": "DeepSeek",                        # 优先用：性价比高（¥1/百万token）
        "env_key": "DEEPSEEK_API_KEY",
        "type": "openai_compat",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
    },
    {
        "name": "Gemini",                          # 备用用：每天1500次免费
        "env_key": "GEMINI_API_KEY",
        "type": "gemini",
        "model": "gemini-2.0-flash",
    },
    {
        "name": "Claude",                          # 备用
        "env_key": "ANTHROPIC_API_KEY",
        "type": "claude",
        "model": "claude-sonnet-4-20250514",
    },
    {
        "name": "GPT-4o-mini",                     # 备用
        "env_key": "OPENAI_API_KEY",
        "type": "openai_compat",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
    },
    {
        "name": "Groq",                            # 备用：免费但有速率限制
        "env_key": "GROQ_API_KEY",
        "type": "openai_compat",
        "model": "llama-3.3-70b-versatile",
        "base_url": "https://api.groq.com/openai/v1",
    },
]


def _get_available_providers():
    """只返回已配置了 API Key 的 provider"""
    available = []
    for p in PROVIDERS:
        if os.environ.get(p["env_key"]):
            available.append(p)
    if not available:
        raise RuntimeError("未找到任何 API Key！请在 .env 中设置至少一个。")
    logger.info(f"[Summarizer] 可用 providers: {[p['name'] for p in available]}")
    return available


def _call_gemini(api_key, model, prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    resp = requests.post(
        url,
        params={"key": api_key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=(10, 60),   # (连接超时, 读取超时) 秒
        verify=True,        # SSL 验证
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def _call_openai_compat(api_key, base_url, model, prompt):
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1000,
        },
        timeout=(10, 60),
        verify=True,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_claude(api_key: str, model: str, prompt: str) -> str:
    api_key = api_key.strip()
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model, max_tokens=1000,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()


def _call_provider(provider: dict, prompt: str) -> str:
    api_key = os.environ[provider["env_key"]]
    ptype = provider["type"]

    if ptype == "gemini":
        return _call_gemini(api_key, provider["model"], prompt)
    elif ptype == "openai_compat":
        return _call_openai_compat(
            api_key, provider["base_url"], provider["model"], prompt
        )
    elif ptype == "claude":
        return _call_claude(api_key, provider["model"], prompt)


# ── Prompt 模板（与原版相同，此处省略，直接复用原文件中的 PROMPTS 字典）──
PROMPTS = {
    "video_transcript": """你是深度学习/AI领域的学术内容助理，请总结以下YouTube视频字幕（中文输出）：
标题：{title} | 频道：{source_name}
内容：{content}

**🎯 核心论点**（3条）
**🔧 技术方法**（2条）
**💡 关键洞察**（2条）
**📌 一句话总结**""",

    "article": """你是深度学习/AI领域的学术内容助理，请总结以下文章（中文输出）：
标题：{title} | 来源：{source_name}
内容：{content}

**🎯 核心观点**（3条）
**📊 主要论据**（2条）
**💡 对从业者的启示**（1条）
**📌 一句话总结**""",

    "paper_abstract": """你是AI研究助理，请解读以下论文摘要（中文输出）：
标题：{title}
内容：{content}

**🔬 研究问题**
**🛠 方法创新**（2条）
**📈 主要结果**
**🌟 意义与影响**""",

    "podcast_summary": """请总结以下播客节目（中文输出）：
标题：{title} | 播客：{source_name}
说明：{content}

**🎙 话题与嘉宾**
**🔑 核心议题**（3条）
**💡 值得收听的理由**""",

    "hn_post": """请简要说明以下HN帖子的内容和价值（中文，2-3句话）：
标题：{title}
内容：{content}""",

    "description": """根据以下YouTube视频描述推断内容，写2-3句中文摘要：
标题：{title} | 频道：{source_name}
描述：{content}""",
}


def summarize(item: dict, max_content_chars: int = 12000, language_hint: str = "") -> str:
    content_type = item.get("content_type", "article")
    prompt_template = PROMPTS.get(content_type, PROMPTS["article"])
    content = item.get("content", "")[:max_content_chars]
    prompt = prompt_template.format(
        title=item.get("title", ""),
        source_name=item.get("source_name", ""),
        content=content,
    )

    providers = _get_available_providers()
    last_error = None

    for provider in providers:
        try:
            logger.info(f"[Summarizer] 使用 {provider['name']} ...")
            result = _call_provider(provider, prompt)
            return result

        # ① 限流 → 等待后换下一个
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            logger.warning(f"[{provider['name']}] HTTP {status}: {e}")
            if status == 429:
                logger.warning("触发限流，等 10s 后切换")
                time.sleep(10)
            last_error = e

        # ② 网络不通（DNS/TCP/SSL）→ 直接换下一个
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                socket.gaierror) as e:
            logger.warning(f"[{provider['name']}] 网络连接失败: {type(e).__name__}: {e}")
            last_error = e

        # ③ anthropic SDK 自己的连接错误
        except Exception as e:
            err_type = type(e).__name__
            logger.warning(f"[{provider['name']}] 调用异常 [{err_type}]: {e}")
            last_error = e

    return f"（所有 provider 均失败，最后错误：{last_error}）"


def batch_summarize(items: list[dict], settings: dict) -> list[dict]:
    max_chars = settings.get("max_content_chars", 12000)
    lang = settings.get("language_hint", "")
    for i, item in enumerate(items, 1):
        logger.info(f"[Summarizer] {i}/{len(items)}: {item['title'][:50]}")
        item["summary"] = summarize(item, max_chars, lang)
    return items
