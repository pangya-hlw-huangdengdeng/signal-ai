#!/usr/bin/env python3
"""
SIGNAL.AI Feed Fetcher
======================
Fetches 20+ RSS feeds + Hacker News API, classifies articles into
the 6-layer AI Technology Panorama framework, and generates data.json.

Run:  python fetcher/update.py
Output: data.json (in repo root)
"""

import feedparser
import requests
import requests.packages.urllib3
import json
import re
import hashlib
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Suppress SSL warnings when verify=False
requests.packages.urllib3.disable_warnings()

# ── Output path ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUT = ROOT / "data.json"

# ── Feed Sources ──────────────────────────────────────────────────────────────
# (id, display_name, rss_url, layer_hint)
#
# Layer guide:
#   l0 = 领袖观点  — industry leader opinions, prominent researcher essays
#   l1 = 算力硬件  — chips, hardware, compute infrastructure
#   l2 = 基础模型  — foundation model releases, training, benchmarks, papers
#   l3 = 推理工程  — inference, serving, MLOps, deployment engineering
#   l4 = 交互Agent — consumer AI products, agents, user-facing apps
#   l5 = 生态商业  — funding, enterprise, policy, business strategy

FEEDS = [
    # ── L0 领袖观点: 行业领袖 + 独立研究者 ─────────────────────────────────────
    # Original: Jack Clark, Ethan Mollick, Arvind Narayanan
    ("import_ai",     "Import AI",            "https://importai.substack.com/feed",                "l0"),
    ("one_useful",    "One Useful Thing",     "https://www.oneusefulthing.org/feed",               "l0"),
    ("ai_snake_oil",  "AI Snake Oil",         "https://aisnakeoil.substack.com/feed",              "l0"),
    # Extended: same tier — researchers/practitioners with independent platforms
    ("gary_marcus",   "Gary Marcus",          "https://garymarcus.substack.com/feed",              "l0"),
    ("chollet",       "François Chollet",     "https://fchollet.substack.com/feed",                "l0"),
    ("karpathy",      "Andrej Karpathy",      "https://karpathy.bearblog.dev/feed/",               "l0"),
    ("lilian_weng",   "Lilian Weng",          "https://lilianweng.github.io/index.xml",            "l0"),
    ("the_gradient",  "The Gradient",         "https://thegradient.pub/rss/",                      "l0"),

    # ── L1 算力硬件: 芯片 + 算力基础设施 ─────────────────────────────────────
    # Original: NVIDIA Blog, Ars Technica
    ("nvidia",        "NVIDIA Blog",          "https://blogs.nvidia.com/feed/",                    "l1"),
    ("ars_technica",  "Ars Technica",         "https://feeds.arstechnica.com/arstechnica/technology-lab", "l1"),
    # Extended: specialized chip/hardware analysis
    ("semianalysis",  "SemiAnalysis",         "https://www.semianalysis.com/feed",                 "l1"),
    ("chip_letter",   "The Chip Letter",      "https://thechipletter.substack.com/feed",           "l1"),
    ("ieee_spectrum", "IEEE Spectrum",        "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss", "l1"),
    ("toms_hardware", "Tom's Hardware",       "https://www.tomshardware.com/feeds/all",            "l1"),

    # ── L2 基础模型: 模型公司 + 论文 ─────────────────────────────────────────
    # Original: OpenAI, Google AI, Meta Engineering, HuggingFace Papers
    ("openai",        "OpenAI Blog",          "https://openai.com/blog/rss.xml",                   "l2"),
    ("anthropic",     "Anthropic",            "https://www.anthropic.com/rss.xml",                 "l2"),
    ("google_ai",     "Google AI Blog",       "https://blog.google/rss/",                          "l2"),
    ("deepmind",      "Google DeepMind",      "https://deepmind.google/feed.xml",                  "l2"),
    ("meta_ai",       "Meta Engineering",     "https://engineering.fb.com/feed/",                  "l2"),
    ("hf_papers",     "HuggingFace Papers",   "https://huggingface.co/papers/rss.xml",             "l2"),
    # Extended: other frontier model labs + research paper streams
    ("cohere",        "Cohere Blog",          "https://cohere.com/blog/rss",                       "l2"),
    ("arxiv_lg",      "arXiv cs.LG",          "https://arxiv.org/rss/cs.LG",                      "l2"),
    ("arxiv_ai",      "arXiv cs.AI",          "https://arxiv.org/rss/cs.AI",                      "l2"),

    # ── L3 推理工程: 推理 + MLOps + 部署工程 ─────────────────────────────────
    # Original: Latent Space, Interconnects, Simon Willison
    ("latent_space",  "Latent Space",         "https://www.latent.space/feed",                     "l3"),
    ("interconnects", "Interconnects",        "https://www.interconnects.ai/feed",                 "l3"),
    ("simon_willison","Simon Willison",       "https://simonwillison.net/atom/everything/",        "l3"),
    # Extended: ML engineering depth — deployment, optimization, systems
    ("chip_huyen",    "Chip Huyen",           "https://huyenchip.com/feed.xml",                   "l3"),
    ("ahead_of_ai",   "Ahead of AI",          "https://magazine.sebastianraschka.com/feed",       "l3"),

    # ── L4 交互Agent: 产品 + Agent + 消费级应用 ──────────────────────────────
    # Original: The Verge, TechCrunch, 404 Media
    ("verge_ai",      "The Verge",            "https://www.theverge.com/rss/index.xml",            "l4"),
    ("techcrunch_ai", "TechCrunch AI",        "https://techcrunch.com/category/artificial-intelligence/feed/", "l4"),
    ("404_media",     "404 Media",            "https://www.404media.co/rss/",                      "l4"),
    # Extended: VC product perspective + broader tech product coverage
    ("venturebeat",   "VentureBeat AI",       "https://venturebeat.com/category/ai/feed/",         "l4"),

    # ── L5 生态商业: 融资 + 企业 + 政策 + 市场 ──────────────────────────────
    # Original: Ben's Bites, MIT Tech Review
    ("bens_bites",    "Ben's Bites",          "https://www.bensbites.com/feed",                    "l5"),
    ("mit_review",    "MIT Tech Review",      "https://www.technologyreview.com/topic/artificial-intelligence/feed/", "l5"),
    # Extended: business strategy, VC, policy, enterprise AI
    ("a16z",          "a16z",                 "https://a16z.com/tag/ai/feed/",                     "l5"),
    ("wired_ai",      "Wired",                "https://www.wired.com/feed/tag/ai/latest/rss",      "l5"),
]

# ── AI Relevance Keywords ─────────────────────────────────────────────────────
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "gpt", "claude", "gemini", "llama",
    "openai", "anthropic", "deepmind", "nvidia", "gpu", "transformer",
    "agent", "chatgpt", "diffusion", "generative ai", "foundation model",
    "neural network", "training", "inference", "benchmark", "multimodal",
    "reasoning", "embedding", "fine-tuning", "rag", "vector database",
    "deepseek", "qwen", "mistral", "hugging face", "huggingface",
    "model release", "compute", "chip", "tpu", "silicon wafer",
    "robot", "automation", "copilot", "assistant", "language model",
    "image generation", "text generation", "stable diffusion", "midjourney",
    "sora", "o3", "o4", "grok", "perplexity", "manus", "cursor ai",
]

# ── Layer Classification Keywords ─────────────────────────────────────────────
LAYER_KEYWORDS = {
    "l0": [
        # Named leaders (original)
        "jensen huang", "sam altman", "demis hassabis", "karpathy", "andrej karpathy",
        "yann lecun", "geoffrey hinton", "jack clark", "nathan lambert", "ethan mollick",
        "arvind narayanan", "gary marcus", "francois chollet", "lilian weng",
        "dario amodei", "ilya sutskever", "greg brockman", "fei-fei li",
        # Content signals
        "ceo", "founder", "keynote", "opinion", "interview", "vision", "perspective",
        "prediction", "future of ai", "agi", "philosophy", "essay", "thoughts on",
        "i believe", "my take", "open letter", "manifesto", "reflection",
        "what i learned", "lessons from", "why i", "the real reason",
    ],
    "l1": [
        # Named companies/products (original + extended)
        "nvidia", "amd", "intel", "qualcomm", "apple silicon", "tsmc", "samsung",
        "blackwell", "hopper", "grace", "hbm3", "hbm4", "mi300", "mi350",
        "tpu v5", "trainium", "gaudi", "groq", "cerebras",
        # Content signals
        "gpu", "chip", "hardware", "tpu", "silicon", "semiconductor",
        "flops", "petaflops", "memory bandwidth", "interconnect", "nvlink",
        "datacenter", "power consumption", "cooling", "liquid cooling",
        "wafer", "fab", "3nm", "2nm", "packaging", "hbm",
        "compute cluster", "ai factory", "inference chip",
    ],
    "l2": [
        "model release", "gpt-", "claude ", "gemini ", "llama ",
        "mistral", "deepseek", "qwen", "training", "pretraining",
        "fine-tuning", "benchmark", "mmlu", "humaneval", "swe-bench",
        "foundation model", "model weights", "open source model",
        "parameter", "context window", "multimodal model", "elo score",
        "chatbot arena", "huggingface",
    ],
    "l3": [
        "inference", "serving", "deployment", "api latency", "throughput",
        "vllm", "tensorrt", "onnx", "quantization", "int4", "int8",
        "tokens per second", "batch processing", "kv cache",
        "speculative decoding", "flash attention", "distillation",
        "model serving", "inference cost", "api pricing",
    ],
    "l4": [
        "agent", "chatbot", "assistant app", "product launch",
        "chatgpt", "copilot", "perplexity", "manus", "workflow",
        "computer use", "tool use", "function calling",
        "plugin", "integration", "user interface", "monthly active",
        "consumer ai", "app store", "mobile ai",
    ],
    "l5": [
        "funding", "startup", "investment", "revenue", "market cap",
        "microsoft", "google cloud", "amazon aws", "azure openai",
        "partnership", "enterprise deal", "saas", "valuation", "ipo",
        "acquisition", "commercial license", "regulation", "policy",
        "eu ai act", "copyright", "lawsuit", "competition",
    ],
}

LAYER_NAMES = {
    "l0": "领袖观点", "l1": "算力硬件", "l2": "基础模型",
    "l3": "推理工程", "l4": "交互Agent", "l5": "生态商业",
}
LAYER_CATS = {
    "l0": "L0 · 领袖观点", "l1": "L1 · 算力硬件", "l2": "L2 · 基础模型",
    "l3": "L3 · 推理工程", "l4": "L4 · 交互Agent", "l5": "L5 · 生态商业",
}

# Source heat multipliers (how "hot" articles from this source tend to be)
SOURCE_HEAT = {
    "openai": 3.0, "anthropic": 2.8, "nvidia": 2.5, "google_ai": 2.3,
    "deepmind": 2.2, "meta_ai": 2.0, "techcrunch_ai": 1.8,
    "verge_ai": 1.6, "mit_review": 1.5, "hf_papers": 1.4,
    "import_ai": 1.3, "latent_space": 1.3, "interconnects": 1.2,
    "ars_technica": 1.2, "wired_ai": 1.1, "bens_bites": 1.1,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_ai_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in AI_KEYWORDS)


def classify_layer(title: str, summary: str, hint: str) -> str:
    text = (title + " " + summary).lower()
    scores = {layer: 0 for layer in LAYER_KEYWORDS}
    for layer, keywords in LAYER_KEYWORDS.items():
        scores[layer] = sum(1 for kw in keywords if kw in text)
    best_layer = max(scores, key=scores.get)
    # Fall back to feed hint if no keyword matched
    return best_layer if scores[best_layer] > 0 else hint


def time_ago(published_parsed) -> str:
    if not published_parsed:
        return "刚刚"
    try:
        pub = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        diff = datetime.now(timezone.utc) - pub
        total_mins = int(diff.total_seconds() / 60)
        if total_mins < 0:
            return "刚刚"
        if total_mins < 60:
            return f"{total_mins}分钟前"
        if total_mins < 1440:
            return f"{total_mins // 60}小时前"
        return f"{total_mins // 1440}天前"
    except Exception:
        return "近期"


def get_published_ts(published_parsed) -> int:
    """Return Unix timestamp for sorting; cap future dates at now."""
    if not published_parsed:
        return 0
    try:
        pub = datetime(*published_parsed[:6], tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        # Cap future-dated articles at current time
        if pub > now:
            pub = now
        return int(pub.timestamp())
    except Exception:
        return 0


def article_id(title: str) -> str:
    """Stable short ID based on title hash."""
    return "a" + hashlib.md5(title.encode("utf-8")).hexdigest()[:8]


def heat_value(feed_id: str, rank: int) -> str:
    """Generate a realistic-looking heat value."""
    base = SOURCE_HEAT.get(feed_id, 1.0)
    val = base * max(0.3, 1 - rank * 0.12) * 15
    return f"{val:.1f}K"


# ── Fetch RSS ─────────────────────────────────────────────────────────────────

def fetch_rss(feed_id: str, name: str, url: str, hint: str) -> list:
    articles = []
    try:
        # Use requests to download (handles SSL, redirects, timeouts better)
        resp = requests.get(url, timeout=15, verify=False,
                            headers={"User-Agent": "SIGNAL.AI/1.0 (+https://signal-ai-pulse.netlify.app)"})
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for i, entry in enumerate(feed.entries[:6]):
            title = entry.get("title", "").strip()
            raw_summary = entry.get("summary", entry.get("description", ""))
            summary = strip_html(raw_summary)[:400]
            link = entry.get("link", "")

            if not title or not link:
                continue
            if not is_ai_relevant(title, summary):
                continue

            layer = classify_layer(title, summary, hint)
            pp = entry.get("published_parsed")
            articles.append({
                "id": article_id(title),
                "layer": layer,
                "cat": LAYER_CATS[layer],
                "title": title,
                "src": name,
                "time": time_ago(pp),
                "published_ts": get_published_ts(pp),
                "heat": heat_value(feed_id, i),
                "views": heat_value(feed_id, i - 1 if i > 0 else 0),
                "url": link,
                "tags": [],
                "body": (f"<p>{summary}</p><p>点击下方「查看原文」阅读完整内容。</p>" if summary else "<p>点击「查看原文」阅读完整内容。</p>"),
            })
    except Exception as e:
        print(f"  ⚠ {name}: {e}", file=sys.stderr)
    return articles


# ── Hacker News ───────────────────────────────────────────────────────────────

def fetch_hn() -> list:
    """Fetch top HN stories relevant to AI."""
    results = []
    try:
        top_ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10
        ).json()[:300]

        for sid in top_ids[:80]:
            try:
                item = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=5
                ).json()
                if not item or item.get("type") != "story":
                    continue
                title = item.get("title", "")
                if not is_ai_relevant(title, ""):
                    continue
                results.append({
                    "platform": "HN",
                    "badge": "pb-hn",
                    "title": title,
                    "url": item.get("url") or f"https://news.ycombinator.com/item?id={sid}",
                    "votes": f"{item.get('score', 0):,}",
                    "comments": f"{item.get('descendants', 0):,}",
                    "time": "近期",
                })
                if len(results) >= 6:
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"  ⚠ HN API: {e}", file=sys.stderr)
    return results


# ── Heatmap ───────────────────────────────────────────────────────────────────

def compute_heatmap(articles: list) -> list:
    """Compute 6-dim heatmap scores from article distribution."""
    counts = {l: 0 for l in ["l0", "l1", "l2", "l3", "l4", "l5"]}
    for a in articles:
        if a["layer"] in counts:
            counts[a["layer"]] += 1

    total = sum(counts.values()) or 1
    ORDER = ["l2", "l4", "l0", "l5", "l1", "l3"]
    LAYER_META = {"l0": "LAYER 0", "l1": "LAYER 1", "l2": "LAYER 2",
                  "l3": "LAYER 3", "l4": "LAYER 4", "l5": "LAYER 5"}

    result = []
    for lid in ORDER:
        pct = int(counts[lid] / total * 100) if total else 50
        # 6 dims: 资讯热度 社区讨论 模型动态 工具趋势 技术突破 商业动态
        seed = abs(hash(lid))
        vals = [
            min(100, max(10, pct + (seed % 20) - 10)),
            min(100, max(10, pct + ((seed >> 3) % 25) - 12)),
            min(100, max(5,  pct + ((seed >> 6) % 30) - 20)) if lid in ("l2", "l3") else min(60, max(5, pct // 2)),
            min(100, max(5,  pct + ((seed >> 9) % 35) - 25)) if lid in ("l4", "l3") else min(50, max(5, pct // 3)),
            min(100, max(10, pct + ((seed >> 12) % 20) - 5)),
            min(100, max(10, pct + ((seed >> 15) % 25) - 8)) if lid == "l5" else min(70, max(10, pct // 2 + 10)),
        ]
        # 7-day trend: gradually climbing toward today's score
        base_trend = max(20, pct - 25)
        trend = [min(100, base_trend + i * ((pct - base_trend) // 6 + 1)) for i in range(7)]

        result.append({
            "id": lid,
            "num": LAYER_META[lid],
            "name": LAYER_NAMES[lid],
            "vals": vals,
            "trend": trend,
        })

    # Sort by composite score descending
    def composite(l):
        w = [0.3, 0.25, 0.2, 0.1, 0.1, 0.05]
        return sum(v * w[i] for i, v in enumerate(l["vals"]))

    return sorted(result, key=composite, reverse=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("🔍 SIGNAL.AI Feed Fetcher starting...")

    all_articles = []
    seen_ids = set()

    for feed_id, name, url, hint in FEEDS:
        print(f"  → {name}")
        items = fetch_rss(feed_id, name, url, hint)
        for a in items:
            if a["id"] not in seen_ids:
                seen_ids.add(a["id"])
                all_articles.append(a)

    print(f"\n✅ {len(all_articles)} unique AI articles from RSS feeds")

    # Sort all articles by published_ts descending (newest first)
    all_articles.sort(key=lambda a: a.get("published_ts", 0), reverse=True)

    # Layer distribution (preserve time-sorted order within each layer)
    by_layer: dict[str, list[str]] = {}
    for a in all_articles:
        by_layer.setdefault(a["layer"], []).append(a["id"])
    for lid, ids in by_layer.items():
        print(f"   {LAYER_NAMES[lid]}: {len(ids)} articles")

    # Top 5 most recent articles across all layers (for featured section)
    top5_ids = [a["id"] for a in all_articles[:5]]

    # Hacker News
    print("\n  → Hacker News API")
    hn_items = fetch_hn()
    print(f"  ✅ {len(hn_items)} AI discussions from HN")

    # Ticker: top 14 articles sorted by recency
    ticker = []
    col_map = {"l0": "var(--l0)", "l1": "var(--l1)", "l2": "var(--l2)",
               "l3": "var(--l3)", "l4": "var(--l4)", "l5": "var(--l5)"}
    for a in all_articles[:14]:
        ticker.append({
            "tag": a["src"][:9].upper(),
            "col": col_map.get(a["layer"], "var(--l2)"),
            "text": a["title"][:65] + ("…" if len(a["title"]) > 65 else ""),
        })

    # Build articles dict (id -> article data without id key)
    articles_dict = {a["id"]: {k: v for k, v in a.items() if k != "id"}
                     for a in all_articles}

    # Community grid: HN + fallback placeholders
    community = hn_items[:]
    # Pad with stable placeholders if HN fetch yielded fewer items
    while len(community) < 4:
        community.append({
            "platform": "HN",
            "badge": "pb-hn",
            "title": "Visit Hacker News for the latest AI discussions",
            "url": "https://news.ycombinator.com",
            "votes": "—",
            "comments": "—",
            "time": "实时",
        })

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(all_articles),
        "articles": articles_dict,
        "by_layer": by_layer,
        "top5": top5_ids,
        "layers": compute_heatmap(all_articles),
        "ticker": ticker,
        "community": community[:8],
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n🚀 data.json written → {OUTPUT}")
    print(f"   Total articles: {len(articles_dict)}")
    print(f"   Updated at: {data['updated_at']}")


if __name__ == "__main__":
    main()
