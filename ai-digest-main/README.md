# AI Daily Digest

一个每日文献与技术内容摘要脚本：抓取 YouTube、RSS 博客、ArXiv、播客和 Hacker News，调用大模型生成中文摘要，然后发送邮件，并把本次摘要写入博客的“论文阅读”板块。

## 支持平台

| 平台 | 内容类型 | 抓取方式 |
| --- | --- | --- |
| YouTube | 视频字幕 | youtube-transcript-api |
| Substack / Medium / Blog | 文章 | RSS + 正文抽取 |
| ArXiv | 论文摘要 | ArXiv API |
| 播客 | 节目说明/可选转录 | RSS + Whisper |
| Hacker News | 热门讨论 | Firebase API |

## 快速开始

```bash
pip install -r requirements.txt
cp config/sources.example.yaml config/sources.yaml
```

然后编辑 `config/sources.yaml`，添加你关心的来源。

## 环境变量

至少配置一个 AI provider key：

```bash
export DEEPSEEK_API_KEY="your_key"
# 或 GEMINI_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY / GROQ_API_KEY
```

邮件发送：

```bash
export EMAIL_ADDRESS="your@gmail.com"
export EMAIL_PASSWORD="your_app_password"
export EMAIL_TO="you@gmail.com,colleague@qq.com,lab@163.com"
```

`EMAIL_TO` 和 `EMAIL_RECIPIENTS` 都支持多个收件人，可用英文逗号、分号或换行分隔。若希望每个收件人收到独立邮件，设置：

```bash
export EMAIL_SEND_INDIVIDUALLY=true
```

博客发布默认会写入上级 Astro 项目的 `src/content/papers`。本仓库放在当前博客根目录下时无需额外配置。可选配置：

```bash
export BLOG_PUBLISH_ENABLED=true
export BLOG_ROOT=".."
export BLOG_PAPERS_DIR="../src/content/papers"
export BLOG_DAILY_DIGEST_TAG="每日摘要"
export BLOG_COVER="/assets/knowledge-hero.png"
```

生成的条目会是公开状态：`draft: false`，并自动带上 `每日摘要` 标签。手动新建入口仍是 `http://127.0.0.1:4321/admin/#/collections/papers/new`；脚本会直接写入 CMS 背后的内容文件，因此生成后可在论文阅读列表里查看和继续编辑。

## 运行

```bash
# 立即运行一次：发邮件并写入博客条目
python main.py --run-now

# 只演练，不发邮件、不写博客
python main.py --dry-run

# 只生成邮件 HTML 预览
python main.py --preview

# 每天 08:00 定时运行
python main.py --schedule

# 临时跳过博客发布
python main.py --run-now --no-blog
```

## 生成的博客条目

每次正常运行会生成或覆盖当天的文件：

```txt
../src/content/papers/daily-digest-YYYY-MM-DD.mdx
```

条目 frontmatter 示例：

```yaml
title: "每日文献摘要：2026-05-14"
description: "AI Daily Digest 自动汇总 8 条文献与技术内容。"
date: "2026-05-14"
tags:
  - "每日摘要"
authors:
  - "AI Daily Digest"
venue: "AI Daily Digest"
year: 2026
readingStatus: "read"
draft: false
```

## 项目结构

```txt
ai-digest-main/
  main.py
  config/
    sources.yaml
  src/
    fetchers/
    processors/
      blog_publisher.py
      email_sender.py
      summarizer.py
    utils/
  templates/
    email.html
```
