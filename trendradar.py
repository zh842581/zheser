# -*- coding: utf-8 -*-
"""
trendradar.py —— 多平台公开热榜追踪器（无需任何 API Key）
========================================================
思路参照开源项目 TrendRadar：直接请求各平台【公开热榜接口】，
不依赖 tophub / 任何付费 Key。每个平台定义为一个 source，含：
  - 请求方式 / 地址 / 请求头
  - 一个解析函数，把原始 JSON 变成统一的 [{title, url, heat}] 结构

特性：
  - 任一平台接口被墙 / 需登录 cookie / 超时，自动跳过，不影响其它平台；
  - 抓回全部热榜后，用关键词漏斗筛出与选题相关的话题；
  - 可作为独立脚本运行（`python trendradar.py`），也可被 hotbot.py 导入复用。

依赖：仅 Python 标准库（urllib / ssl / json），无需 pip install。
"""

import json
import ssl
import time
import urllib.parse
import urllib.request

# 关闭证书校验：部分国内接口证书链在沙箱里校验会失败，这里统一放行（仅用于抓取热榜文本）
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ----------------------------- 各平台解析函数 -----------------------------
def _parse_toutiao(j):
    out = []
    for it in j.get("data", []) or []:
        title = it.get("Title")
        if title:
            out.append({"title": title, "url": it.get("Url") or "", "heat": it.get("HotValue")})
    return out


def _parse_douyin(j):
    out = []
    wl = (j.get("data") or {}).get("word_list") or []
    for it in wl:
        word = it.get("word")
        if word:
            out.append({
                "title": word,
                "url": "https://www.douyin.com/search/" + urllib.parse.quote(word),
                "heat": it.get("hot_value"),
            })
    return out


def _parse_weibo(j):
    out = []
    for it in (j.get("data") or {}).get("realtime", []) or []:
        word = it.get("word")
        if word:
            out.append({
                "title": word,
                "url": "https://s.weibo.com/weibo?q=%23" + urllib.parse.quote(word) + "%23",
                "heat": it.get("num"),
            })
    return out


def _parse_zhihu(j):
    out = []
    for it in j.get("data", []) or []:
        tgt = it.get("target") or {}
        title = tgt.get("title")
        if not title:
            continue
        url = tgt.get("url") or it.get("url") or ""
        if url.startswith("/"):
            url = "https://www.zhihu.com" + url
        out.append({"title": title, "url": url, "heat": it.get("detail_text")})
    return out


def _parse_bilibili(j):
    out = []
    for it in (j.get("data") or {}).get("list", []) or []:
        title = it.get("title")
        if not title:
            continue
        bvid = it.get("bvid")
        url = "https://www.bilibili.com/video/" + bvid if bvid else ""
        out.append({"title": title, "url": url, "heat": (it.get("stat") or {}).get("view")})
    return out


def _parse_baidu(j):
    # 结构嵌套：data.cards[].content[].content[] 才是真正的热榜条目
    out = []
    for card in (j.get("data") or {}).get("cards", []) or []:
        for block in card.get("content", []) or []:
            for it in block.get("content", []) or []:
                word = it.get("word")
                if word:
                    out.append({
                        "title": word,
                        "url": it.get("url") or "https://www.baidu.com/s?wd=" + urllib.parse.quote(word),
                        "heat": it.get("hotScore"),
                    })
    return out


# ----------------------------- 平台 source 定义 -----------------------------
# requires_cookie=True 的接口在本环境大概率被挡，但用户本机（有登录态/cookie）通常可用。
SOURCES = [
    {
        "name": "头条",
        "url": "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc",
        "parser": _parse_toutiao,
        "requires_cookie": False,
    },
    {
        "name": "抖音",
        "url": "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383",
        "parser": _parse_douyin,
        "requires_cookie": True,
    },
    {
        "name": "微博",
        "url": "https://weibo.com/ajax/side/hotSearch",
        "parser": _parse_weibo,
        "requires_cookie": True,
    },
    {
        "name": "知乎",
        "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=50",
        "parser": _parse_zhihu,
        "requires_cookie": True,
    },
    {
        "name": "B站",
        "url": "https://api.bilibili.com/x/web-interface/popular?pn=1",
        "parser": _parse_bilibili,
        "requires_cookie": True,
    },
    {
        "name": "百度",
        "url": "https://top.baidu.com/api/board?platform=wise&tab=realtime",
        "parser": _parse_baidu,
        "requires_cookie": False,
    },
]


def _fetch_source(src):
    """抓取单个平台，失败返回空列表（不抛异常）。"""
    try:
        req = urllib.request.Request(src["url"], headers={"User-Agent": _UA, "Referer": "https://www.baidu.com/"})
        with urllib.request.urlopen(req, timeout=12, context=_CTX) as r:
            text = r.read().decode("utf-8", "ignore")
        try:
            j = json.loads(text)
        except Exception:
            return []  # 返回的是反爬页/HTML，视为无数据
        return src["parser"](j)
    except Exception as e:
        print(f"  [{src['name']}] 获取失败：{type(e).__name__}: {str(e)[:60]}")
        return []


def fetch_all(enabled=None):
    """抓取所有（或全部启用的）平台热榜，返回 {平台名: [item,...]}。"""
    sources = [s for s in SOURCES if enabled is None or s["name"] in enabled]
    result = {}
    for src in sources:
        print(f"正在获取【{src['name']}】热榜...")
        items = _fetch_source(src)
        result[src["name"]] = items
        print(f"  {src['name']} 抓到 {len(items)} 条")
        time.sleep(0.6)  # 礼貌性间隔，降低被封风险
    return result


def filter_related(items_by_platform, keywords):
    """关键词漏斗：逐平台筛选标题命中的热点。"""
    out = {}
    for platform, items in items_by_platform.items():
        hit = [it for it in items if any(kw in (it.get("title") or "") for kw in keywords)]
        if hit:
            out[platform] = hit
    return out


# ----------------------------- 独立运行入口 -----------------------------
def _main():
    KEYWORDS = [
        # 身体症状 / 不适
        "不舒服", "乏力", "疲劳", "疲惫", "没劲", "浑身", "酸痛", "头晕", "头痛",
        "颈椎", "腰酸", "背痛", "失眠", "睡眠", "亚健康",
        # 情绪 / 心理
        "焦虑", "压力", "放松", "心情", "抑郁", "情绪", "紧张", "养心", "心理",
        # 养生 / 调理
        "健康", "养生", "体检", "免疫力", "三高", "血压", "血糖", "饮食",
        "运动", "减肥", "冥想", "瑜伽", "调理", "泡脚", "气血",
        # 人群 / 阶段
        "中年", "40岁", "50岁", "更年期", "退休", "老年",
    ]
    all_items = fetch_all()
    total = sum(len(v) for v in all_items.values())
    print(f"\n=== 共抓到 {total} 条热榜 ===")
    related = filter_related(all_items, KEYWORDS)
    if not related:
        print("本次没有命中选题关键词的热点（属正常：热榜随时变化）。")
        # 展示各平台前 3 条，证明抓取真实生效
        for p, items in all_items.items():
            for it in items[:3]:
                print(f"  [{p}] {it['title']}")
        return
    for p, items in related.items():
        print(f"\n【{p}】命中 {len(items)} 条：")
        for it in items[:5]:
            print(f"  - {it['title']}  ({it.get('url','')})")


if __name__ == "__main__":
    _main()
