# -*- coding: utf-8 -*-
"""
trendradar_to_briefing.py
==========================
把真正 TrendRadar（sansan0/TrendRadar）抓取后写入 output/ 的数据，
转换成 hotbot.py 能消费的 briefing.md（markdown 链接列表）。

TrendRadar 在 config.yaml 里配置 storage.formats.sqlite=true + html=true，
数据写到 storage.local.data_dir（默认 output/）下的 SQLite 数据库与 index.html。
本脚本优先读 SQLite（结构化、最干净），读不到再回退解析 index.html 的 <a> 链接。

用法（GitHub Actions / 本地均可）：
    python3 trendradar_to_briefing.py
环境变量：
    TR_OUTPUT_DIR   TrendRadar 数据目录（默认 output）
    BRIEFING_FILE   输出文件路径（默认 briefing.md，相对当前工作目录）
"""
import os
import re
import glob
import sqlite3

TR_OUTPUT_DIR = os.environ.get("TR_OUTPUT_DIR", "output")
BRIEFING_FILE = os.environ.get("BRIEFING_FILE", "briefing.md")

# SQLite 反射式列名匹配（不同版本列名可能不同）
TITLE_COLS = ("title", "headline", "name", "topic", "news_title")
URL_COLS = ("url", "link", "href", "news_url", "target_url")


def extract_sqlite(out_dir):
    dbs = (glob.glob(os.path.join(out_dir, "*.db"))
           + glob.glob(os.path.join(out_dir, "*.sqlite"))
           + glob.glob(os.path.join(out_dir, "*.sqlite3")))
    items = []
    for db in dbs:
        try:
            con = sqlite3.connect(db)
            cur = con.cursor()
            tbls = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for t in tbls:
                try:
                    cols = [r[1].lower() for r in cur.execute(f'PRAGMA table_info("{t}")')]
                except Exception:
                    continue
                title_c = next((c for c in cols if c in TITLE_COLS), None)
                url_c = next((c for c in cols if c in URL_COLS), None)
                if not (title_c and url_c):
                    continue
                try:
                    for row in cur.execute(f'SELECT "{title_c}","{url_c}" FROM "{t}"'):
                        ti, u = (row[0] or ""), (row[1] or "")
                        ti, u = ti.strip(), u.strip()
                        if ti and u.startswith("http"):
                            items.append((ti, u))
                except Exception:
                    continue
            con.close()
        except Exception as e:
            print(f"[转换] SQLite 读取 {db} 失败: {e}")
    return items


def extract_html(out_dir):
    cands = (glob.glob(os.path.join(out_dir, "index.html"))
             + glob.glob("index.html")
             + glob.glob(os.path.join(out_dir, "*.html")))
    html = None
    for c in cands:
        try:
            html = open(c, encoding="utf-8", errors="ignore").read()
            break
        except Exception:
            continue
    if not html:
        return []
    items = []
    for m in re.finditer(r'href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html):
        u, t = m.group(1).strip(), re.sub(r"\s+", " ", m.group(2)).strip()
        if t and u.startswith("http") and len(t) >= 4:
            items.append((t, u))
    return items


def main():
    out_dir = TR_OUTPUT_DIR
    items = extract_sqlite(out_dir)
    src = "sqlite"
    if not items:
        items = extract_html(out_dir)
        src = "html"
    # 去重（按标题）
    seen, uniq = set(), []
    for t, u in items:
        if t in seen:
            continue
        seen.add(t)
        uniq.append((t, u))
    with open(BRIEFING_FILE, "w", encoding="utf-8") as f:
        if not uniq:
            f.write("# TrendRadar 本次未抓到任何热点\n")
        else:
            for t, u in uniq:
                f.write(f"- [{t}]({u})\n")
    print(f"[转换] 来源={src} 抽取 {len(uniq)} 条热点 -> {BRIEFING_FILE}")


if __name__ == "__main__":
    main()
