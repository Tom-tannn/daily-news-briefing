#!/usr/bin/env python3
"""
每日新闻简报生成脚本
自动从 Perigon News API 获取新闻并生成多页 HTML 网站

使用方式:
    python scripts/generate_news.py

依赖:
    pip install requests
"""

import os
import json
import requests
from datetime import datetime, timezone, timedelta

# === 配置 ===
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")
API_BASE = "https://api.perigon.io/v2"

# === 栏目配置：搜索关键词和分类 ===
COLUMNS = {
    "tech": {
        "label": "科技",
        "icon": "💻",
        "tag_class": "tag-tech",
        "color_tag": "💻 科技",
        "query": "technology AI tech innovation",
        "category": ["Tech"],
        "sort": "date",
    },
    "politics": {
        "label": "国际政治",
        "icon": "🌍",
        "tag_class": "tag-politics",
        "color_tag": "🌍 国际政治",
        "query": "international politics world affairs diplomacy",
        "category": ["Politics", "World"],
        "sort": "date",
    },
    "finance": {
        "label": "金融",
        "icon": "📈",
        "tag_class": "tag-finance",
        "color_tag": "📈 金融",
        "query": "stock market economy finance",
        "category": ["Finance", "Business"],
        "sort": "date",
    },
}


def fetch_news(api_key, column_key):
    """从 Perigon API 获取某个栏目的新闻"""
    col = COLUMNS[column_key]
    params = {
        "query": col["query"],
        "category": col["category"],
        "sortBy": col["sort"],
        "size": 10,
        "showReprints": "false",
        "summarize": "true",
        "countries": ["us"],
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(f"{API_BASE}/articles", params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    api_key = os.environ.get("PERIGON_API_KEY")
    if not api_key:
        print("❌ 请设置 PERIGON_API_KEY 环境变量")
        return 1

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 获取今天的日期（北京时间）
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y年%m月%d日")
    today_en = datetime.now(beijing_tz).strftime("%Y-%m-%d")

    print(f"📰 正在生成 {today} 的新闻简报...")

    # 抓取三个栏目的新闻
    all_news = {}
    for key in COLUMNS:
        print(f"  正在获取 {COLUMNS[key]['label']} 新闻...")
        try:
            articles = fetch_news(api_key, key)
            all_news[key] = articles
            print(f"    ✅ 获取到 {len(articles)} 条新闻")
        except Exception as e:
            print(f"    ❌ 获取失败: {e}")
            all_news[key] = []

    # TODO: 用 Jinja2 或字符串模板渲染 HTML
    # 目前模板已静态写在 public/ 目录中
    # 后续可接入 LLM 进行深度分析生成

    print(f"\n✅ 简报生成完成！文件位于 {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    exit(main())
