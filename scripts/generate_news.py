#!/usr/bin/env python3
"""
每日新闻简报自动生成脚本
========================================
工作流程：
  1. 从 Perigon News API 获取三个栏目的最新新闻
  2. 用 DeepSeek LLM 对头条进行深度分析（大众化风格）
  3. 对其他新闻生成简要快讯
  4. 渲染多页 HTML 网站（首页 + 三个栏目页）

使用方法：
  export PERIGON_API_KEY="your_key"
  export DEEPSEEK_API_KEY="your_key"
  python scripts/generate_news.py

定时运行（GitHub Actions）：
  每天 UTC 01:00 = 北京时间 09:00
"""

import os
import re
import json
import sys
import requests
from datetime import datetime, timezone, timedelta

# ── DeepSeek API 配置 ───────────────────────────────────────
DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"  # 你已订阅的 DeepSeek 模型


# ═══════════════════════ 配 置 ═══════════════════════════

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")
API_BASE = "https://api.perigon.io/v2"

COLUMNS = {
    "tech": {
        "label": "科技",
        "icon": "💻",
        "tag_class": "tag-tech",
        "color_tag": "💻 科技",
        "query": "technology AI tech innovation",
        "category": ["Tech"],
        "sort": "date",
        "size": 10,
    },
    "politics": {
        "label": "国际政治",
        "icon": "🌍",
        "tag_class": "tag-politics",
        "color_tag": "🌍 国际政治",
        "query": "international politics world affairs diplomacy",
        "category": ["Politics", "World"],
        "sort": "date",
        "size": 10,
    },
    "finance": {
        "label": "金融",
        "icon": "📈",
        "tag_class": "tag-finance",
        "color_tag": "📈 金融",
        "query": "stock market economy finance",
        "category": ["Finance", "Business"],
        "sort": "date",
        "size": 10,
    },
}

DEEPSEEK_MODEL = "deepseek-chat"  # 你已订阅的 DeepSeek 模型

# ── DeepSeek system prompts ─────────────────────────────

DEEP_ANALYSIS_SYSTEM = """你是一位面向普通大众读者的新闻分析撰稿人。你的任务是把专业新闻改写成普通人也能轻松看懂的分析文章。

## 写作规则（务必遵守）

1. **大众化语言**：避免任何专业术语。如果必须使用（如"通胀"），立刻用通俗说法解释（"物价上涨"）。
   例如："量化宽松" → "央行印钱买债券"
   例如："地缘政治博弈" → "国与国之间的明争暗斗"
   例如："加息" → "提高借钱成本"

2. **文章结构**必须严格按以下三个部分，每部分都要有 emoji 标题：
   📌 **发生了什么** — 事实叙述：发生了什么事？谁说了什么？时间地点人物？
   🔍 **这意味着什么** — 分析：这件事为什么重要？背后的原因是什么？
   🔮 **接下来会怎样** — 预测：基于事实的合理推断，放在 prediction_box 中

3. **客观中立**：不偏袒任何一方，呈现多方观点。

4. **源头标注**：引用的新闻必须标注来源名称。

5. **标题**：吸引人但不过分夸张，10-20字为宜。

## 输出格式

返回纯 JSON，不要包含 Markdown 代码块标记：
{
  "title": "标题",
  "excerpt": "首页概览用的一句话摘要（不超过60字）",
  "section_what": "📌 发生了什么段落（2-4句话）",
  "section_analysis": "🔍 这意味着什么段落（3-6句话）",
  "section_prediction": "🔮 接下来会怎样段落（2-4句话）"
}"""

BRIEF_SYSTEM = """你是一位新闻摘要撰稿人。给定几条新闻，为每条写一段简短摘要。

## 规则

1. 每条摘要1-2句话，保留核心信息
2. 大众化语言，避免专业术语
3. 标注每条新闻的来源

## 输出格式

返回纯 JSON，不要包含 Markdown 代码块标记：
{
  "briefs": [
    {"title": "快讯标题（10字以内）", "summary": "摘要内容（1-2句话）", "source": "来源名称"}
  ]
}"""


# ═══════════════════════ 核 心 功 能 ═══════════════════════

def fetch_news(api_key, column_key):
    """从 Perigon API 获取某个栏目的新闻"""
    col = COLUMNS[column_key]
    params = {
        "query": col["query"],
        "category": col["category"] if col["category"] else None,
        "sortBy": col["sort"],
        "size": col.get("size", 10),
        "showReprints": "false",
        "summarize": "true",
        "countries": [],  # 不加国家限制，获取全球新闻
    }
    # 移除 None 值参数
    params = {k: v for k, v in params.items() if v is not None}

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{API_BASE}/articles", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def _format_article_text(article):
    """把一篇文章格式化为文字，供 LLM 阅读"""
    title = article.get("title", "") or ""
    summary = article.get("summary", "") or ""
    source = article.get("source", {})
    source_name = ""
    if isinstance(source, dict):
        source_name = source.get("name", "") or ""
    elif isinstance(source, str):
        source_name = source

    author = article.get("author", "") or ""
    date = article.get("datePublished", "") or ""
    url = article.get("url", "") or ""

    parts = [f"标题：{title}"]
    if summary:
        parts.append(f"摘要：{summary}")
    if source_name:
        parts.append(f"来源：{source_name}")
    if author and author != source_name:
        parts.append(f"作者：{author}")
    if date:
        parts.append(f"日期：{date}")
    parts.append(f"链接：{url}")
    return "\n".join(parts)


def call_deepseek(api_key, system_prompt, user_message, max_tokens=1500):
    """调用 DeepSeek API（兼容 OpenAI 格式）并解析返回的 JSON"""
    resp = requests.post(
        f"{DEEPSEEK_API_BASE}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["choices"][0]["message"]["content"].strip()

    # 清理可能的 Markdown 代码块标记
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return json.loads(text)


def generate_deep_analysis(api_key, article, column_key):
    """用 DeepSeek 对头条新闻生成深度分析"""
    col = COLUMNS[column_key]
    article_text = _format_article_text(article)

    user_message = (
        f"请为以下{col['label']}新闻写一篇面向普通大众的深度分析文章。\n\n"
        f"新闻内容：\n{article_text}\n\n"
        f"注意：这篇文章的读者是普通大众，请用最通俗的语言解释。"
    )

    try:
        result = call_deepseek(api_key, DEEP_ANALYSIS_SYSTEM, user_message)
        # 确保所有必要字段都存在
        result.setdefault("title", article.get("title", ""))
        result.setdefault("excerpt", "")
        result.setdefault("section_what", "")
        result.setdefault("section_analysis", "")
        result.setdefault("section_prediction", "")
        return result
    except Exception as e:
        print(f"    ⚠️  深度分析生成失败: {e}")
        # 降级：用原文标题和摘要
        return {
            "title": article.get("title", ""),
            "excerpt": (article.get("summary", "") or "")[:60],
            "section_what": article.get("summary", "") or "无法生成分析",
            "section_analysis": "",
            "section_prediction": "",
        }


def generate_briefs(api_key, articles, column_key):
    """用 DeepSeek 对非头条新闻生成快讯摘要"""
    if not articles:
        return []

    col = COLUMNS[column_key]
    articles_text = "\n---\n".join([_format_article_text(a) for a in articles])

    user_message = (
        f"以下是一些{col['label']}新闻，请为每条新闻写一个简短摘要（1-2句话）。\n\n"
        f"{articles_text}"
    )

    try:
        result = call_deepseek(api_key, BRIEF_SYSTEM, user_message, max_tokens=1000)
        return result.get("briefs", [])
    except Exception as e:
        print(f"    ⚠️  快讯生成失败: {e}")
        # 降级：用原文摘要
        briefs = []
        for a in articles:
            source = a.get("source", {})
            source_name = source.get("name", "") if isinstance(source, dict) else str(source)
            briefs.append({
                "title": (a.get("title", "") or "")[:30],
                "summary": (a.get("summary", "") or "")[:120],
                "source": source_name,
            })
        return briefs


def extract_source_name(article):
    """从文章对象中提取来源名称"""
    source = article.get("source", {})
    if isinstance(source, dict):
        return source.get("name", "") or ""
    return str(source) if source else ""


# ═══════════════════════ HTML 模 板 ═══════════════════════

def render_navbar(active_col=None):
    """渲染导航栏 HTML"""
    links = [
        ("index.html", "首页", active_col is None),
        ("tech.html", "💻 科技", active_col == "tech"),
        ("politics.html", "🌍 国际", active_col == "politics"),
        ("finance.html", "📈 金融", active_col == "finance"),
    ]
    items_list = []
    for href, label, active in links:
        cls = ' class="active"' if active else ""
        items_list.append(f'      <li><a href="{href}"{cls}>{label}</a></li>')
    items = "\n".join(items_list)
    return f'''<nav class="navbar">
  <div class="navbar-inner">
    <a href="index.html" class="logo"><span>📰</span> 每日简报</a>
    <ul class="nav-links">
{items}
    </ul>
  </div>
</nav>'''


def render_footer(date_str):
    return f'''<div class="footer">
  <p>每日新闻简报 · {date_str} · 数据来源：Perigon News</p>
</div>
<div class="ai-badge">🤖 内容由 AI 生成，仅供参考</div>'''


def render_deep_analysis(analysis, col, date_str):
    """渲染深度分析卡片"""
    source_html = ""
    if analysis.get("source_name"):
        source_html = f'\n      <p class="article-meta" style="margin-top:20px;">—— 来源: {analysis["source_name"]}</p>'

    return f'''<div class="deep-analysis">

    <span class="tag {col['tag_class']}" style="margin-bottom:12px;">{col['color_tag']}</span>
    <h2>{analysis['title']}</h2>

    <p class="article-meta">
      📅 {date_str} ·
      {f'<span class="source">{analysis["source_name"]}</span>' if analysis.get("source_name") else ''}
    </p>

    <div class="section-label">📌 发生了什么</div>
    <p>{analysis.get('section_what', '')}</p>

    <div class="section-label">🔍 这意味着什么</div>
    <p>{analysis.get('section_analysis', '')}</p>

    <div class="prediction-box">
      <div class="section-label" style="margin-top:0;">🔮 接下来会怎样</div>
      <p>{analysis.get('section_prediction', '')}</p>
    </div>
{source_html}

  </div>'''


def render_briefs(briefs):
    """渲染快讯列表"""
    if not briefs:
        return ""

    items = "\n".join(
        f'''    <div class="brief-item">
      <div class="brief-title">{b.get("title", "")}</div>
      <div class="brief-summary">{b.get("summary", "")}</div>
      <div class="brief-source">—— 来源: {b.get("source", "")}</div>
    </div>'''
        for b in briefs
    )

    return f'''<div class="brief-section">
    <h3>📋 今日更多快讯</h3>

{items}

  </div>'''


def render_column_page(col_key, col, analysis, briefs, date_str, date_str_en):
    """生成一个栏目页 HTML"""
    navbar = render_navbar(col_key)
    footer = render_footer(date_str)
    deep_html = render_deep_analysis(analysis, col, date_str)
    briefs_html = render_briefs(briefs)

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{col['label']} · 每日新闻简报 {date_str_en}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>

{navbar}

<div class="container">

  <div class="column-header">
    <a href="index.html" class="back-link">← 返回首页</a>
    <h1>{col['icon']} {col['label']} · 今日头条</h1>
    <p style="color:var(--text-secondary);font-size:14px;">{date_str}</p>
  </div>

{deep_html}

{briefs_html}

</div>

{footer}

</body>
</html>'''


def render_index_page(overviews, date_str):
    """生成首页 HTML"""
    navbar = render_navbar()

    cards = "\n".join(
        f'''    <a href="{ov['href']}" class="overview-card">
      <span class="tag {ov['tag_class']}">{ov['color_tag']}</span>
      <h3>{ov['title']}</h3>
      <p class="excerpt">{ov['excerpt']}</p>
      <span class="more-link">阅读全文 →</span>
    </a>'''
        for ov in overviews
    )

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>每日新闻简报 · {date_str}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>

{navbar}

<div class="container">

  <div class="date-header">
    <h1>📰 每日新闻简报</h1>
    <p>{date_str} · 三分钟读懂今日要闻</p>
  </div>

  <div class="overview-grid">

{cards}

  </div>

</div>

{render_footer(date_str)}

</body>
</html>'''


# ═══════════════════════ 主 流 程 ═══════════════════════

def main():
    # ── 检查环境变量 ──
    perigon_key = os.environ.get("PERIGON_API_KEY")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")

    if not perigon_key:
        print("❌ 请设置 PERIGON_API_KEY 环境变量")
        print("   获取: https://perigon.io/ (注册后获取 API key)")
        return 1

    if not deepseek_key:
        print("❌ 请设置 DEEPSEEK_API_KEY 环境变量")
        print("   获取: https://platform.deepseek.com/ (登录后创建 API key)")
        return 1

    # ── 北京时间 ──
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    date_str = now.strftime("%Y年%m月%d日")
    date_str_en = now.strftime("%Y-%m-%d")
    weekday_cn = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    weekday_str = weekday_cn[now.weekday()]

    print(f"📰 正在生成 {date_str} ({weekday_str}) 的新闻简报...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── 开始处理 ──
    api_key = deepseek_key  # DeepSeek API key，传给各函数
    overviews = []
    column_results = {}

    # ── 逐栏目处理 ──
    for key in COLUMNS:
        col = COLUMNS[key]
        print(f"\n{'='*40}")
        print(f"📌 {col['label']}")
        print(f"{'='*40}")

        # 1. 抓取新闻
        print(f"  正在获取新闻...")
        try:
            articles = fetch_news(perigon_key, key)
            print(f"  ✅ 获取到 {len(articles)} 条新闻")
        except Exception as e:
            print(f"  ❌ 获取失败: {e}")
            column_results[key] = None
            overviews.append({
                "href": f"{key}.html",
                "tag_class": col["tag_class"],
                "color_tag": col["color_tag"],
                "title": "新闻获取失败",
                "excerpt": f"抱歉，{col['label']}新闻暂时无法获取。",
            })
            continue

        if not articles:
            print(f"  ⚠️  没有获取到新闻")
            column_results[key] = None
            overviews.append({
                "href": f"{key}.html",
                "tag_class": col["tag_class"],
                "color_tag": col["color_tag"],
                "title": "暂无新闻",
                "excerpt": f"今天暂无{col['label']}相关新闻。",
            })
            continue

        # 2. 深度分析（头条）
        top_article = articles[0]
        source_name = extract_source_name(top_article)
        print(f"  正在生成深度分析... (来源: {source_name})")
        analysis = generate_deep_analysis(api_key, top_article, key)
        analysis["source_name"] = source_name
        print(f"  ✅ 深度分析完成: {analysis.get('title', '')[:40]}...")

        # 3. 快讯（其余文章，最多2条）
        brief_articles = articles[1:3]
        briefs = []
        if brief_articles:
            print(f"  正在生成快讯... ({len(brief_articles)} 条)")
            briefs = generate_briefs(api_key, brief_articles, key)
            print(f"  ✅ 快讯生成完成")

        # 4. 保存结果
        column_results[key] = {
            "analysis": analysis,
            "briefs": briefs,
        }

        overviews.append({
            "href": f"{key}.html",
            "tag_class": col["tag_class"],
            "color_tag": col["color_tag"],
            "title": analysis.get("title", ""),
            "excerpt": analysis.get("excerpt", ""),
        })

    # ── 生成 HTML 文件 ──
    print(f"\n{'='*40}")
    print("📄 生成 HTML 文件...")
    print(f"{'='*40}")

    # 首页
    index_html = render_index_page(overviews, f"{date_str} · {weekday_str}")
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"  ✅ index.html")

    # 栏目页
    for key in COLUMNS:
        col = COLUMNS[key]
        result = column_results.get(key)

        if result is None:
            # 无新闻 → 生成空状态页面
            html = render_empty_page(key, col, date_str, date_str_en)
        else:
            html = render_column_page(
                key, col,
                result["analysis"],
                result["briefs"],
                date_str, date_str_en,
            )

        filename = f"{key}.html"
        with open(os.path.join(OUTPUT_DIR, filename), "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✅ {filename}")

    # ── 完成 ──
    print(f"\n{'='*40}")
    print(f"🎉 简报生成完成！")
    print(f"📁 文件位于: {OUTPUT_DIR}/")
    print(f"📅 {date_str} ({weekday_str})")
    print(f"{'='*40}")
    return 0


def render_empty_page(col_key, col, date_str, date_str_en):
    """当某栏目无新闻时，生成空状态页"""
    navbar = render_navbar(col_key)
    footer = render_footer(date_str)
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{col['label']} · 每日新闻简报 {date_str_en}</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>

{navbar}

<div class="container">

  <div class="column-header">
    <a href="index.html" class="back-link">← 返回首页</a>
    <h1>{col['icon']} {col['label']} · 今日头条</h1>
    <p style="color:var(--text-secondary);font-size:14px;">{date_str}</p>
  </div>

  <div class="empty-state">
    <div class="icon">📭</div>
    <p>今天暂无{col['label']}相关新闻。</p>
  </div>

</div>

{footer}

</body>
</html>'''


if __name__ == "__main__":
    exit(main())
