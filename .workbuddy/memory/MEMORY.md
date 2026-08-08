# 项目长期笔记：公众号自动化热点追踪

## 目标
围绕"中年人浑身不得劲"做公众号爆款：每日追踪 头条/抖音/快手/公众号 等平台热点 → 关键词筛选 → 本地大模型成文 → 定时推送。

## 数据源：TrendRadar（无 API Key）
- 模块：`trendradar.py`（标准库 urllib，多平台公开热榜，单平台失败自动跳过）。
- 平台实测可达性（2026-08-07，本沙箱）：
  - ✅ 头条 `https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc` → `data[].{Title,Url,HotValue}`
  - ✅ 抖音 `https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383` → `data.word_list[].word`（偶发反爬，重试/加 cookie）
  - ✅ 百度 `https://top.baidu.com/api/board?platform=wise&tab=realtime` → 嵌套 `data.cards[].content[].content[].{word,url,hotScore}`
  - ⚠️ 微博/知乎/B站：本沙箱 403/401，需登录 cookie；用户 Windows 本机有登录态通常可通
  - ❌ 快手：需 graphql POST + cookie，暂未实现
- 注：GitHub 在本沙箱不可达（000），无法 clone 官方 TrendRadar 仓库，故自建等价实现。
- **沙箱 pip 装包失败**（pypi.org 超时），所有脚本一律用标准库（urllib），不要依赖 requests。

## 本地大模型（LM Studio）
- 地址：`http://127.0.0.1:1234`，OpenAI 兼容：`/v1/chat/completions`、`/v1/models`。
- 调用时 model 字段用 `"local-model"` 即可路由到当前加载模型（已验证：qwen3vl-8b-instruct、qwen3.5-4b、gemma-4 系列等）。
- 用 stdlib urllib 发 POST，超时设 120s（1500 字文章生成可能需要几十秒）。

## 流水线
- `hotbot.py`：数据源 `HOTBOT_SOURCE`=trendradar(默认)/tophub/mock；`HOTBOT_LLM_MOCK=1` 模拟文章；`HOTBOT_MOCK=1` 全离线。
- 本沙箱跑通：149 条真实热榜 → 关键词 0 命中（今日无健康热点，正常）。

## 待办 / 下一步
- (C) 建每日 7:30 定时自动化，自动跑趋势追踪+成文并推送。
- 用户本机验证：头条/抖音/百度/微博/知乎/B站 实际可达性（带 cookie）。
- 可选：补 快手 解析（graphql + cookie）。
