# -*- coding: utf-8 -*-
"""连通性诊断：从 GitHub Actions 运行环境(美国服务器)测试各端点可达性。
纯标准库，无需任何依赖。run: python3 .github/scripts/conn_test.py
"""
import os
import time
import ssl
import urllib.request
import urllib.error

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# (分组, 名称, URL)
TARGETS = [
    ("采集源·国内平台", "头条热榜", "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"),
    ("采集源·国内平台", "抖音热搜", "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383"),
    ("采集源·国内平台", "百度实时", "https://top.baidu.com/api/board?platform=wise&tab=realtime"),
    ("采集源·国内平台", "微博热搜", "https://weibo.com/ajax/side/hotSearch"),
    ("云端模型", "硅基流动", "https://api.siliconflow.cn/v1/models"),
    ("推送", "钉钉机器人", "https://oapi.dingtalk.com/robot/send"),
    ("基础设施", "Docker Hub", "https://registry-1.docker.io/v2/"),
    ("基础设施", "GitHub", "https://github.com"),
    ("基础设施·参考", "newsnow公共实例", "https://newsnow.busiyi.world/"),
]


def check(name, url):
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            body = r.read()
            code = r.status
        return True, code, len(body), time.time() - t0
    except urllib.error.HTTPError as e:
        # 能拿到 HTTP 响应 = 主机可达（钉钉/Docker Hub 正常也会返回非 200）
        try:
            _ = e.read(80)
        except Exception:
            pass
        return True, e.code, 0, time.time() - t0
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", 0, time.time() - t0


def main():
    print("===== GitHub Actions 连通性诊断（美国服务器）=====")
    rows = []
    ok_count = 0
    for group, name, url in TARGETS:
        ok, code, size, dt = check(name, url)
        if ok:
            ok_count += 1
        rows.append((group, name, ok, code, size, dt))
        tag = "OK  " if ok else "FAIL"
        print(f"[{tag}] {group:14s} {name:14s} code={code}  size={size}B  {dt:.2f}s")
    print(f"\n=== 可达 {ok_count}/{len(TARGETS)} ===")

    summary = [
        "## 连通性诊断结果", "",
        f"可达 **{ok_count}/{len(TARGETS)}**。运行环境：GitHub Actions (ubuntu-latest，美国服务器)。", "",
        "| 分组 | 端点 | 可达 | 状态 | 字节 | 耗时(s) |",
        "|------|------|------|------|------|---------|",
    ]
    for group, name, ok, code, size, dt in rows:
        summary.append(f"| {group} | {name} | {'✅' if ok else '❌'} | {code} | {size} | {dt:.2f} |")
    summary += [
        "",
        "**说明**：钉钉 / Docker Hub 返回非 200 属正常（需带参数 POST / 需鉴权），只要“可达=✅”即证明网络通。",
        "**结论**：若“采集源·国内平台”全部 ❌，说明美国服务器抓不到国内热榜，应改用本机定时或国内云；"
        "若 ✅，则 GitHub Actions 全自动方案可行。",
    ]
    text = "\n".join(summary)
    # 写文件供 artifact 下载（便于在沙箱取回结果）
    with open("connectivity-result.md", "w", encoding="utf-8") as f:
        f.write(text + "\n")
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
