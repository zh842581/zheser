# -*- coding: utf-8 -*-
"""
hotbot.py —— 公众号"健康管理"热点追踪与自动成文
================================================
两种模型来源（HOTBOT_MODEL_MODE / config.json.model_mode，默认 local）：
  - local : 调用你本机部署的模型（默认 http://127.0.0.1:1234 ，需本机开机）
  - cloud : 调用云端开源模型 API（在 config.json.cloud 填 url/key/model，无需本机开机）

数据源（HOTBOT_SOURCE / config.json.source，默认 trendradar）：
  - trendradar : 各平台公开热榜，无需 API Key
  - tophub     : tophub.today 聚合 API（需填 tophub_key）
  - mock       : 内置模拟数据，完全离线

文章验证：HOTBOT_LLM_MOCK=1 用模拟文章（用于无模型时验证流程）。

外部简报（双管齐下）：设置 BRIEFING_FILE=路径，可将 TrendRadar 等简报
（markdown 链接 [标题](url) 或纯文本每行一条）抽取的候选热点，合并进选题池，
与自研采集合并后一起过关键词漏斗、一起成文。

微信推送：由 wechat_push.py 负责，读取 config.json.wechat 或环境变量；
          未配置则跳过（不影响主流程）。

依赖：纯标准库。本机双击 run_local.bat 即以 local 模式运行。
"""

import os
import time
import json
import ssl
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
OUTPUT_DIR = os.path.join(HERE, "output")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


# ----------------------------- 加载配置 -----------------------------
def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


CFG = load_config()

MODEL_MODE = (os.environ.get("HOTBOT_MODEL_MODE") or CFG.get("model_mode", "local")).lower()
SOURCE = os.environ.get("HOTBOT_SOURCE") or CFG.get("source", "trendradar")
LLM_MOCK = (os.environ.get("HOTBOT_LLM_MOCK") == "1") or bool(CFG.get("llm_mock", False))
TOPHUB_API_KEY = os.environ.get("TOPHUB_API_KEY") or CFG.get("tophub_key", "")

LOCAL_URL = (os.environ.get("HOTBOT_LOCAL_URL")
             or CFG.get("local", {}).get("api_url")
             or "http://127.0.0.1:1234/v1/chat/completions")
LOCAL_MODEL = (os.environ.get("HOTBOT_MODEL")
               or CFG.get("local", {}).get("model", "local-model"))

CLOUD_URL = os.environ.get("CLOUD_LLM_API_URL") or CFG.get("cloud", {}).get("api_url", "")
CLOUD_KEY = os.environ.get("CLOUD_LLM_API_KEY") or CFG.get("cloud", {}).get("api_key", "")
CLOUD_MODEL = os.environ.get("CLOUD_LLM_MODEL") or CFG.get("cloud", {}).get("model", "")

SYSTEM_PROMPT = (os.environ.get("HOTBOT_SYSTEM") or CFG.get("system_prompt") or "").strip()
# 采样参数（硅基流动/本地 OpenAI 兼容接口通用；repetition_penalty 即"repeat penalty"）
GEN_PARAMS = CFG.get("gen_params") or {
    "temperature": 0.8, "top_p": 1.0, "top_k": 40,
    "repetition_penalty": 1.05, "presence_penalty": 0.0, "min_p": 0.0, "max_tokens": 2000,
}

KEYWORDS = CFG.get("keywords") or [
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

ARTICLE_PROMPT = """根据热点“{title}”，写一篇关于中年人健康管理的公众号文章。
文章要围绕“身体不舒服、缓解疲劳、放松心情”等健康主题，引发中年读者共鸣。
要求：
- 给出 3 个标题，其中至少 1 个包含“浑身不得劲”；
- 全文口语化、有共情，像朋友唠嗑；
- 用热点自然引入，通俗解释背后的身体/心理原因，可以顺带聊点实在的调理思路，但别写成教条。
"""


# ----------------------------- 数据源：trendradar -----------------------------
def get_items():
    if SOURCE == "tophub":
        return _tophub_items_by_platform()
    if SOURCE == "mock":
        return _mock_items_by_platform()
    import trendradar  # 默认 trendradar
    return trendradar.fetch_all()


# ----------------------------- 数据源：tophub -----------------------------
def fetch_hot_tophub(channel_code):
    url = f"https://api.tophub.today/v1/GetHotNews?apikey={TOPHUB_API_KEY}&p={channel_code}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as r:
            resp = json.loads(r.read().decode("utf-8", "ignore"))
        if resp.get("code") == 0:
            return resp.get("Data", [])
        print(f"获取{channel_code}失败：{resp.get('msg')}")
        return []
    except Exception as e:
        print(f"请求{channel_code}出错：{e}")
        return []


def _tophub_items_by_platform():
    CHANNELS = {"头条": "Toutiao", "抖音": "Douyin", "快手": "Kwai", "公众号": "Wechat"}
    out = {}
    for name, code in CHANNELS.items():
        print(f"正在获取【{name}】热榜(tophub)...")
        items = fetch_hot_tophub(code)
        out[name] = [{"title": it.get("Title", ""), "url": it.get("Url", ""), "heat": None} for it in items]
        print(f"  {name} 抓到 {len(out[name])} 条")
        time.sleep(1)
    return out


# ----------------------------- 数据源：mock -----------------------------
def _mock_items_by_platform():
    return {
        "头条": [{"title": "40岁后突然浑身没劲？医生提醒：别把累当小事", "url": "https://mock.toutiao/1", "heat": None},
                 {"title": "女子连续加班后猝死，生前总说只是有点累", "url": "https://mock.toutiao/2", "heat": None}],
        "抖音": [{"title": "中年男人的硬撑：体检报告不敢看", "url": "https://mock.douyin/1", "heat": None},
                 {"title": "长期失眠的人后来都怎么样了", "url": "https://mock.douyin/2", "heat": None}],
        "快手": [{"title": "辅导作业气到浑身酸痛？宝妈真实记录", "url": "https://mock.kuaishou/1", "heat": None}],
        "公众号": [{"title": "亚健康不是矫情：浑身不得劲的 5 个信号", "url": "https://mock.wechat/1", "heat": None},
                   {"title": "三高人群饮食红黑榜，收藏这一篇就够了", "url": "https://mock.wechat/2", "heat": None}],
    }


# ----------------------------- 外部简报（双管齐下：吸收 TrendRadar 等简报） -----------------------------
def load_briefing(path):
    """从外部简报文件抽取候选热点，用于和自研采集合并。
    支持：1) Markdown 链接 [标题](url)（TrendRadar 简报常用）；2) 纯文本每行一条标题。
    返回 [{"title":..., "url":..., "heat":None}, ...]
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as e:
        print(f"[简报] 读取失败：{e}")
        return []
    import re
    items, seen = [], set()
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        title, url = m.group(1).strip(), m.group(2).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        items.append({"title": title, "url": url, "heat": None})
    if not items:  # 退化：按行抽取标题
        for line in text.splitlines():
            line = line.strip().lstrip("-*#").strip()
            if line and len(line) >= 4 and line not in seen:
                seen.add(line)
                items.append({"title": line, "url": "", "heat": None})
    print(f"[简报] 从 {path} 抽取 {len(items)} 条候选")
    return items


# ----------------------------- 关键词漏斗 -----------------------------
def filter_related(items_by_platform):
    out = {}
    for platform, items in items_by_platform.items():
        hit = [it for it in items if any(kw in (it.get("title") or "") for kw in KEYWORDS)]
        if hit:
            out[platform] = hit
    return out


# ----------------------------- 文章生成 -----------------------------
def call_llm(prompt):
    if LLM_MOCK:
        return _mock_article(prompt)
    if MODEL_MODE == "cloud":
        if not CLOUD_URL or not CLOUD_KEY:
            return "（未配置云端模型：请在 config.json.cloud 填 api_url / api_key / model）"
        url = CLOUD_URL
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CLOUD_KEY}"}
        model = CLOUD_MODEL or "default"
    else:
        url = LOCAL_URL
        headers = {"Content-Type": "application/json"}
        model = LOCAL_MODEL

    data = {
        "model": model,
        "messages": ([{"role": "system", "content": SYSTEM_PROMPT}] if SYSTEM_PROMPT else [])
                     + [{"role": "user", "content": prompt}],
    }
    data.update(GEN_PARAMS)  # 注入 temperature/top_p/top_k/repetition_penalty/presence_penalty/min_p/max_tokens
    req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"),
                                 headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        return j["choices"][0]["message"]["content"]
    except Exception as e:
        return f"大模型调用异常：{e}"


def _mock_article(prompt):
    return (
        "【以下为 MOCK 模拟文章，未调用真实模型】\n\n"
        f"> 使用的 Prompt：\n> {prompt.strip()}\n\n"
        "标题候选：\n"
        "1. 中年以后，突然发现自己浑身不得劲，很可能和这件事有关\n"
        "2. 40岁后总感觉累？不是矫情，是身体在报警\n"
        "3. 别硬撑了：那些“浑身没劲”的中年人，后来都怎样了\n\n"
        "（正文示例约 1500 字，基于热点自然引入 + 通俗病理解释 + 共情叙事……）\n\n"
        "实用建议：\n1. 规律午睡 20 分钟，给身体“充电”；\n"
        "2. 每年做一次深度体检，别等不舒服才去；\n"
        "3. 把“硬撑”换成“说出来”，运动 + 倾诉双管齐下。\n\n"
        "互动引导：你最近一次“浑身不得劲”是什么时候？评论区聊聊。"
    )


# ----------------------------- 微信推送 -----------------------------
def notify_wechat(title, content):
    try:
        from wechat_push import push_wechat
        return push_wechat(title, content)
    except Exception as e:
        print(f"[微信推送] 模块加载失败：{e}")
        return False


# ----------------------------- 主流程 -----------------------------
def main():
    print(f"===== 开始（数据源={SOURCE}，模型={MODEL_MODE}{' 模拟' if LLM_MOCK else ''}）=====")
    briefing_path = os.environ.get("BRIEFING_FILE")
    b_items = []
    if briefing_path and os.path.exists(briefing_path):
        b_items = load_briefing(briefing_path)
    if b_items:
        # 串接成文模式：优先用真正 TrendRadar 抓取的热点，不再重复自建抓取
        all_items = {"TrendRadar": b_items}
        print(f"===== 使用 TrendRadar 简报作为采集源（{len(b_items)} 条，已跳过自建抓取）=====")
    else:
        # 兜底：TrendRadar 无产出时回退自建采集
        all_items = get_items()
    total = sum(len(v) for v in all_items.values())
    print(f"=== 共抓到 {total} 条热榜 ===")

    related = filter_related(all_items)

    if not related:
        print("本次没有命中选题关键词的热点（属正常：热榜随时变化）。")
        lines = [f"=== 健康管理 追踪简报 {time.strftime('%Y-%m-%d %H:%M')}（数据源={SOURCE}）===\n",
                 "今日无命中健康类关键词的热点。各平台热榜前 3：\n"]
        for p, items in all_items.items():
            lines.append(f"\n【{p}】")
            for it in items[:3]:
                lines.append(f"  - {it.get('title', '')}")
        _save(lines)
        notify_wechat("【公众号追踪】今日无健康类热点",
                      "今日各平台热榜未出现健康管理类选题，已记录追踪简报。明天继续。")
        return

    lines = [f"=== 健康管理 选题报告 {time.strftime('%Y-%m-%d %H:%M')}（数据源={SOURCE}）===\n"]
    for platform, hot_list in related.items():
        lines.append(f"\n【{platform}平台热点】")
        for idx, item in enumerate(hot_list[:5], 1):
            lines.append(f"{idx}. {item.get('title', '')}\n   链接：{item.get('url', '')}")

    first_hot = next(iter(related.values()))[0]
    prompt = ARTICLE_PROMPT.format(title=first_hot.get("title"))
    print("正在让大模型生成文章...")
    article = call_llm(prompt)
    lines.append("\n\n========== AI生成示例文章 ==========\n")
    lines.append(article)
    _save(lines)
    notify_wechat(f"【公众号选题】{first_hot.get('title', '')}", article)


def _save(lines):
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    filename = os.path.join(OUTPUT_DIR, f"report_{time.strftime('%Y%m%d_%H%M')}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n报告已生成：{filename}")
    return filename


if __name__ == "__main__":
    main()
