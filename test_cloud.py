# -*- coding: utf-8 -*-
"""快速验证云端大模型 API 是否可用（不跑完整流水线，只发一条测试请求）。

用法：
  python test_cloud.py                       # 用默认健康类测试 prompt
  python test_cloud.py "你是谁？"            # 自定义一条 prompt
  HOTBOT_CLOUD_KEY=sk-xxx python test_cloud.py   # 临时用环境变量覆盖 key

配置来源：config.json 的 cloud 字段（api_url / api_key / model）。
"""
import os
import sys
import json
import ssl
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

PLACEHOLDER = ("在此填写", "你的云端", "请替换", "<", "example", "xxx")


def load_cloud():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f).get("cloud", {})
    except Exception:
        cfg = {}
    api_url = os.environ.get("HOTBOT_CLOUD_URL") or cfg.get("api_url") or "https://api.siliconflow.cn/v1/chat/completions"
    api_key = os.environ.get("HOTBOT_CLOUD_KEY") or cfg.get("api_key") or ""
    model = os.environ.get("HOTBOT_CLOUD_MODEL") or cfg.get("model") or ""
    return api_url, api_key, model


def main():
    api_url, api_key, model = load_cloud()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

    if not api_key or any(p in api_key for p in PLACEHOLDER):
        print("=" * 60)
        print("尚未配置云端模型 Key。请先在 config.json 的 cloud.api_key 填入真实 Key，")
        print("或直接用环境变量：HOTBOT_CLOUD_KEY=sk-xxx python test_cloud.py")
        print(f"（当前 api_url={api_url}  model={model or '(未填)'}）")
        print("=" * 60)
        return

    prompt = sys.argv[1] if len(sys.argv) > 1 else \
        "用一句话解释什么是'亚健康'，并给一个缓解疲劳的实用小建议。"

    system_prompt = (os.environ.get("HOTBOT_SYSTEM")
                     or cfg.get("system_prompt")
                     or "")
    gen_params = cfg.get("gen_params") or {"temperature": 0.7, "max_tokens": 400}

    messages = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages}
    payload.update(gen_params)
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    print(f">>> 测试请求：model={model}")
    print(f">>> prompt：{prompt}\n--- 模型返回 ---")
    try:
        with urllib.request.urlopen(req, timeout=90, context=ctx) as r:
            resp = json.loads(r.read().decode("utf-8", "ignore"))
        print(resp["choices"][0]["message"]["content"])
        print("\n[OK] 云端模型调用成功，可接入方案 B 定时自动化。")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")[:300]
        print(f"[HTTP {e.code}] 调用失败：{body}")
    except Exception as e:
        print(f"[ERR] 调用异常：{e}")


if __name__ == "__main__":
    main()
