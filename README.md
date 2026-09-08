# zj-jxjy-study — 浙江会计继续教育自动刷课（Skill）

> 🎯 在 WorkBuddy 对话里说一句"装个 zj-jxjy-study"，AI 就能自动帮你登录学习中心、播放视频、跳过已学完课程、累计学分、维护看板。

[![Skill 版本](https://img.shields.io/badge/version-1.0.0-blue)]()
[![平台](https://img.shields.io/badge/平台-WorkBuddy%20Desktop-purple)]()
[![适配](https://img.shields.io/badge/适配-浙江%2F正保网校-green)]()

---

## 目录

- [这是什么](#这是什么)
- [核心特性](#核心特性)
- [适用人群](#适用人群)
- [快速上手](#快速上手-3-步)
- [详细安装步骤](#详细安装步骤)
- [配置说明](#配置说明)
- [使用示例](#使用示例)
- [看板截图说明](#看板截图说明)
- [自动化与跨夜运行](#自动化与跨夜运行)
- [常见问题](#常见问题)
- [文件清单](#文件清单)
- [免责声明](#免责声明)

---

## 这是什么

`zj-jxjy-study` 是一个 **WorkBuddy Skill（技能）**，专门用于浙江会计继续教育（正保网校 chinaacc）的自动学习。安装后你只需要对 AI 说一句话，剩下的它帮你搞定：

| 你说一句 | AI 做什么 |
|---------|----------|
| "继续教育开始" | 启动刷课任务，每天定时运行 |
| "继续教育开始到 22:00" | 临时跑一次性任务 |
| "现在学到多少了" | 读学分总览 / 看课程清单 |
| "继续教育远程扫码登录" | 截浙里办二维码 + SMTP 发邮件到手机 |
| "继续教育当前邮箱配置是啥" | 显示 jxjy_mail_config.json |

## 核心特性

✅ **自动登录** —— 首次扫码后保存登录态，隔夜失效自动提示重新扫码  
✅ **自动跳过已学完课程** —— 基于"完成学习 / 学分已满 / 剩余时长 0"三重判断  
✅ **跨夜长跑** —— 默认每天 9:00 起跑 15 小时到次日 0:00，支持任意小时数  
✅ **远程扫码登录** —— 不在电脑前也能用手机扫浙里办二维码登录（SMTP 邮件推送）  
✅ **独立看板** —— 显示已学 / 待学 / 即将学分数 + 课程清单  
✅ **多通道配置** —— QQ / 163 / Gmail 邮箱均可作为二维码接收方  
✅ **脱敏模板** —— skill 不含任何账号/授权码信息，可安全公开分享  

## 适用人群

- 浙江（含杭州、宁波、温州等）的会计/税务从业人员，每年需完成 90 学分继续教育
- 工作日挤不出时间手动刷视频、又不想拖到过期
- 已经在用 WorkBuddy Desktop，希望 AI 接管日常运维任务

> ⚠️ **不适用**：其他省份（江苏/上海/广东等）继续教育入口和学分要求不同；非正保网校平台；非继续教育类课程。

---

## 快速上手（3 步）

### 第 1 步：安装 Skill

在 WorkBuddy Desktop 对话框里说一句：

```
装个 zj-jxjy-study
```

AI 会自动从 BuiltinMarket 搜索、安装到 `~/.workbuddy/skills/zj-jxjy-study/`。

### 第 2 步：配置邮箱 + 登录态

1. 在你的项目 `.workbuddy/jxjy_mail_config.json` 填入 SMTP 配置（参考 [配置说明](#配置说明)）
2. 启动 `jxjy_remote_login.py --wait 15`，扫描邮件里的二维码完成首次登录

### 第 3 步：开刷

```
继续教育开始
```

AI 会启动脚本，每天 9:00 自动运行 15 小时。

---

## 详细安装步骤

### 方式一：WorkBuddy 市场安装（推荐）

```
装个 zj-jxjy-study
```

按提示确认安装即可。安装位置：`C:\Users\<你的用户名>\.workbuddy\skills\zj-jxjy-study\`

### 方式二：手动安装

1. 下载本仓库（`SKILL.md` + `scripts/` 目录）
2. 复制 `SKILL.md` 到 `C:\Users\<你的用户名>\.workbuddy\skills\zj-jxjy-study\SKILL.md`
3. 把 `scripts/` 下的 6 个 `.py` 文件复制到你项目的 `.workbuddy/` 目录（⚠️ 必须放这里，脚本按自身所在目录读写 `jxjy_state.json` 等状态文件）
4. 重启 WorkBuddy Desktop

### 方式三：项目级安装（团队共享）

1. 把 SKILL.md 复制到项目的 `.workbuddy/skills/zj-jxjy-study/SKILL.md`
2. 把 `scripts/` 下的 6 个 `.py` 复制到项目的 `.workbuddy/` 目录
3. ⚠️ 注意：项目级 skill 对所有项目成员可见，**不要带个人邮箱/账号配置**

---

## 配置说明

### 1. 邮箱 SMTP 配置（`jxjy_mail_config.json`）

放在你项目的 `.workbuddy/jxjy_mail_config.json`（不存在则创建）：

```json
{
  "from_addr": "<你的发件邮箱，例如 123456@qq.com>",
  "pass": "<你的SMTP授权码，不是登录密码>",
  "to_addr": "<收件邮箱，建议与发件邮箱一致>",
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465
}
```

**SMTP 服务商参考**：

| 服务商 | smtp_host | 端口 | 加密 | 密码类型 |
|--------|-----------|------|------|----------|
| QQ 邮箱 | smtp.qq.com | 465 | SSL | 授权码（非登录密码）|
| 163 邮箱 | smtp.163.com | 465 | SSL | 授权码 |
| Gmail | smtp.gmail.com | 587 | STARTTLS | 应用专用密码 |
| Outlook | smtp.office365.com | 587 | STARTTLS | 应用密码 |

> 💡 **如何获取 QQ 邮箱授权码**：登录 QQ 邮箱网页版 → 设置 → 账户 → POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务 → 开启"POP3/SMTP服务"或"IMAP/SMTP服务" → 按提示短信验证 → 复制 16 位授权码。

### 2. 浙里办 SSO 登录态（`jxjy_state.json`）

首次运行需要登录一次：

```bash
cd "<你的项目>/.workbuddy"
python jxjy_remote_login.py --wait 15
```

或电脑旁人工登录：

```bash
python jxjy_login_window.py --wait 10
```

成功后会在 `.workbuddy/jxjy_state.json` 保存登录态（含 SSO_TOKEN + 正保 chinaacc cookie，约 40+ 条）。

---

## 使用示例

### 启动刷课

```
继续教育开始
```

AI 启动刷课任务（默认 15 小时）。可选临时参数：

```
继续教育开始到 22:00   # 跑到晚上 10 点
继续教育开始 8 小时    # 跑 8 小时
```

### 查询学分进度

```
现在继续教育学到多少了
继续教育看板
```

AI 会读取 `jxjy_dashboard_data.json` 并刷新看板 HTML。

### 远程扫码登录

```
继续教育远程扫码登录
```

AI 启动 `jxjy_remote_login.py`，每 45 秒截浙里办二维码发到你邮箱。手机邮件 App 收图 → 保存到相册 → 浙里办/支付宝/微信"扫一扫 → 从相册选图"完成登录。

### 重置邮箱配置

```
继续教育邮箱重置成 123456@163.com，授权码 ABCD1234EFGH5678
继续教育邮箱授权码过期了，新的是 XYZ123
继续教育 SMTP 改成 163，邮箱 123456@163.com，授权码 ABCD1234
```

AI 会先备份 `jxjy_mail_config.json` 为 `.bak`，再写入新配置。

---

## 看板截图说明

> 📸 **本 README 不含图片，避免敏感信息外泄**。以下文字说明在哪些场景需要截图，可用于小红书笔记或文档：

### 截图 1：综合看板 → 继续教育卡片

- **位置**：项目根目录 `综合看板.html`
- **时机**：刷课进行中打开
- **建议区域**：右下角"继续教育自动刷课"卡片，含学分数 + 进度条
- **截图前**：打码掉任何可能泄露账号的字段（账号名、邮箱等）

### 截图 2：独立继续教育看板

- **位置**：项目根目录 `继续教育看板.html`
- **建议区域**：顶部"已学习 / 待学习 / 即将学习"三栏
- **亮点**：三色进度条 + 学分数字

### 截图 3：学分对比

- **位置**：自己截图编辑（PS/Canva）
- **内容**：左侧"手动刷课前 0/90 学分"，右侧"AI 跑 1 周后 30+/90 学分"

### 截图 4：远程扫码邮件

- **位置**：你的 QQ 邮箱 → 主题"继续教育自动刷课 - 远程扫码登录"
- **截图前**：打码掉发件人邮箱 + 授权码相关字段

---

## 自动化与跨夜运行

### 创建自动化任务

AI 默认会创建**每天 9:00 启动、运行 15 小时**的自动化任务（次日 0:00 结束）。

修改方式：

```
把继续教育自动化改成每天 10 点启动，跑 12 小时
```

### 跨夜小贴士

- ⚠️ **建议电脑不休眠也不关机**：跨夜关机 → 第二天重启会从该课开头重新捡起
- Windows 默认"按电源键 → 休眠"即可：省电 + 不杀进程
- 必须真关机时：先说"暂停继续教育自动化任务"，恢复时说"恢复"

### 暂停 / 恢复自动化

```
暂停继续教育自动化
恢复继续教育自动化
```

---

## 多账号扩展（未来规划）

> ⚠️ **本节为未实现规划**。当前 skill 仅支持单账号。

### 适用场景

- 本人多个继续教育账号（主 + 备用）
- 同事/家人委托代刷（多人共用同一台电脑）

### 不建议现在做

- **平台风控**：正保网校同 IP 短时间开多账号易触发"批量账号"风控
- **资源占用**：每 Chrome 实例 300–500MB，3 账号 ≈ 1.5GB 内存
- **登录混淆**：多账号同时扫码，邮件里多张二维码易混淆
- **会中断当前刷课**

### 改造方案（待实施）

```
.workbuddy/
├── jxjy_state_<account>.json
├── jxjy_dashboard_data_<account>.json
├── jxjy_courses_<account>.json
├── jxjy_mail_config_<account>.json    # 每账号独立邮箱
└── jxjy_study_<account>.log
```

```bash
python jxjy_daily_study.py 900 --account <account_id>
python jxjy_remote_login.py --wait 15 --account <account_id>
```

每个账号一个 automation 任务，`rrule` 同：`FREQ=DAILY;BYHOUR=9;BYMINUTE=0`，prompt 里指定 `--account`。

### 风控对策

1. 错峰启动（间隔 5–10 分钟）
2. 同时间最多 2 个账号在线播放
3. 3+ 账号建议换 IP
4. 新账号头一周每天手动检查无异常登录提醒

### 用户指令示例（待实现）

```
加一个新账号 zhangsan，用他手机 13800138000 当 ID
3 个账号一起刷，每个错峰 10 分钟
暂停 zhangsan 的刷课
现在 zhangsan 账号学到哪了
```

更多细节见 `SKILL.md`「多账号扩展」章节。

---

## 常见问题

### Q1：登录态隔夜失效怎么办？

A：SSO_TOKEN 有效期短（通常 12-24 小时），隔夜后会自动被踢到登录页。说一句"继续教育远程扫码登录"即可重新扫码。

### Q2：视频播放但学分不涨？

A：多半是卡在已学完课程。检查 `jxjy_study.log` 是否每 20 秒推进 `current=` 时间。修复后脚本会自动跳过"完成学习/学分已满/剩余时长 0"的课程。

### Q3：能不装 SMTP 直接用吗？

A：可以。远程扫码登录会退回到"电脑旁人工登录"模式，需要人守在电脑前用短信/扫码完成登录。

### Q4：能换成其他省份吗？

A：skill 里的入口 URL 是浙江政务服务网 + 正保网校。其他省份（江苏会计学会、广东会计网等）的入口和学分要求不同，需要单独适配。

### Q5：脚本会偷我账号吗？

A：本 skill 完全开源，所有脚本都在你的本机 `.workbuddy/` 目录。脚本只做两件事：登录和播放视频，不会主动外发任何数据。邮箱配置也只用于发二维码到你自己的收件箱。

---

## 文件清单

### 本仓库文件

```
zj-jxjy-study/
├── README.md           # 本文件
├── SKILL.md            # WorkBuddy Skill 定义（不含个人配置）
└── scripts/            # 配套 Python 脚本（复制到项目 .workbuddy/ 使用）
    ├── jxjy_daily_study.py         # 刷课主脚本
    ├── jxjy_remote_login.py        # 远程扫码登录（SMTP 邮件推送）
    ├── jxjy_login_window.py        # 电脑旁人工登录
    ├── jxjy_dashboard_updater.py   # 综合看板刷新
    ├── jxjy_kanban_updater.py      # 独立看板刷新
    └── refresh_jxjy_after_session.py  # 刷课后抓取学分面板
```

### 安装后会在你项目里出现

```
<你的项目>/
├── .workbuddy/
│   ├── jxjy_daily_study.py         # 刷课主脚本（你需自己拷贝或自行部署）
│   ├── jxjy_remote_login.py        # 远程扫码登录
│   ├── jxjy_login_window.py        # 电脑旁人工登录
│   ├── jxjy_mail_config.json       # SMTP 配置（你自己填）
│   ├── jxjy_state.json             # 登录态（运行后自动生成）
│   ├── jxjy_study.log              # 刷课日志
│   ├── jxjy_study_report.json      # 每次跑完的报表
│   ├── jxjy_dashboard_data.json    # 学分数据
│   ├── jxjy_courses.json           # 课程清单
│   ├── jxjy_dashboard_updater.py   # 看板刷新
│   └── jxjy_kanban_updater.py      # 独立看板刷新
├── 综合看板.html                    # 你的综合看板（按你项目结构放）
└── 继续教育看板.html                # 独立继续教育看板
```

> 📌 **注**：本仓库只包含 Skill 定义（`SKILL.md`）和说明文档（`README.md`）。具体 Python 脚本需从你原项目复制，或由 AI 智能体根据 SKILL.md 自动生成。

---

## 免责声明

本 Skill 仅用于**个人继续教育学习进度管理与自动化**。使用时请遵守：

1. **不替代真实学习**：本工具帮助你完成继续教育平台上的视频学习时长，不构成代考、代学、代刷。任何平台禁止的行为（如虚假学习、批量账号等）本 skill 概不涉及。
2. **遵守继续教育管理规定**：浙江会计继续教育要求学员真实学习，请在使用本 skill 时确保视频正常播放、弹窗正常处理，不要人为干扰学习过程。
3. **数据安全**：本 skill 不上传任何账号/学习数据到第三方服务器。所有配置与登录态都保存在你的本机。分享 skill 时请脱敏（仓库 SKILL.md 已默认脱敏）。
4. **平台变更风险**：浙江继续教育平台（jxjy.czt.zj.gov.cn）或正保网校（chinaacc.com）的入口 URL、登录方式、学分计算规则可能变更。本 skill 配套脚本可能需要同步更新。如发现脚本失效，请反馈 issue。

---

## 反馈与贡献

- 提交 Issue：[GitHub Issues]
- 邮件联系：见仓库说明

## 许可证

MIT License