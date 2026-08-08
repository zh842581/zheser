# -*- coding: utf-8 -*-
"""消息推送模块（纯标准库，无需任何第三方依赖）。

支持五种服务（均无需自建云空间，注册/建群即得的免费服务）：
  - serverchan : Server酱  https://sct.ftqq.com/        (SendKey，推到微信，免费版仅显示标题)
  - pushplus   : PushPlus  https://www.pushplus.plus/    (token，推到微信，支持完整 markdown 长文)
  - wxpusher   : WxPusher  https://wxpusher.zjiecode.com/ (appToken + uids，推到微信)
  - feishu     : 飞书群机器人  https://open.feishu.cn/    (webhook，免费，完整 markdown 卡片)
  - dingtalk   : 钉钉群机器人  https://oapi.dingtalk.com/ (webhook，免费，完整 markdown)

配置来源（优先级：环境变量 > config.json.wechat）：
  WECHAT_MODE   / config.wechat.mode
  WECHAT_TOKEN  / config.wechat.token     （serverchan / pushplus / wxpusher 用）
  WECHAT_UIDS   / config.wechat.uids      （仅 wxpusher 需要，多个用逗号分隔）
  WECHAT_WEBHOOK/ config.wechat.webhook   （feishu / dingtalk 用）
  WECHAT_SECRET / config.wechat.secret    （feishu / dingtalk 加签用，可选）

未配置时 push_wechat() 仅打印警告并返回 False，不影响主流程。
"""
import os
import json
import ssl
import time
import hmac
import hashlib
import base64
import urllib.request
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "config.json")

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def _conf():
    env_mode = os.environ.get("WECHAT_MODE")
    env_token = os.environ.get("WECHAT_TOKEN")
    env_uids = os.environ.get("WECHAT_UIDS")
    env_webhook = os.environ.get("WECHAT_WEBHOOK")
    env_secret = os.environ.get("WECHAT_SECRET")
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f).get("wechat", {})
    except Exception:
        cfg = {}
    return (
        (env_mode or cfg.get("mode") or ""),
        (env_token or cfg.get("token") or ""),
        (env_uids or cfg.get("uids") or ""),
        (env_webhook or cfg.get("webhook") or ""),
        (env_secret or cfg.get("secret") or ""),
    )


def _feishu_sign(secret):
    """飞书加签：HMAC-SHA256(timestamp + '\n' + secret) -> base64。"""
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


def _dingtalk_sign(secret):
    """钉钉加签：HMAC-SHA256(timestamp + '\n' + secret) -> base64，timestamp 为毫秒。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    sign = base64.b64encode(hmac_code).decode("utf-8")
    return timestamp, sign


def _post(url, payload, is_json=True):
    data = json.dumps(payload).encode("utf-8") if is_json else urllib.parse.urlencode(payload).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"} if is_json else \
        {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return r.read().decode("utf-8", "ignore")


def _ok(resp):
    """通用返回码校验：解析各平台返回的 JSON，errcode/code 非预期即视为失败。
    无法解析（纯文本响应）时保守返回 True，保持原行为。"""
    try:
        d = json.loads(resp)
    except Exception:
        return True
    if isinstance(d, dict):
        if d.get("errcode", 0) != 0:
            return False
        code = d.get("code")
        if code is not None and code not in (0, 200, 1000):
            return False
        if d.get("success") is False:
            return False
    return True


def push_wechat(title, content, max_len=2000):
    """推送一条消息。成功返回 True，未配置/失败返回 False。"""
    mode, token, uids, webhook, secret = _conf()
    if not mode:
        print("[推送] 未配置 WECHAT_MODE（或 config.json.wechat.mode），跳过推送。")
        return False
    mode = mode.lower()

    # 内容过长截断，提示看本地完整报告
    if len(content) > max_len:
        content = content[:max_len] + "\n\n…（内容过长已截断，完整版见本地报告文件 output/）"

    try:
        if mode == "serverchan":
            if not token:
                print("[推送] serverchan 模式缺少 token"); return False
            url = f"https://sctapi.ftqq.com/{token}.send"
            data = urllib.parse.urlencode({"title": title, "desp": content}).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                resp = r.read().decode("utf-8", "ignore")

        elif mode == "pushplus":
            if not token:
                print("[推送] pushplus 模式缺少 token"); return False
            payload = {"token": token, "title": title, "content": content, "template": "markdown"}
            resp = _post("https://www.pushplus.plus/send", payload)

        elif mode == "wxpusher":
            if not token:
                print("[推送] wxpusher 模式缺少 token"); return False
            payload = {
                "appToken": token,
                "content": content,
                "summary": title,
                "contentType": 2,  # 2 = markdown
                "uids": [u.strip() for u in uids.split(",") if u.strip()] if uids else [],
            }
            resp = _post("https://wxpusher.zjiecode.com/api/send/message", payload)

        elif mode == "feishu":
            if not webhook:
                print("[推送] feishu 模式缺少 webhook（config.wechat.webhook）"); return False
            card = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": title[:50]},
                        "template": "blue",
                    },
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
                },
            }
            if secret:
                ts, sign = _feishu_sign(secret)
                card["timestamp"] = ts
                card["sign"] = sign
            resp = _post(webhook, card)

        elif mode == "dingtalk":
            if not webhook:
                print("[推送] dingtalk 模式缺少 webhook（config.wechat.webhook）"); return False
            url = webhook
            if secret:
                ts, sign = _dingtalk_sign(secret)
                url = f"{webhook}&timestamp={ts}&sign={urllib.parse.quote(sign)}"
            payload = {"msgtype": "markdown", "markdown": {"title": title[:50], "text": content}}
            resp = _post(url, payload)

        else:
            print(f"[推送] 未知模式: {mode}（支持 serverchan / pushplus / wxpusher / feishu / dingtalk）")
            return False

        print(f"[推送] {mode} 返回: {resp[:200]}")
        return _ok(resp)
    except Exception as e:
        print(f"[推送] 发送失败: {e}")
        return False


if __name__ == "__main__":
    # 自测：配置好后在终端跑 `python wechat_push.py` 即可收到一条测试消息
    push_wechat("测试推送", "如果你收到这条消息，说明推送已配置成功。\n- 支持飞书 / 钉钉 / Server酱 / PushPlus / WxPusher")
