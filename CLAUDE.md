# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

每日新闻简报 — 一个多页响应式 HTML 新闻网站，从 Perigon News 获取真实新闻，用通俗中文撰写深度分析。

- **栏目**: 科技（💻）、国际政治（🌍）、金融（📈）
- **数据源**: [Perigon News](https://perigon.io/) — 200k+ 全球新闻来源，提供结构化新闻 API（MCP 工具已接入）
- **部署**: Vercel（纯静态 HTML）
- **更新**: 每个栏目 2-3 条新闻，头条深度分析（事实→分析→预测），其余简要快讯

## 写作规范

面向普通大众读者，务必遵循以下规则：

### ✅ 要这样做
- 用日常语言解释复杂概念（如"量化宽松" → "央行印钱"、"通胀" → "物价上涨"）
- 每个分析的完整结构：**📌 发生了什么** → **🔍 这意味着什么** → **🔮 接下来会怎样**
- 预测放在 `.prediction-box` 卡片中（蓝色背景 + 左边框）
- 引用来源（来源名称 + 记者名）

### ❌ 不要这样做
- 不要用专业术语不解释（地缘政治、资产负债表、货币紧缩等）
- 不要编造新闻 — 必须基于 Perigon 返回的真实文章
- 不要用 AI 生成的"假新闻" — Perigon 给的是真实数据

## 架构

```
news-briefing/
├── public/                # 静态网站（直接部署到 Vercel）
│   ├── index.html         # 首页：导航 + 今日概览（3 栏卡片）
│   ├── styles.css         # 全局样式（响应式、深色/浅色模式）
│   ├── tech.html          # 科技栏目页
│   ├── politics.html      # 国际政治栏目页
│   └── finance.html       # 金融栏目页
├── scripts/
│   └── generate_news.py   # Perigon API 集成脚本（自动化生成用）
├── vercel.json            # Vercel 配置（cleanUrls）
└── requirements.txt       # Python 依赖
```

### 页面结构

**首页** (`index.html`): 顶部粘性导航栏（sticky navbar, backdrop-filter blur）+ 日期标题 + 三栏概览网格 (+ `.overview-grid` 响应式: 3列→2列→1列)

**栏目页** (`tech.html`, `politics.html`, `finance.html`):
1. 返回首页链接 + 栏目标题
2. 深度分析卡片 (`.deep-analysis`): 标签 → 标题 → 元信息 → 📌发生了什么 → 🔍分析 → 🔮预测框
3. 快讯列表 (`.brief-section`): 每条用 `.brief-item` 卡片，标题 + 摘要 + 来源

### CSS 设计系统

- CSS 变量切换深色/浅色模式（`prefers-color-scheme: dark`）
- 三个栏目颜色：tech=蓝色(#3b82f6), politics=红色(#ef4444), finance=绿色(#10b981)
- 标签徽章：各栏目有独立 `.tag-tech` / `.tag-politics` / `.tag-finance` 样式
- 导航栏 `.active` 类高亮当前页
- 空状态 `.empty-state` 用于无内容时显示

### 自动化脚本

`generate_news.py` 从环境变量 `PERIGON_API_KEY` 和 `DEEPSEEK_API_KEY` 读取 API key（**不要硬编码**），通过 Perigon API 获取新闻，再调用 DeepSeek API 生成深度分析内容，最后渲染为 HTML。

## 常用命令

```bash
# 本地预览（Python 内置服务器）
cd news-briefing && python3 -m http.server 8080 -d public

# 安装 Python 依赖
cd news-briefing && pip install -r requirements.txt

# 运行自动化脚本（需设置两个 API key）
cd news-briefing && PERIGON_API_KEY=your_key DEEPSEEK_API_KEY=your_key python scripts/generate_news.py
```

## Perigon MCP 使用指南

Session 已连接 Perigon News MCP 服务器，工具前缀为 `mcp__perigon-news__`，可直接在对话中使用。

### 常用工具

- `search_news_articles` — 搜索文章，支持 Boolean 查询、分类/主题/情感过滤
- `search_news_stories` — 搜索聚合新闻故事（clustered headlines）
- `get_company_news` / `get_person_news` / `get_location_news` — 快捷查询
- `search_companies` / `search_people` — 查询公司/人物背景信息
- `search_wikipedia` / `search_vector_wikipedia` — 百科背景搜索

### 搜索技巧

- 默认国家过滤为 US，需要国际新闻时设 `countries: []` 或指定其他代码
- `sourceGroup: "top25"` 过滤高质量来源
- `showReprints: false` 去重（默认）
- `search_news_stories` 获取聚合头条，比单篇文章更适合做"今日要闻"概览
- 向量搜索 `search_vector_news` 适合概念性/语义搜索

### 新闻文章 → HTML 转换流程

1. 用 Perigon 搜索获取真实文章（标题、摘要、来源、日期）
2. 提取关键事实，用大众化语言改写
3. 按 发生了什么→分析→预测 结构组织
4. 每条分析标注来源（尊重版权）
5. 渲染为 HTML（保持已有页面结构和样式一致性）
