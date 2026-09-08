---
name: zj-jxjy-study
display_name: 浙江会计继续教育自动刷课
display_name_en: Zhejiang Accounting CPE Auto-Study
description: 浙江会计继续教育自动刷课（学分管理 / 浙里办 SSO / 正保网校 chinaacc / 90 学分）。用于每日自动登录学习中心、播放视频、跳过已学完课程、判断学分累计、刷新看板数据；登录态隔夜失效时自动触发远程扫码登录（SMTP 邮件推送二维码）。触发词：继续教育、会计继续教育、浙里办学习中心、正保网校、自动刷课、刷学分、学分没动、视频不播放、远程扫码登录、登录态过期、继续教育看板。
description_zh: 面向浙江会计从业者的继续教育自动刷课技能：自动登录浙里办 SSO 与正保网校、播放视频并跳过已学完课程、累计学分、刷新看板；登录态过期时通过 SMTP 邮件推送二维码远程扫码登录。
description_en: Auto-study skill for Zhejiang accounting continuing professional education (CPE). Auto-login via Zheliban SSO and Chinaacc, play videos and skip completed courses, track credits, refresh the dashboard, and trigger remote QR-code login via SMTP email when the session expires.
category: productivity
version: 1.2.0
author: Dannywjj
agent_created: true
---

# 浙江会计继续教育自动刷课运维

> ⚠️ **使用前必读（首次安装）**
> 本 skill 是通用模板，**不含**你的账号/邮箱/SMTP 授权码等个人信息。使用者需要：
> 1. 在自己的项目 `.workbuddy/jxjy_mail_config.json` 填入自己的 QQ / 163 / Gmail 邮箱配置（**SMTP 必须用授权码，不要用登录密码**）。
> 2. 在 `.workbuddy/jxjy_state.json` 准备好浙里办 SSO + 正保 chinaacc 登录态（可由 `jxjy_remote_login.py` 或 `jxjy_login_window.py` 生成）。
> 3. 不要把带个人配置的文件提交到任何公开仓库。

## 触发场景

用户使用以下任一表述时，优先使用本技能：
- "继续教育刷课" / "继续教育自动刷课" / "会计继续教育"
- "今天的刷课开始了么" / "现在学到多少了" / "学分没动"
- "需要登录" / "远程扫码登录" / "登录态过期"
- "学时没累计" / "视频不播放"
- "继续教育看板" / "已学习学分 / 待学习学分"

> 备注：刷完自动关机功能已停用。如用户提出"刷完关机"，先确认是否真的需要，并在操作系统层单独执行 `shutdown /s /t 60`，不修改刷课脚本。

## 关键文件（当前项目 .workbuddy/ 下）

刷课与登录：
- `jxjy_daily_study.py` —— 每日刷课主脚本（仅参数：时长分钟数；**无自动关机**）
- `jxjy_login_window.py` —— 电脑旁人工登录（短信/扫码，弹出 Chrome 窗口）
- `jxjy_remote_login.py` —— 远程扫码登录（截图二维码 + 邮件推送到手机）
- `jxjy_state.json` —— Playwright 登录态（含 SSO_TOKEN + 正保 chinaacc cookie）
- `jxjy_study.log` —— 统一日志

数据与看板：
- `jxjy_dashboard_data.json` —— 学分汇总（总/专业/公需、今日学分、当前课程）
- `jxjy_courses.json` —— 课程清单（已学完/学习中/即将学习）
- `refresh_jxjy_after_session.py` —— 刷课结束后抓取最新学分面板
- `jxjy_dashboard_updater.py` —— 根据数据 JSON 刷新本地看板
- `继续教育看板.html`（项目根目录）—— 独立继续教育看板

邮件配置（远程扫码用）：
- `jxjy_mail_config.json` —— SMTP 配置 `{"from_addr","pass","to_addr","smtp_host":"smtp.qq.com","smtp_port":465}`

## 登录策略（优先级）

1. **电脑旁 → 人工登录**：后台启动 `jxjy_login_window.py --wait 10`，弹出 Chrome 窗口，用户短信/扫码登录，脚本自动保存 `jxjy_state.json`。

2. **人不在电脑旁 → 远程扫码登录**：后台启动 `jxjy_remote_login.py --wait 15`。
   - 脚本打开登录页 → 切「扫码登录」tab → 截取二维码 canvas 存到 `jxjy_login_qr.png`。
   - 若存在 `jxjy_mail_config.json`，每次刷新二维码（约 45 秒）自动发一封带图片附件的邮件到用户邮箱。
   - 用户手机邮件 App 收图 → 保存 → 浙里办/支付宝/微信「扫一扫 → 从相册选图」。
   - 登录成功后脚本自动保存 `jxjy_state.json` 并退出。
   - 注意：QQ 邮箱 SMTP 需要授权码（非登录密码）；`agent-mail` MCP 未开通不可用；WorkBuddy 手机 App 端无法稳定显示/保存产物图片，均不可用，邮件是唯一可靠远程通道。

3. **密码登录仅作最后手段**：会触发极验 v4 滑块，自动化易被风控，不推荐。

## 刷课启动流程

登录态有效后，用隔离 venv Python 启动：

```bash
cd "C:/Users/admin/WorkBuddy/<project>/.workbuddy"
"C:/Users/admin/.workbuddy/binaries/python/envs/default/Scripts/python.exe" jxjy_daily_study.py 900
```

> 提示：默认单次运行时长 15 小时（900 分钟）。如需临时调短/调长，直接改命令行最后一个数字即可；自动化任务的 prompt 里也会写明运行时长。

> 旧的 `--shutdown-on-exit` 参数已移除。如本次需要刷完关机，请在刷课脚本启动后另开终端执行 `shutdown /s /t 60`。

进入链：
1. `https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html`
2. 点「继续学习」→ 选课页
3. 点正保「继续学习」→ `jxjy.chinaacc.com/learningCenter`（此步动态建立正保 cookie）
4. `ctx.storage_state()` 写回 `jxjy_state.json`（含正保 cookie）
5. 学习中心表格找第一个可学课程行（**自动跳过已学完课程**，见下）
6. 点「开始学习/继续学习」→ `courseware/Index/...`
7. `start_video()` 大按钮 → 章节 `a:has-text("第01讲")`/`a.akuo`
8. 等 `video` 元素，URL 变为 `.../video/VideoPlayH5?VideoID=...`
9. 播完点下一讲；无下一讲则刷新学习中心找新课程

## 跳过已学完课程（关键逻辑）

`find_current_course()` 用 `is_course_row_completed()` 判断课程行是否已完成，满足任一即跳过：
- 行文本含「完成学习」；
- 「已完成/要求学分」为 `X/X`（如 `3.34/3.34 学分`）；
- 剩余时长为 `0/150分钟`。

**根因**：平台对学分已满的课程仍开放「继续学习」，脚本若不跳过会傻乎乎重播已拿满学分的课，导致学分不涨。修复后脚本会正确进入下一门未完成课程。

## 跨夜任务小贴士

自动化任务默认 9:00 启动、运行 15 小时，**次日 0:00 才结束**——会跨越深夜。

### 建议：保持电脑开机（或休眠代替关机）

- 跨夜时电脑一旦真关机，刷课进程会被强制中断；第二天 9:00 重启时虽然会自动进入未完成课程，但会**从该课的开头重新捡起**（已播过的部分会重新播放）。
- Windows 默认"按电源键 → 休眠"行为即可：休眠不杀进程、不耗电、唤醒后秒续。避免选"关机"或"重启"。

### 万一需要真关机（如长期出差、机器维护）

- **暂停自动化任务**（推荐）：让智能体调用 `automation_update` 把自动化任务（任务名"浙江会计继续教育每日自动刷课"）状态改为 `PAUSED`；回来后再改回 `ACTIVE`。
- **手动启动临时任务**：说"今晚继续教育手动跑到 22:00"，按小时数跑一次性的刷课任务，不占用自动化时长。

### 第二天首件事

1. 智能体启动自动化任务时，先看 `jxjy_state.json` 是否过期（cookie 数通常 ≥40）。
2. 若被踢到登录页（任务报 status=error），走"远程扫码登录"或"人工登录"流程重新生成登录态。
3. 登录后任务从第一门未完成课程开始；已学完的会被 `is_course_row_completed()` 自动跳过，不会傻乎乎重播。

## 按需自动关机（用户口令启用）

**默认不启用**——避免误关机风险。仅在用户当天**明确要求**时，才给 9:00 任务的 prompt 加上一段"刷完关机"逻辑，且**只在深夜 23:00 后**执行，避开白天误关机。

### 设计原则

- **不写死在 `jxjy_daily_study.py` 里**：保持脚本纯净，关机是上层调度决策
- **不修改刷课主脚本**：避免误触发后无法调试
- **不默认开启**：必须用户口令才会改 automation 任务的 prompt
- **深夜时间窗**：≥23:00 且 < 次日 08:00，避免白天误关机

### 用户原话触发（agent 自动处理）

| 用户原话 | agent 动作 |
|---|---|
| "今晚刷完关机" / "晚上刷完自动关机" | 给 9:00 任务 prompt 末尾追加 1 段（见下），次日 9:00 自动失效 |
| "今晚不关机" / "今晚取消关机" | 从 9:00 任务 prompt 末尾移除该段 |
| "以后每天都关机" / "默认刷完关机" | **拒绝**：明确告知"默认每天关机有误操作风险，请每次说一次"，引导用户每次单独口令 |
| "立刻关机" / "现在关机" | 立即执行 `shutdown /s /t 60`（不等任务结束） |
| "取消关机" / "别关机了" | 立即执行 `shutdown /a`（取消进行中的关机倒计时） |

### 追加到 9:00 任务 prompt 的内容（启用时）

```
7.【当日特殊 · 仅用户口令启用】任务报告 "学习完成" 后：
   - 若当前本地时间在 23:00 ~ 次日 08:00 之间：执行 `shutdown /s /t 60`（60 秒缓冲，用户可手动 `shutdown /a` 取消）
   - 若当前时间 < 23:00：不执行任何关机动作（避免白天被误关）
   - 若 jxjy_state.json 已失效导致学分未涨：跳过关机（用户应被提醒而非被关机）
```

agent 调用方式：

```python
# 启用今晚关机
automation_update(
    id="260afb90-3106-4a73-aead-538a39a1fe0a",  # 9:00 刷课任务 ID
    mode="update",
    prompt="<原 prompt>\n\n" + "<上述第 7 段>"
)

# 关闭今晚关机
automation_update(
    id="260afb90-3106-4a73-aead-538a39a1fe0a",
    mode="update",
    prompt="<原 prompt>"  # 不含第 7 段
)
```

### 安全兜底

- **60 秒缓冲**：`/t 60` 让用户有 1 分钟按 `shutdown /a` 取消
- **时间窗口限制**：白天（08:00~23:00）永不关机
- **失败兜底**：登录失效 / 学分未涨时跳过关机，避免"没刷到还被关机"
- **次日自动失效**：下次 9:00 任务启动时，agent 应重新检查口令是否仍有效（一般口令都是当日有效）

### 与跨夜任务的协同

| 场景 | 策略 |
|---|---|
| 9:00 启动 → 23:00 完成 + 用户口令 | 自动关机 |
| 9:00 启动 → 16:00 完成 + 用户口令 | **不关机**（时间未到 23:00） |
| 9:00 启动 → 23:00 完成 + 用户没口令 | 不关机 |
| 9:00 启动 → 23:30 仍未完成（卡课） | 不关机（学分未涨兜底触发） |
| 临时任务（用户口头说"今晚手动刷到 22:00"） | 由 agent 在临时任务里单独处理 |

## 常见故障与处理

### 1. 课程页「您的登录信息已失效」
- `jxjy_state.json` 缺正保（chinaacc）cookie。必须从浙江平台「学习中心 → 继续学习 → 正保」完整跳转，不要直接 goto courseware URL。

### 2. 进入课程页「未检测到 video 元素」
- 新课页面是章节目录 SPA。`start_video()` 需 fallback：大按钮 → `a:has-text("第01讲")`/`a.akuo` → 当前页等待 `video` 出现（10-30 秒）。

### 3. 视频进度不前进 / 学分不涨
- 先查日志 `current=` 是否每 20 秒推进；播放速度应约 1:1。
- 若长时间停在某课且学分不涨，多半是卡在已学完课程 → 检查 `is_course_row_completed()` 是否生效。
- 检查弹窗（继续学习/知道了等）用 `close_annoying()` 关闭。

### 4. 登录态隔夜失效
- SSO_TOKEN 有效期短。隔夜后 `jxjy_state.json` 大概率失效，刷课脚本进入学习中心会被踢到登录页（报告 status=error）。
- 处理：走「远程扫码登录」或「人工登录」重新生成登录态，再启动刷课。

### 5. 平台更换学习中心入口
- 平台曾把旧路径 `/ckmgr/ckmgrNews/golearncenterNew`（404）换成 `/front/golearncenterNew.html`。若再次 404，检查 `open_learning_center()` 里的入口 URL。

## 看板更新

刷课结束或用户查看时，同步看板数据：
1. `refresh_jxjy_after_session.py` 抓最新学分面板 → 更新 `jxjy_dashboard_data.json`。
2. `jxjy_dashboard_updater.py` 据 JSON 刷新 `继续教育看板.html` 与 `综合看板.html`。
3. 课程清单手动/脚本维护在 `jxjy_courses.json`。

看板核心指标口径：
- **已学习学分** = `total.got`（如 24.26）
- **待学习学分** = `total.need - total.got`（如 65.74）
- **即将学习学分** = 下一门待学课程的学分

## 配套自动化（每日中午刷新，可选）

刷课任务（默认每天 9:00 启动、跑 15 小时）只在结束时刷新一次看板。但白天用户想"看一眼当前学分"，就要等到 0:00 之后——这不友好。

**解决：建一个独立的"中午刷新" automation 任务**，每天 12:00 自动跑一次，只抓数据不刷课（~30 秒完成），与刷课任务并行无干扰。

### 为什么必须独立任务（不能合并到刷课任务）

- 9:00 刷课任务是单一连续进程（900 分钟不中断）
- 在它内部塞"12:00 暂停刷课→刷新→继续"会破坏视频连续性，跳课风险高
- 独立任务 12:00 跑 ~30 秒就退出，刷课进程无感知

### 一键创建命令（用 WorkBuddy 工具）

让智能体执行以下 prompt：

```
请帮我在当前 WorkBuddy 里创建一个定时自动化任务，参数如下：
- 任务名：浙江会计继续教育看板每日中午刷新
- 状态：ACTIVE
- 频率：FREQ=DAILY;BYHOUR=12;BYMINUTE=0
- 工作目录：C:\Users\admin\WorkBuddy\<当前项目目录>\.workbuddy
- 任务 prompt：

  运行浙江会计继续教育看板中午刷新：
  1. 使用 Python 解释器 C:\Users\admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe
  2. 工作目录切换到工作目录参数指定的位置
  3. 执行命令：python refresh_jxjy_after_session.py
     - 该脚本会用 jxjy_state.json 的登录态打开学习中心 → 抓取最新学分 → 写入 jxjy_dashboard_data.json
  4. 然后执行：python jxjy_dashboard_updater.py
     - 该脚本根据 jxjy_dashboard_data.json 刷新 继续教育看板.html 和 综合看板.html
  5. 读取 jxjy_dashboard_data.json，向用户汇报当前总学分 / 专业课 / 公需课、今日学分、正在学课程
  6. 如果 jxjy_state.json 已过期导致抓数据失败，输出提醒"登录态过期，下次 9:00 刷课任务会自动重建"即可，不强制重建登录态（避免重复扫码打扰用户）。
```

创建后可用 `automation_update id=<新任务id> mode=view` 校验。

### 关闭 / 删除

- **暂停**：`automation_update id=<id> status=PAUSED`，12:00 不再触发但任务保留
- **永久删除**：`automation_update id=<id> mode=delete`
- **修改时间**：`automation_update id=<id> mode=update rrule=FREQ=DAILY;BYHOUR=18;BYMINUTE=0`（改成 18:00 傍晚刷新）

### 用户原话触发

用户说以下任一表述时，按本节流程创建或更新任务：
- "继续教育每天 12 点自动刷新一下" → 按上述默认参数创建
- "继续教育改成下午 6 点刷新" → mode=update 改 rrule
- "中午刷新暂停" → status=PAUSED
- "中午刷新停了" / "删掉中午刷新" → mode=delete

## 依赖环境

隔离 venv Python（必须）：
```
C:/Users/admin/.workbuddy/binaries/python/envs/default/Scripts/python.exe
```
依赖：`playwright`、`PIL`。邮件推送用标准库 `smtplib`/`email`。

## 调试脚本

- `jxjy_chain_diag.py`：验证浙江平台 → 正保跳转后 chinaacc cookie。
- `jxjy_course_diag.py`：直接访问 courseware 页检查登录态。
- `jxjy_video_diag.py`：完整走链路确认 video 出现。
- `jxjy_remote_login.py --demo`：只截一次二维码验证（不进入循环）。

## 邮箱配置（远程扫码登录）

配置文件：`.workbuddy/jxjy_mail_config.json`，脚本 `jxjy_remote_login.py` 启动时通过 `load_mail_config()` 自动读取，无需每次手动设置。**示例为占位符，请替换为你自己的真实配置后保存**：

```json
{
  "from_addr": "<你的发件邮箱，例如 123456@qq.com>",
  "pass": "<你的SMTP授权码，不是登录密码>",
  "to_addr": "<收件邮箱，建议与发件邮箱一致>",
  "smtp_host": "smtp.qq.com",
  "smtp_port": 465
}
```

常见 SMTP 服务商参考：QQ 邮箱 `smtp.qq.com:465 SSL`、163 邮箱 `smtp.163.com:465 SSL`、Gmail `smtp.gmail.com:587 STARTTLS`（需开"不够安全的应用"或应用专用密码）。

注意：QQ 邮箱 SMTP 必须使用**授权码**（非登录密码）；163 / Gmail 同理。`agent-mail` MCP 未开通不可用；WorkBuddy 手机 App 端无法稳定显示/保存产物图片，邮件是唯一可靠远程通道。

### 标准重置话术

用户使用以下任一表述时，直接更新 `jxjy_mail_config.json`（**先备份原文件**为 `jxjy_mail_config.json.bak`，改坏可恢复）：

| 用户原话 | 动作 |
|---------|------|
| "继续教育邮箱重置成 `<邮箱>`，授权码 `<授权码>`" | 全量更新 from_addr / pass / to_addr |
| "继续教育二维码发到 `<新邮箱>`" | 仅更新 to_addr |
| "继续教育 SMTP 改成 163，邮箱 `<邮箱>`，授权码 `<授权码>`" | 全量更新 smtp_host / smtp_port / from_addr / pass |
| "继续教育邮箱授权码过期了，新的是 `<新授权码>`" | 仅更新 pass |
| "继续教育远程扫码改成企业微信 / 微信 / 钉钉推送" | 切换通道（需先确认有对应 MCP/Agent 可用），暂不可用时回退邮件 |
| "继续教育当前邮箱配置是啥" | cat 配置文件并展示 |

修改后用 `python -c "from jxjy_remote_login import load_mail_config; print(load_mail_config())"` 验证加载。

## 多账号扩展（未来规划）

> ⚠️ **本节为未实现规划**。当前 skill 仅支持单账号。如需多账号同步刷课，需按以下方案改造。

### 适用场景

- 本人多个继续教育账号（主 + 备用）
- 同事/家人委托代刷（多人共用同一台电脑）

### 不建议现在做的原因

1. **平台风控风险高**：正保网校同 IP 短时间开多账号易触发"批量账号"风控，可能导致账号临时锁定。
2. **资源占用大**：每 Chrome 实例约 300–500MB，3 账号 ≈ 1.5GB 内存。
3. **同步登录冲突**：多账号同时扫码，邮件里多张二维码容易混淆。
4. **改造会中断当前刷课**：脚本改动期间正在跑的任务会中断。

### 推荐触发时机

- 自己主账号刷完 / 快刷完时
- 确认有 3 个以上明确需要的账号
- 平台风控政策放宽后再评估

### 改造方案（待实施）

#### 1. 数据隔离（按账号后缀命名文件）

```
.workbuddy/
├── jxjy_state_<account>.json          # 登录态
├── jxjy_dashboard_data_<account>.json # 学分数据
├── jxjy_courses_<account>.json        # 课程清单
├── jxjy_mail_config_<account>.json    # 可选：每账号独立邮箱
└── jxjy_study_<account>.log           # 日志
```

#### 2. 命令行参数

```bash
python jxjy_daily_study.py 900 --account <account_id>
python jxjy_remote_login.py --wait 15 --account <account_id>
python jxjy_login_window.py --wait 10 --account <account_id>
```

`<account_id>` 推荐用账号后 8 位手机号或拼音首字母（如 `tdn` / `zhangsan`）。

#### 3. 自动化任务

每个账号独立 automation：

- 任务名：`浙江会计继续教育每日自动刷课 - <account_id>`
- rrule 同：`FREQ=DAILY;BYHOUR=9;BYMINUTE=0`
- prompt 里加 `--account <account_id>`

#### 4. 看板适配

- **综合看板**：检测 `.workbuddy/jxjy_dashboard_data_*.json` 文件数，每个账号一个 tab
- **独立看板**：保持单一，但加账号切换器（页面右上角下拉）

#### 5. 远程扫码登录（重要）

每账号独立邮箱收件，避免混淆：

```json
// jxjy_mail_config_zhangsan.json
{
  "from_addr": "...",
  "pass": "...",
  "to_addr": "zhangsan@example.com",  // 张三自己的收件
  ...
}
```

启动时按 `--account` 自动选对应配置文件。

### 风控对策建议

1. **错峰启动**：3 个账号不要同一分钟开刷，间隔 5–10 分钟
2. **限制并发**：同一时间最多 2 个账号在线播放，第三个在后台待命
3. **IP 隔离**：3+ 账号建议换不同 IP（公司网络 vs 家里网络错开）
4. **观察期**：新账号上线后头一周每天手动检查一次"无异常登录提醒"

### 用户指令示例（待实现）

- "加一个新账号 zhangsan，用他手机 13800138000 当 ID"
- "3 个账号一起刷，每个错峰 10 分钟"
- "暂停 zhangsan 的刷课"
- "现在 zhangsan 账号学到哪了"
