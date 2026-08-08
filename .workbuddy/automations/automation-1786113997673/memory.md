# 自动化执行记录：公众号健康热点-每日云端出稿推送

## 2026-08-08 09:53 (GMT+8) 执行
- 模式：HOTBOT_MODEL_MODE=cloud，脚本 hotbot.py，隔离 Python 3.13.12。
- 热榜抓取：trendradar 共 149 条（头条 50、抖音 48、百度 51；微博/知乎/B站 403/401 失败，沙箱无登录态）。
- 选题命中：3 条（头条「睡眠地图背后藏着的经济账」「中医教你一招提升气血」、百度「23岁博士确诊胃癌晚期：常熬夜压力大」）。
- 文章生成：❌ 失败——config.json.cloud.api_key 为空，call_llm 返回「未配置云端模型」。
- 微信推送：❌ 跳过——config.wechat 模式为 dingtalk，但 webhook 为空，「dingtalk 模式缺少 webhook」。
- 产出文件：output/report_20260808_0953.txt（选题报告 + 未配置提示）。

## ⚠️ 关键问题（需用户处理）
- 实际项目里**不存在 config.json**，仅有 config.example.json 模板（credentials 全空）。
- 本次按模板创建了 config.json，但用户所说的「API Key / token 已写入」并未落实。
- 用户必须填写：config.json.cloud.api_key、config.json.wechat.(webhook+secret 或 token/uids)。

## 待办
- 用户填好 config.json 的 cloud / wechat 字段后，下次自动化即可真正出稿并推送。
