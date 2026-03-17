"""
Daily trending updater for GitHub profile README.
Fetches top 10 from: X/Twitter (trends24.in), Substack, GitHub Trending
"""

import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MEDAL = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


# ── X / Twitter ──────────────────────────────────────────────────────────────

def fetch_x_trending():
    """Scrape trending topics from trends24.in (United States, fallback worldwide)."""
    for region in ("united-states", "worldwide"):
        try:
            url = f"https://trends24.in/{region}/"
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            trends = []
            # trends24 renders cards; pick the first (most-recent) card's ol list
            ol = soup.select_one(".trend-card__list")
            if not ol:
                continue
            for li in ol.find_all("li")[:10]:
                name_el = li.select_one(".trend-name")
                link_el = li.select_one(".trend-link")
                count_el = li.select_one(".tweet-count")
                if not name_el:
                    continue
                name = name_el.text.strip()
                count = count_el.text.strip() if count_el else ""
                if link_el and link_el.get("href", "").startswith("http"):
                    search_url = link_el["href"]
                else:
                    search_url = f"https://x.com/search?q={requests.utils.quote(name)}&src=trend_click"
                trends.append({"name": name, "count": count, "url": search_url})

            if trends:
                print(f"  [X] {len(trends)} trends from trends24.in/{region}")
                return trends
        except Exception as exc:
            print(f"  [X] trends24.in/{region} error: {exc}")
    return []


# ── Substack ─────────────────────────────────────────────────────────────────

def fetch_substack_trending():
    """Try Substack's internal API, fall back to discover page scrape."""
    # Primary: JSON API
    try:
        resp = requests.get(
            "https://substack.com/api/v1/trending?limit=10",
            headers=HEADERS,
            timeout=20,
        )
        resp.raise_for_status()
        raw = resp.json()
        # API returns {"posts": [...], "trendingPosts": [...(IDs only)]}
        # Actual post data is in the "posts" key
        if isinstance(raw, list):
            items = raw
        elif "posts" in raw and isinstance(raw["posts"], list):
            items = raw["posts"]
        else:
            items = raw.get("results", raw.get("items", []))
        posts = []
        for item in items[:10]:
            bylines = item.get("publishedBylines") or []
            author = bylines[0].get("name", "") if bylines else ""
            posts.append({
                "title": (item.get("title") or item.get("name") or "")[:70],
                "author": author or item.get("publication_name", ""),
                "url": item.get("canonical_url") or item.get("url") or "#",
            })
        if posts:
            print(f"  [Substack] {len(posts)} posts from API")
            return posts
    except Exception as exc:
        print(f"  [Substack] API error: {exc}")

    # Fallback: scrape /discover
    try:
        resp = requests.get("https://substack.com/discover", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        posts = []
        for a in soup.select("a.post-preview-title")[:10]:
            title = a.text.strip()
            link = a.get("href", "#")
            if not link.startswith("http"):
                link = "https://substack.com" + link
            posts.append({"title": title[:70], "author": "", "url": link})
        if posts:
            print(f"  [Substack] {len(posts)} posts from discover page")
            return posts
    except Exception as exc:
        print(f"  [Substack] discover scrape error: {exc}")

    return []


# ── GitHub Trending ───────────────────────────────────────────────────────────

def fetch_github_trending():
    """Scrape github.com/trending."""
    try:
        resp = requests.get("https://github.com/trending", headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        repos = []
        for article in soup.select("article.Box-row")[:10]:
            h2 = article.select_one("h2.h3 a")
            if not h2:
                continue
            path = h2.get("href", "").strip().lstrip("/")
            repo_url = f"https://github.com/{path}"

            desc_el = article.select_one("p")
            desc = desc_el.text.strip() if desc_el else ""
            if len(desc) > 72:
                desc = desc[:72] + "…"

            stars_el = article.select_one('a[href$="/stargazers"]')
            stars = stars_el.text.strip().replace(",", "").strip() if stars_el else "?"

            lang_el = article.select_one('[itemprop="programmingLanguage"]')
            lang = lang_el.text.strip() if lang_el else ""

            today_el = article.select_one("span.d-inline-block.float-sm-right")
            today_stars = today_el.text.strip() if today_el else ""

            repos.append({
                "name": path,
                "url": repo_url,
                "desc": desc,
                "stars": stars,
                "language": lang,
                "today_stars": today_stars,
            })

        print(f"  [GitHub] {len(repos)} repos from trending")
        return repos
    except Exception as exc:
        print(f"  [GitHub] error: {exc}")
        return []


# ── Section builders ──────────────────────────────────────────────────────────

def _now_cst():
    return datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M CST")


def build_x_section(trends):
    ts = _now_cst()
    if not trends:
        body = "\n> ⚠️ 暂时无法获取 X 热门数据，稍后重试\n"
    else:
        rows = ["| # | 热门话题 | 讨论量 |", "|:---:|:---|---:|"]
        for i, t in enumerate(trends[:10]):
            count = f"`{t['count']}`" if t.get("count") else "—"
            rows.append(f"| {MEDAL[i]} | [{t['name']}]({t['url']}) | {count} |")
        body = "\n" + "\n".join(rows) + "\n"

    return (
        "<!-- TRENDING-X-START -->\n"
        "<details open>\n"
        "<summary><h2>🐦 X (Twitter) 今日热议 Top 10</h2></summary>\n"
        f"{body}\n"
        "</details>\n\n"
        f"<sub>🕐 更新于 {ts} &nbsp;·&nbsp; 数据来源: trends24.in</sub>\n"
        "<!-- TRENDING-X-END -->"
    )


def build_substack_section(posts):
    ts = _now_cst()
    if not posts:
        body = "\n> ⚠️ 暂时无法获取 Substack 热门数据，稍后重试\n"
    else:
        rows = ["| # | 文章标题 | 作者 / Newsletter |", "|:---:|:---|:---|"]
        for i, p in enumerate(posts[:10]):
            title = p.get("title", "—")
            author = p.get("author", "") or "—"
            url = p.get("url", "#")
            rows.append(f"| {MEDAL[i]} | [{title}]({url}) | {author} |")
        body = "\n" + "\n".join(rows) + "\n"

    return (
        "<!-- TRENDING-SUBSTACK-START -->\n"
        "<details open>\n"
        "<summary><h2>📰 Substack 热门文章 Top 10</h2></summary>\n"
        f"{body}\n"
        "</details>\n\n"
        f"<sub>🕐 更新于 {ts} &nbsp;·&nbsp; 数据来源: substack.com</sub>\n"
        "<!-- TRENDING-SUBSTACK-END -->"
    )


def build_github_section(repos):
    ts = _now_cst()
    if not repos:
        body = "\n> ⚠️ 暂时无法获取 GitHub 热门数据，稍后重试\n"
    else:
        rows = ["| # | 项目 | ⭐ Stars | 语言 | 简介 |", "|:---:|:---|:---:|:---:|:---|"]
        for i, r in enumerate(repos[:10]):
            lang = f"`{r['language']}`" if r.get("language") else "—"
            desc = r.get("desc") or "—"
            rows.append(
                f"| {MEDAL[i]} | [{r['name']}]({r['url']}) "
                f"| {r['stars']} | {lang} | {desc} |"
            )
        body = "\n" + "\n".join(rows) + "\n"

    return (
        "<!-- TRENDING-GITHUB-START -->\n"
        "<details open>\n"
        "<summary><h2>⭐ GitHub 热门项目 Top 10</h2></summary>\n"
        f"{body}\n"
        "</details>\n\n"
        f"<sub>🕐 更新于 {ts} &nbsp;·&nbsp; 数据来源: github.com/trending</sub>\n"
        "<!-- TRENDING-GITHUB-END -->"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def update_readme(readme_path: str = "README.md"):
    print("📡 Fetching trending data...")
    x_trends = fetch_x_trending()
    substack_posts = fetch_substack_trending()
    github_repos = fetch_github_trending()

    print("📝 Patching README...")
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    replacements = {
        r"<!-- TRENDING-X-START -->.*?<!-- TRENDING-X-END -->":
            build_x_section(x_trends),
        r"<!-- TRENDING-SUBSTACK-START -->.*?<!-- TRENDING-SUBSTACK-END -->":
            build_substack_section(substack_posts),
        r"<!-- TRENDING-GITHUB-START -->.*?<!-- TRENDING-GITHUB-END -->":
            build_github_section(github_repos),
    }

    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)

    print("✅ README updated successfully!")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "README.md"
    update_readme(path)
