---
name: zj-jxjy-study
display_name: 浙江会计继续教育自动刷课
display_name_en: Zhejiang Accounting CPE Auto-Study
description: 浙江会计继续教育自动刷课（学分管理 / 浙里办 SSO / 正保网校 chinaacc / 90 学分）。用于每日自动登录学习中心、播放视频、跳过已学完课程、判断学分累计、刷新看板数据；登录态隔夜失效时自动触发远程扫码登录（SMTP 邮件推送二维码）。触发词：继续教育、会计继续教育、浙里办学习中心、正保网校、自动刷课、刷学分、学分没动、视频不播放、远程扫码登录、登录态过期、继续教育看板。
description_zh: 面向浙江会计从业者的继续教育自动刷课技能：自动登录浙里办 SSO 与正保网校、播放视频并跳过已学完课程、累计学分、刷新看板；登录态过期时通过 SMTP 邮件推送二维码远程扫码登录。
description_en: Auto-study skill for Zhejiang accounting continuing professional education (CPE). Auto-login via Zheliban SSO and Chinaacc, play videos and skip completed courses, track credits, refresh the dashboard, and trigger remote QR-code login via SMTP email when the session expires.
category: productivity
version: 1.7.0
author: Dannywjj
agent_created: true
---

# 浙江会计继续教育自动刷课运维

> ⚠️ **使用前必读（首次安装）**
> 本 skill 是通用模板，**不含**你的账号/邮箱/SMTP 授权码等个人信息。使用者需要：
> 1. 在自己的项目 `.workbuddy/jxjy_mail_config.json` 填入自己的 QQ / 163 / Gmail 邮箱配置（**SMTP 必须用授权码，不要用登录密码**）。
> 2. 在 `.workbuddy/jxjy_state.json` 准备好浙里办 SSO + 正保 chinaacc 登录态（可由 `jxjy_remote_login.py` 或 `jxjy_login_window.py` 生成）。
> 3. 不要把带个人配置的文件提交到任何公开仓库。

## 换账号 / 给别人用的落地清单（脱敏 checklist）

本 skill **不含任何个人账号信息**，脚本里没有写死姓名、手机号、邮箱、所在目录。
换到一个全新的号上跑，只需按下面四步准备；**唯一不能共享的是登录态**。

| # | 要做的事 | 说明 | 能否从别人那儿拷 |
|---|---|---|---|
| 1 | 装 skill | `SKILL.md` 放到 `~/.workbuddy/skills/zj-jxjy-study/SKILL.md` | ✅ 可以 |
| 2 | 放脚本 | `scripts/` 下 10 个 `.py` → 自己项目的 `.workbuddy/`（**必须放这里**，脚本按自身目录读写状态文件） | ✅ 可以 |
| 3 | **生成自己的登录态** | 跑 `jxjy_login_window.py`，本人扫码/短信登录，产出 `jxjy_state.json` | ❌ **绝对不能拷** |
| 4 | 填自己的邮箱 | `jxjy_mail_config.json`（SMTP 授权码，非登录密码） | ❌ 不能拷 |

> ⚠️ **第 3 步是硬隔离**：`jxjy_state.json` 就是那个人的登录凭证，拷给别人 = 把账号交出去，
> 而且两个人同时用同一份登录态会**互相踢下线**，两边都刷不成。必须各自登录。

**两个可能需要调的参数**（换账号 / 跨年度时）：

| 参数 | 默认值 | 什么情况下要改 |
|---|---|---|
| 学习年度 | 当前自然年 | 跨年补学（如 2027 年还在补 2026 年度）→ `set JXJY_YEAR=2026` |
| 学习计划 ID | 自动识别，兜底 21037 | 拉证报「未找到打印信息」且日志显示用了兜底值 → `jxjy_download_cert.py 200 --study-id <真实ID>` |

> 换年度时先看这几个地方：`refresh_jxjy_after_session.py` 的选课 URL 带 `syear=`、
> 学分面板抓的是含年度的那一行。两者都跟随上面的学习年度参数，不需要改代码。

## 触发场景

用户使用以下任一表述时，优先使用本技能：
- "继续教育刷课" / "继续教育自动刷课" / "会计继续教育"
- "今天的刷课开始了么" / "现在学到多少了" / "学分没动"
- "需要登录" / "远程扫码登录" / "登录态过期"
- "学时没累计" / "视频不播放"
- "继续教育看板" / "已学习学分 / 待学习学分"

> 备注：**刷课脚本本身不含自动关机**（`jxjy_daily_study.py` 只负责刷课）。用户提出"刷完关机"时，
> 由独立看门狗 `jxjy_auto_shutdown.py --at "<时刻>" --on-all-done` 负责关机，**不要改刷课脚本**。
> 跨天/长会话还需另挂 `jxjy_login_guard.py` 保证中途掉线能自动接力。

## 关键文件（当前项目 .workbuddy/ 下）

刷课与登录：
- `jxjy_daily_study.py` —— 每日刷课主脚本（仅参数：时长分钟数；**无自动关机**）
- `jxjy_login_window.py` —— 电脑旁人工登录（短信/扫码，弹出 Chrome 窗口）；带 `--check` 可无头探测当前 profile 是否仍在线
- `jxjy_remote_login.py` —— 远程扫码登录（截图二维码 + 邮件推送到手机）
- `jxjy_download_cert.py` —— 刷满 90 后自动从平台拉取「会计专业技术人员继续教育学习证明」PDF（详见「学习证明自动拉取」一节）
- `jxjy_chain_login_study_cert.sh` —— 三段链式：登录窗口等待 → 登录成功自动刷课 → 刷完自动拉证明（详见「学习证明自动拉取」一节）
- `jxjy_state.json` —— Playwright 登录态（含 SSO_TOKEN + 正保 chinaacc cookie）
- `jxjy_study.log` —— 统一日志
- `jxjy_study_report.json` —— 本次会话报告（`status` 见「完成态语义」一节）
- `jxjy_study.lock` —— 单实例锁（内容 = 运行中的 PID）

长跑守护（跨天/长会话必用）：
- `jxjy_login_guard.py` —— **登录态守护 + 会话接力看门狗**（详见「长跑守护」一节）
- `jxjy_auto_shutdown.py` —— 定时/刷完自动关机看门狗
- `jxjy_login_guard.log` / `jxjy_shutdown.log` —— 两个守护各自的日志

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

2. **人不在电脑旁 → 远程扫码登录**：后台启动 `jxjy_remote_login.py --wait 5`
   （⚠️ **二维码有效期实测仅约 60 秒**，见下「坑 0」；先确认用户在手机旁再发码，否则纯属白等 + 炸邮箱）。
   - 脚本打开登录页 → 切「扫码登录」tab → 截取二维码 canvas 存到 `jxjy_login_qr.png`。
   - 若存在 `jxjy_mail_config.json`，每个**内容变化**的二维码自动发一封带图片附件的邮件到用户邮箱
     （按 MD5 去重 + 最小 2 分钟间隔，避免 45 秒一轮的刷新炸邮箱）。
   - 用户手机邮件 App 收图 → 保存 → 浙里办/支付宝/微信「扫一扫 → 从相册选图」。
   - 登录成功后脚本自动保存 `jxjy_state.json` 并退出。
   - **`--headless`（2026-09-11 实测可用）**：无头也能正常切到「扫码登录」tab 并截到二维码
     （实测输出 9306 字节的真二维码 PNG）。**锁屏 / 无人值守时必须用无头**——
     有头窗口在锁屏会话上可能渲染失败。`jxjy_login_guard.py` 已默认「先无头、失败再有头兜底」。
   - 邮件通道自检（不真发信）：
     ```python
     import smtplib, json
     cfg = json.load(open('jxjy_mail_config.json', encoding='utf-8'))
     s = smtplib.SMTP_SSL(cfg.get('smtp_host','smtp.qq.com'), int(cfg.get('smtp_port',465)), timeout=30)
     s.login(cfg['from_addr'], cfg['pass']); s.noop(); s.quit()   # 全部通过 = 救援邮件可发出
     ```
   - 注意：QQ 邮箱 SMTP 需要授权码（非登录密码）；`agent-mail` MCP 未开通不可用；WorkBuddy 手机 App 端无法稳定显示/保存产物图片，均不可用，邮件是唯一可靠远程通道。

3. **密码登录仅作最后手段**：会触发极验 v4 滑块，自动化易被风控，不推荐。

### 登录重试实操经验（2026-09-10 踩坑）

**坑 0（2026-09-14 实测，最关键）：二维码真实有效期 ≈ 60 秒，远程邮件扫码通道基本不可用。**
无头登录页实测时间线：t=4s~56s 页面无任何失效文案、canvas 不变；
**t=67s 出现「二维码已失效 / 请点击刷新」，canvas 内容同时改变** → 即平台侧二维码 TTL ≈ 60 秒（并非脚本误判）。
后果：`邮件 → 打开邮件 → 保存图片 → 相册扫一扫` 的链路通常 > 60 秒，用户看到的码**早已失效**，
因此历次"远程扫码救援"屡屡失败（用户最终都只能回到电脑旁重新登录）。
→ **规则**：远程扫码**只在用户明确说"我现在在手机旁"时才发码**，并提醒"收到立刻扫，码只有 60 秒"；
   无人值守时不要指望邮件通道能救回来，跨天任务宁可提前挂 `jxjy_login_guard.py` 并默认用户会在电脑前。
→ **可靠路径永远是「电脑旁 `jxjy_login_window.py`」**（窗口内可手动点「刷新」续码，不受 60 秒限制影响使用节奏）。

**坑 1：远程扫码窗口开太长会"邮件轰炸"**。二维码每约 45 秒刷新一次，`--wait 15` 会在 15 分钟内发出 **约 20 封**邮件，明显骚扰用户（2026-09-14 实测 `--wait 10` 也发了 **17 封**）。
→ **远程扫码请把 `--wait` 控制在 5 分钟以内**；超时后先问用户"方便时告诉我，我再发一次"，不要直接再开 15 分钟窗口。

**坑 2：登录窗口超时后用户往往还没回来**。连开两次窗口都容易白等。
→ **推荐"登录窗口 + 自动接刷课"链式命令**：窗口开长时间（≤60 分钟），登录成功即自动启动刷课，用户任何时刻回电脑前都能直接登，agent 无需值守：

```bash
cd <项目>/.workbuddy
rm -f jxjy_login_success.flag
"<venv>/Scripts/python.exe" jxjy_login_window.py --wait 60 2>&1 | tee jxjy_login_window2.log
if [ -f jxjy_login_success.flag ]; then
  "<venv>/Scripts/python.exe" jxjy_daily_study.py 900 >> jxjy_study.log 2>&1
else
  echo "=== LOGIN_TIMEOUT 未登录，未启动刷课 ==="
fi
```
（后台运行；`jxjy_login_window.py` 检测到登录会写 `jxjy_login_success.flag` 并退出，因此 flag 可作为链式判断条件。）

**坑 3：登录态「半失效」的识别**。表现为两类探测结果矛盾：
- `refresh_jxjy_after_session.py` 仍能直接打开 chinaacc 学习中心并抓到**新鲜**学分（chinaacc 侧 cookie 未过期）；
- 但 `jxjy_login_window.py --check` / 首页探测被重定向到 `user.zjzwfw.gov.cn/pc/login?action=ssoLogin...`（浙江平台 SSO_TOKEN 已失效），刷课脚本会直接 `RuntimeError: 未能进入学习中心页面`。

→ 结论：**面板能抓 ≠ 能刷课**。只要被重定向到登录页，就必须重新登录，别再试着重启刷课脚本。

## 刷课启动流程

登录态有效后，用隔离 venv Python 启动：

```bash
cd "<你的项目>/.workbuddy"      # 例：D:/我的工作台/【我的小助理】/.workbuddy
"<隔离venv>/Scripts/python.exe" jxjy_daily_study.py 840
```

> 提示：运行时长就是命令行最后一个数字（分钟）。**当前每日 09:00 自动化任务用 840 分钟（09:00 → 23:00）**；
> 历史上曾误设为 60 分钟，导致进度极慢 —— 排查「学分不涨」时先确认这个数字。
> 脚本内部默认值 `DEFAULT_MINUTES = 480`（不传参数时生效）。

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

## 公需课自动切换（2026-09-11 新增）

### 背景：公需课长期 0 分的真实原因

浙江会计继续教育要求：**总 ≥90 学分，专业课 ≥60，公需课 ≥18**。正保学习中心的课程表是
**专业课分类在前、公需课分类在后**：

```
专业课：会计职业道德 / 会计法治 / 会计改革与发展 / 企业财务会计 / 政府及非营利组织会计 /
        农村会计 / 管理会计 / 内部控制 / 财务管理 / 税收实务 / 会计信息化 /
        可持续信息披露 / 审计基础 / 金融基础 / 财经相关法规 / 其他财会财经热点
公需课：管理基础 / 财经基础 / 科学技术 / 思政文化 / 公共管理 / 综合素质   ← 排在最后
```

> ⚠️ **只要专业课还有未完成课程，`find_current_course()` 就永远取不到公需课** —— 这就是「公需课一直 0 分」的根因（与登录态、风控无关）。

### 关键事实（实测）

| 事实 | 证据 |
|---|---|
| 公需课与专业课**同平台**（正保 chinaacc） | 学习中心有 `课程分类 → 公需知识` 筛选 tab（class `.pc_cwaretype`） |
| 「包干价」套餐**无需逐门选课** | `jxjy.chinaacc.com/selectStudy`：包干价 = 年度内对应级别所有课程可学。公需课 99 门状态全为「开始学习」 |
| 公需课共 **99 门** | 思政文化 42 / 公共管理 20 / 管理基础 14 / 科学技术 10 / 财经基础 8 / 综合素质 5 |
| **学分密度恒定 ≈ 0.0222 学分/分钟**（约 45 分钟 1 学分） | 各门课 credits/时长 比值一致 → **挑课不省时间**，18 学分恒需 ≈810 分钟；只按「相关性」挑 |

### 实现（`jxjy_daily_study.py` 已内置）

- `should_do_public()`：`专业课 >= 60` 且 `公需课 < 18` → True，切公需课模式。
- `find_current_course(study_page, prefer_public=True, plan=[...])`：公需课模式下按计划名单**逐门搜索定位**；
  名单全完成/搜不到 → 退化为点「公需知识」分类顺序选课。
- 计划文件：`.workbuddy/jxjy_pubcourse_plan.json`（有序课程名单，用户可随时改）。
- 刷课结束一门课后会先等学分入账（最多 4×20 秒）再判定模式，避免入账延迟误判。
- `enter_course(..., prefer_public, plan)` 逐层透传参数。

### 学习中心课程搜索框用法（重要技巧）

学习中心表格分页只显示 10 行/页，分类筛选靠 AJAX 重载 —— **直接抓 `table tr` 会把隐藏行也算进去**（静态 657 行）。要精确定位某一门课，用搜索框：

```
输入框：#courseSearch0（placeholder「请输入课程名称/关键字搜索」）
触发：  必须点 a.searchBth（.searchBth）—— 合成 keyboard event / form submit 都无效
结果：  表格过滤为命中行；行内链接 onclick =
        isStudyThisCourse(64410973,21037,<courseId>,'course_jxjy',2)   # 2=开始学习，1=继续学习
```

> 读表格行用 `row.inner_text()`：Playwright 对隐藏元素返回空串，天然过滤掉分页外的隐藏行。

### 挑课建议

公需课学分密度恒定，按内容相关性挑即可。财税从业者常用组合：
- **财税+数字化**：新经济新业态下非财人员的财税管理(9.65) + Excel+AI高阶应用实战(6.41) + DeepSeek功能介绍与使用场景(2.94) = 19.00 学分
- **管理能力向**：新经济新业态下非财人员的财税管理(9.65) + 管理智慧：甩掉影响你前进的包袱(7.30) + 传统财务向财务BP的跨越(1.63) = 18.58
- **思政党建为主**：中国共产党人的精神谱系(5.43) + 《中国共产党纪律处分条例》专题讲座(5.25) + 习近平讲故事(3.54) + 习近平谈治国理政（第五卷）(3.38) + 弘扬伟大建党精神(2.41) = 20.01

枚举全部公需课：`python jxjy_pubcourse_list.py`（翻页导出分类/名称/时长/学分/状态）。

## 跨夜任务小贴士

自动化任务 9:00 启动、运行 840 分钟（09:00 → 23:00）。若临时改成 900 分钟则会跨到次日 0:00，会跨越深夜。

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
| "**继续教育学习完毕后关机**" / "**最迟次日 N 点关机**" / "**跑到今天X点关机**" | **启动独立看门狗脚本** `jxjy_auto_shutdown.py`（30 秒轮询），触发 `shutdown /s /t 60`：
  - 指定时刻：`--at HH:MM`（今天；已过则顺延明天）/ `--at "YYYY-MM-DD HH:MM"` 或 `--at HH:MM --date YYYY-MM-DD`（指定具体日期）/ `--after N`（N 分钟后）→ 默认**只按时间点关机**
  - 提前关机（可选叠加）：`--on-all-done` = **所有课程真正刷完**（completed/all_courses_done）才提前关；`--on-study-done` = 本次会话结束（含 time_up 计时到点）就关
  - 无参数（旧行为）：刷课报告 status ∈ {completed, all_courses_done, time_up} → 立即关机；或到达启动次日 03:00 → 兜底关机 |
| "以后每天都关机" / "默认刷完关机" | **拒绝**：明确告知"默认每天关机有误操作风险，请每次说一次"，引导用户每次单独口令 |
| "立刻关机" / "现在关机" | 立即执行 `shutdown /s /t 60`（不等任务结束） |
| "取消关机" / "别关机了" | 立即执行 `shutdown /a`（取消进行中的关机倒计时） |

### 「学习完毕 + 最迟时间」关机方案（推荐用于跨夜任务）

适用于用户口头给出"刷完关机"+"最迟 X 点"组合指令（如本会话 2026-09-09 "继续教育学习完毕后关机，最迟次日3点"）。

**优势 vs 9:00 任务 prompt 嵌入**：
- ✅ 不依赖 automation 任务执行（agent 不可用时仍生效）
- ✅ 支持任意最迟时间，不限于 23:00 后
- ✅ 看门狗和刷课进程相互独立，一个挂了不影响另一个
- ✅ 看门狗脚本本身可重复使用（用户再次说同样指令时，agent 直接 `python jxjy_auto_shutdown.py` 即可）

**脚本位置**：`<你的项目>/.workbuddy/jxjy_auto_shutdown.py`（脱敏版在 `scripts/`）。注意其 `BASE` 是脚本内唯一写死的绝对路径。

**启动命令**：
```bash
# ① 指定时刻关机（推荐）—— 今天 21:00；已过则自动顺延到明天
cd "<项目>/.workbuddy" && python jxjy_auto_shutdown.py --at 21:00
# ② 指定"次日 21:00"（跨天跨天场景；只给 HH:MM 会落到今天，必须给日期）
python jxjy_auto_shutdown.py --at "2026-09-12 21:00" --on-all-done
#    等价写法：--at 21:00 --date 2026-09-12
# ③ N 分钟后关机
python jxjy_auto_shutdown.py --after 300
# ④ 无参数 = 旧行为（本次会话结束就关 或 启动次日03:00兜底）
python jxjy_auto_shutdown.py
```

**判定逻辑**：
- 每 30 秒检查一次
- 指定时刻（`--at` / `--after`）默认：**只按时间点关机**，不受刷课是否结束影响
- 可选叠加提前关机条件：
  - `--on-all-done`：仅当**所有课程真正刷完**（status ∈ {completed, all_courses_done}）时提前关机
    —— 用户说"**刷完就关**"用这个（**不会**被 `time_up` 计时到点误触发）
  - `--on-study-done`：本次刷课会话一结束（含 `time_up`）就关机
- 无参数模式：条件 ① status ∈ {completed, all_courses_done, time_up} → 立即关机；条件 ② 当前时间 ≥ 启动次日 03:00 → 兜底关机
- 关机命令：`shutdown /s /t 60` + 提示文案（用户可 60 秒内执行 `shutdown /a` 取消）

> ⚠️ **`time_up` 不是"刷完"**：它表示"本次会话计时到点、按设定时长正常退出"。用户要求"刷完再关机"时，
> 若用了旧语义或 `--on-study-done`，会话一到时长就会误关机。跨天连续刷课的场景一律用 `--on-all-done`。

**日志位置**：`jxjy_shutdown.log`（可随时查看看门狗状态）

### 单实例防护（防止同账号两会话互踢）

`jxjy_daily_study.py` 内置单实例锁 `.workbuddy/jxjy_study.lock`（内容 = 当前进程 PID）：
- 启动时若锁文件里的 PID**仍存活** → 打印「检测到已有刷课实例在运行（PID xxx），本次跳过」并 `exit 0`，**不启动新会话**。
- 锁里的 PID 已死（崩溃/被 taskkill）→ 自动接管并正常运行，无需人工清理。
- 进程正常退出时自动删除自己的锁（`atexit`）。

**为什么需要**：推长会话（如"连续刷到明天 21:00"）时，次日 09:00 的自动任务会照着 prompt 再起一个
`jxjy_daily_study.py`。同一正保账号被两个会话同时登录会**互相踢下线**，两边都刷不成。有此锁后，
09:00 任务会干净跳过；长会话若中途挂了，09:00 任务又能自愈接上。

> 排查：若日志出现「检测到已有刷课实例在运行」，而实际并没有会话在跑 → 锁文件残留了失效 PID，
> 直接删除 `.workbuddy/jxjy_study.lock` 即可（脚本也会在下次启动时自动接管）。

**关闭看门狗**：
```bash
# 方法 1：按命令行定位并结束（推荐；注意杀进程树，venv 是 启动器→真实解释器 两层）
powershell -c "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object CommandLine -like '*jxjy_auto_shutdown*' | ForEach-Object { taskkill /F /T /PID $_.ProcessId }"
# 方法 2：用户 Ctrl+C（仅前台运行时）
# 方法 3：用户重启电脑
```

> ⚠️ 后台启动的看门狗**没有窗口标题**，用 `taskkill /FI "WINDOWTITLE eq ..."` 抓不到，必须按命令行匹配。
> ⚠️ 若关机倒计时已开始（`shutdown /s /t 60` 已发出），**取消要执行 `shutdown /a`**，杀看门狗进程并不能取消已排队的关机。

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
    id="647a0028-0377-4501-a629-f3bb7936a882",  # 9:00 刷课任务 ID（变更时会重建，先 mode=list 核对）
    mode="update",
    prompt="<原 prompt>\n\n" + "<上述第 7 段>"
)

# 关闭今晚关机
automation_update(
    id="647a0028-0377-4501-a629-f3bb7936a882",  # 9:00 刷课任务 ID（变更时会重建，先 mode=list 核对）
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

## 完成态语义（「刷完即关机」的判据）

`jxjy_study_report.json` 的 `status` 取值与含义：

| status | 含义 | 是否算"刷完" |
|---|---|---|
| `running` | 会话进行中 | 否 |
| `time_up` | **本次会话计时到点**，课程未必刷完 | **否** |
| `all_courses_done` | **总学分 ≥ 90，年度任务完成**（2026-09-11 起脚本会输出） | 是 |
| `done_no_more_courses` | 学习中心已无可继续学习的课程 | 是 |
| `too_many_entry_failures` | 连续 8 门课程打不开 | 否 |
| `error` | 异常；`error` 含 `zjzwfw.gov.cn` → 登录态失效 | 否 |

> ⚠️ **历史坑（2026-09-11 修复）**：刷课脚本原先**从不输出** `all_courses_done` / `completed`，
> 而看门狗 `--on-all-done` 只认这两个值 → 「刷完再关机」形同虚设，实际永远只能到点关机。
> 现已两侧补齐：脚本在学分达标（总 ≥ 90）时输出 `all_courses_done`；
> 看门狗把 `done_no_more_courses` 也计入完成，并追加「看板学分数据 15 分钟内刷新且总学分达标」兜底判据。

## 年度达标后的收尾（自动化运维，2026-09-16 实践）

学分三项全部达标（总 ≥90 且 专业 ≥60 且 公需 ≥18）后，**继续每天 09:00 跑刷课没有意义**：

- 平台已无「打印学习证明」之外的增量，刷课脚本只会因为登录态过期反复报 `status=error`，
  每天一条失败提醒反而制造噪音（实测 2026-09-16 16:43 就是这样一次空跑）。
- **核对顺序（接到"继续教育自动更新/怎么还在刷"类需求时先做这三步）**：
  1. `cat .workbuddy/jxjy_dashboard_data.json` → 看 `total/major/public` 的 got vs need；
  2. `cat .workbuddy/jxjy_study_report.json` → 看最近一次 status（error 且含 `zjzwfw.gov.cn` = 登录态过期，不是脚本坏了）；
  3. 项目根目录是否已有 `会计专业技术人员继续教育学习证明.pdf` / `继续教育证明/` 目录 → 有即证明已归档。

**收尾动作**：

| 动作 | 说明 |
|---|---|
| 暂停 09:00 刷课任务 | `automation_update mode=update id=<刷课任务id> status=PAUSED`；同时在 prompt 开头加一段「某年度已达标、本任务已暂停、恢复前先确认是否新年度」的说明，避免日后误判为故障 |
| 保留 12:00 看板刷新任务 | 数据不再变化，但保留可让看板不显示陈旧时间戳；其 prompt 里补一句「抓取失败简要说明即可、不要重试/打扰用户」 |
| 不要删除任务 | 新年度（一般 1 月起）直接改回 `ACTIVE` + 更新年度，比重建省事 |

> 恢复刷课的唯一信号：**进入新年度** 或 用户明确要求继续刷（如换了工作/补学）。
> 恢复时记得 `jxjy_state.json` 大概率已过期，需先走一次人工登录。

## 学习证明自动拉取（刷满 90 后）

`jxjy_download_cert.py` —— 刷满 90 学分后，自动从**正保会计网校学习中心**拉取
**平台自己出具的官方「继续教育学习证明（合格证）」**（与学习中心「证书打印」同源；
文件名固定为 `会计专业技术人员继续教育学习证明.pdf`，平台通常同时提供 pdf / jpg / xml 三种格式，以 pdf 为准）。

> ⚠️ **交付物口径（最关键，2026-09-14 用户明确）**：
> **交付给用户的是「正保 / 浙江继续教育平台自己出具的官方学习证明」**，即本脚本从正保学习中心
> `https://jxjy.chinaacc.com/mgt/certPrint?studyID=21037`（mgt 会话，认 `jxjy_state.json`）拉取的 PDF
> （参考已落盘的 `继续教育证明/继续教育学习证明_2026-09-12.pdf` / `.jpg` / `.xml`）。
> **绝不能**把本地用 `jxjy_dashboard_data.json` 自制的「完成情况证明」HTML / 网页另存 PDF 当成交付物 ——
> 那只是登录态不可用、平台又打不开时的**兜底说明**，不具备官方效力，用户明确不要。

**触发**：用户说"刷完拉证明" / "下载学习证明" / "拿个结业证明"；或刷课 `all_courses_done` 之后。
**前置**：登录态有效（`jxjy_state.json` 且浙里办 SSO 未过期，< 9 小时）。
**真实入口（2026-09-14 实测，已跑通）**：
- 正保学习中心「证书打印 / 去打印」按钮 → `https://jxjy.chinaacc.com/mgt/certPrint?studyID=<学习计划ID>`
  （2026 学习计划 ID 实测为 21037，与页面上的 `isContinueLearning(...,21037,...)` 一致；
   **不同账号 / 不同年度可能不同**，脚本会自动解析，见下方「学习计划 ID 怎么定」）。
- **不是**浙江平台 `golearncenterNew.html` 的「查看详情」页 —— 那个页**只有「查看详情」、没有打印按钮**，
  原脚本在此页找按钮必然失败（退出码 4）。现已改为直连上面的 certPrint 地址。
- 全国平台 `ausm.mof.gov.cn` 的「会计人员继续教育登记 → 学习证明」是**权威备份源**（浙江平台明文：
  "继续教育总学分以全国平台登记信息为准"），但其 SPA 子模块在无头环境点击不触发路由，需真人可见浏览器操作，
  故脚本主走正保侧、全国平台作人工兜底。

**原理**：
1. 读本地汇总总学分（来自 `jxjy_dashboard_data.json`）；**未达标时每 60 秒轮询**（默认最多等 180 分钟）。
2. 达标后用 `jxjy_state.json` 的 mgt 会话直连 `certPrint?studyID=<解析出的学习计划ID>`。

**学习计划 ID 怎么定（换账号 / 跨年度必看）**：
脚本启动时先把学习中心页面打开一次，按以下优先级确定 studyID，并在日志里打印来源：

| 优先级 | 来源 | 用法 |
|---|---|---|
| 1 | 命令行 | `jxjy_download_cert.py 200 --study-id 31234` |
| 2 | 环境变量 | `set JXJY_STUDY_ID=31234` |
| 3 | 页面动态识别 | 自动从 `isStudyThisCourse(...,<ID>,...)` / `isContinueLearning(...)` / `studyID=` 提取 |
| 4 | 内置默认值 | `21037`（2026 实测值，换人换年度后可能不适用） |

> 排查：拉证失败且日志显示来源是「内置默认值」，多半就是这个 ID 不对。
> 让用户在浏览器打开学习中心 → 右键查看源码搜 `studyID=` 拿到真实值，用方式 1 或 2 指定即可。
3. 页面出现「下载」类链接 → 逐个点击触发浏览器下载（PDF/JPG/XML）。
4. 保存到 `继续教育证明/继续教育学习证明_YYYY-MM-DD.pdf`，并复制为项目根 `会计专业技术人员继续教育学习证明.pdf`。
5. 若页面返回「**未找到打印信息**」→ 该学习计划当前**尚未生成可打印证书**（多半计划仍在"进行中"，
   合格证需平台侧完结/刷新后才可打印，或 studyID 已变更）→ 退出码 4，持续轮询等待平台置为可打印。

**命令**：
```bash
cd "<项目>/.workbuddy"
"<venv>/Scripts/python.exe" jxjy_download_cert.py 200   # 200 = 达标且可打印前最多等待分钟
"<venv>/Scripts/python.exe" jxjy_download_cert.py 200 --study-id 31234   # 手动指定学习计划 ID
```
退出码：`0`=成功；`2`=登录失效；`3`=等待超时仍未拉到；`4`=达标但平台「未找到打印信息」（证书暂不可打印，待平台完结/刷新）。

**与刷课链路结合（推荐）**——登录窗口 + 刷课 + 达标自动拉证明一气呵成。已封装为三段链式脚本
`jxjy_chain_login_study_cert.sh`（登录窗口等待 → 检测到 `jxjy_login_success.flag` 即自动刷课 → 刷课结束自动拉证明）：
```bash
cd "<项目>/.workbuddy"
bash jxjy_chain_login_study_cert.sh 90 240 180
#   参数=登录窗口分钟  刷课时长分钟  证书轮询分钟
# 用户只需在弹窗里扫码/短信登录一次，后续全自动，agent 无需值守。
```
等效手写版（便于理解/调试）：
```bash
cd "<项目>/.workbuddy"
rm -f jxjy_login_success.flag
"<venv>/Scripts/python.exe" jxjy_login_window.py --wait 60 2>&1 | tee jxjy_login_window2.log
if [ -f jxjy_login_success.flag ]; then
  "<venv>/Scripts/python.exe" jxjy_daily_study.py 900 >> jxjy_study.log 2>&1
  "<venv>/Scripts/python.exe" jxjy_download_cert.py 30   # 刷完即拉证明（登录仍有效）
fi
```

> ⚠️ **证书可打印 ≠ 仅看学分**：学分 ≥90 只是必要条件，正保侧合格证还需该学习计划处于"可打印"状态
> （计划完结/平台刷新后）。若脚本报「未找到打印信息」(退出码 4)，说明平台侧暂未生成证书，需等计划完结
> 或用户到正保学习中心点「证书打印 / 申请合格证」触发，脚本会在轮询窗口内自动重试拉取。
> ⚠️ 浙里办 SSO 会话 **< 9 小时**，拉证明动作务必在刷课当天的登录窗口内完成（跨天会随登录失效而失败）。
> 🛠️ **课程收尾兜底（v1.6.3）**：个别课程媒体真实时长略小于播放器上报 `duration`，`ended` 事件不触发、`current` 卡在末尾不动（实测《我国会计服务市场监管体系研究》停在 26:06/26:39 整段 199 分钟不前进、0 学分入账）。`jxjy_daily_study.py` 现增加「卡在末尾(进度停滞 ≥3 次/约 60s) 按播完处理」兜底，避免整门课永远刷不完。

## 长跑守护：`jxjy_login_guard.py`（跨天/长会话必用）

**为什么需要**：浙里办 SSO 会话实测 **< 9 小时**（曾有 00:30 登录、09:00 即失效的实例）。
跨天 30 小时的长会话中途**必然**掉线，且掉线后脚本以 `status=error` 静默退出，
没人发现就会白等数小时。守护脚本把「发现 → 通知 → 恢复 → 接力」整条链路自动化。

```bash
# 标准用法：守到 2026-09-12 21:00，会话终点 20:45（接力时按距终点的剩余分钟数启动新会话）
python jxjy_login_guard.py --until "2026-09-12 21:00" --session-end "2026-09-12 20:45"

python jxjy_login_guard.py --status                  # 只打印一次状态，不守护（排障首选）
python jxjy_login_guard.py --dry-run --until ...     # 只记录将要执行的动作
```

巡检逻辑（默认每 3 分钟）：

1. 读 `jxjy_study.lock` 的 PID 判断刷课进程是否存活；存活则进入下一轮。
2. 进程已死时读 `jxjy_study_report.json`：
   - `status ∈ {all_courses_done, completed, done_no_more_courses}` → 全部刷完，守护退出；
   - `status=error` 且报告是 **60 分钟内**写的、错误含登录特征 → **登录态失效**，走救援；
   - 其他（`time_up` / 崩溃退出）→ 直接接力重启会话。
3. 进程存活但 `jxjy_study.log` 超过 `--hang-min`（默认 20 分钟）没有更新 → 判为卡死，杀进程树后接力
   （`--no-hang-kill` 可关闭该行为）。

**接力退避**（防止系统性故障时刷爆平台风控）：连续接力失败时**前两次立即重试**，之后按
**5/15/30/60 分钟逐级放大**；一旦观察到「会话存活且日志 5 分钟内有更新」，计数**立刻清零**。
因此正常的长跑接力不受影响，只在真的连续失败时才生效。
登录救援失败**不适用**这条退避，而是按 `--retry-min`（默认 10 分钟）固定节流 ——
那属于"等人工扫码"的正常等待，不是故障。

救援动作：调用 `jxjy_remote_login.py`
**先无头（`--headless`，锁屏/无人值守同样能截到二维码并邮件推送），失败再退化为有头窗口兜底**；
若持久化 profile 恰好仍在线，该脚本会**静默续期**、无需人工。
扫码成功后按「距 `--session-end` 的剩余分钟数」重启刷课会话。
失败则按 `--retry-min`（默认 10 分钟）节流后重试，避免邮件轰炸。

关键参数：`--until`（守护截止，不填 = 启动次日 03:00）、`--session-end`（会话终点，决定接力时长）、
`--interval`、`--hang-min`、`--retry-min`、`--wait-min`、`--no-login-rescue`、`--no-hang-kill`、`--dry-run`、`--status`。

⚠️ 守护只负责「保持一直有会话在跑」，**不负责关机**；关机仍由 `jxjy_auto_shutdown.py` 负责，两者独立进程。

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
- SSO_TOKEN 有效期短（实测 < 9 小时）。隔夜后 `jxjy_state.json` 大概率失效，刷课脚本进入学习中心会被踢到登录页（报告 status=error）。
- 处理：走「远程扫码登录」或「人工登录」重新生成登录态，再启动刷课。
- **跨天长会话请提前挂 `jxjy_login_guard.py`**（见「长跑守护」一节）：它能自动发现失效、推送二维码、
  扫码后自动接力重启会话；否则失效后到下一次巡检/人工发现，往往白等数小时。
- 排障一行命令：`python jxjy_login_guard.py --status`（一次看清进程/报告/日志/登录态新鲜度）。

### 5. 平台更换学习中心入口
- 平台曾把旧路径 `/ckmgr/ckmgrNews/golearncenterNew`（404）换成 `/front/golearncenterNew.html`。若再次 404，检查 `open_learning_center()` 里的入口 URL。

## 看板更新

刷课结束或用户查看时，同步看板数据：
1. `refresh_jxjy_after_session.py` 抓最新学分面板 → 写入 `jxjy_dashboard_data.json`。
   - 2026-09-11 修复：此脚本此前**只截图打印、并不落盘**（与文档不符）。现已补上写入逻辑，
     并内置**防冲突保护**——若 `jxjy_dashboard_data.json` 在 60 秒内被修改过（说明刷课进程正在实时写），
     则跳过写入只打印，避免两个进程同时写坏 JSON。
   - 学分解析优先用「学分进度」精确正则，失败才回落到表格行扫描。
2. `jxjy_dashboard_updater.py` 据 JSON 刷新 `.workbuddy/jxjy_dashboard.html` + 根目录 `综合看板.html`。
3. `jxjy_kanban_updater.py` 据 JSON 刷新根目录 `继续教育看板.html`（与 dashboard_updater 互补，确保三个看板全同步）。
4. 课程清单手动/脚本维护在 `jxjy_courses.json`。

> **重要**：12:00 中午刷新任务必须**同时跑两个 updater**，否则根目录的 `继续教育看板.html` 会停留在刷课结束时的旧版。
> 刷课进行中（09:00–23:00）时数据文件本就每 20 秒被刷课脚本刷新，中午刷新主要价值在于**补齐三个看板**。

看板核心指标口径：
- **已学习学分** = `total.got`（如 24.26）
- **待学习学分** = `total.need - total.got`（如 65.74）
- **即将学习学分** = 下一门待学课程的学分

> ⚠️ **「今日学分」基线陷阱**（2026-09-11 修复）：`save_dashboard_data()` 早期用「上次文件里的总分」当基线，
> 而刷课过程中会多次以 `overview=None` 调用它（开课时、每 20 秒更新讲次），此时 `total_got` 取自旧文件 →
> `today_got` 被算成 0，**第二次保存就把「今日 +x 学分」清零**。
> 现改为持久化 `day_key`（日期）+ `day_base`（当天起点学分）：同一天沿用 `day_base`，跨天才重置基线，负数则归零并重置。
> 排查「今日学分显示 0」时先看这两个字段是否正确。

> ⚠️ `综合看板.html` 里继续教育相关文案有**两处**需同步：底部 `auto-meta` 与「三大工作模块」里的 `module-desc`。
> 2026-09-11 修复前 `module-desc`（「每日 09:00 自动挂课 8 小时 · 已获 44.28/90 …」）长期未同步、残留旧数字；
> 已在 `jxjy_dashboard_updater.py` 中补上该正则替换，并把「8 小时」更正为实际的「14 小时」（840 分钟）。

## 配套自动化（每日中午刷新，可选）

刷课任务（每天 9:00 启动、跑 840 分钟）只在结束时刷新一次看板。但白天用户想"看一眼当前学分"，就要等到 0:00 之后——这不友好。

**解决：建一个独立的"中午刷新" automation 任务**，每天 12:00 自动跑一次，只抓数据不刷课（~30 秒完成），与刷课任务并行无干扰。

### 为什么必须独立任务（不能合并到刷课任务）

- 9:00 刷课任务是单一连续进程（840 分钟不中断）
- 在它内部塞"12:00 暂停刷课→刷新→继续"会破坏视频连续性，跳课风险高
- 独立任务 12:00 跑 ~30 秒就退出，刷课进程无感知

### 一键创建命令（用 WorkBuddy 工具）

让智能体执行以下 prompt：

```
请帮我在当前 WorkBuddy 里创建一个定时自动化任务，参数如下：
- 任务名：浙江会计继续教育看板每日中午刷新
- 状态：ACTIVE
- 频率：FREQ=DAILY;BYHOUR=12;BYMINUTE=0
- 工作目录：<你的项目目录>\.workbuddy
- 任务 prompt：

  运行浙江会计继续教育看板中午刷新：
  1. 使用隔离 venv 的 Python 解释器 <隔离venv>\Scripts\python.exe
  2. 工作目录切换到工作目录参数指定的位置
  3. 执行命令：python refresh_jxjy_after_session.py
     - 该脚本会用 jxjy_state.json 的登录态打开学习中心 → 抓取最新学分 → 写入 jxjy_dashboard_data.json
  4. 然后**同时跑两个 updater**确保三个看板全部同步：
     - python jxjy_dashboard_updater.py（刷新 .workbuddy/jxjy_dashboard.html 和根目录 综合看板.html）
     - python jxjy_kanban_updater.py（刷新根目录 继续教育看板.html）
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
<隔离venv>/Scripts/python.exe
```
依赖：`playwright`、`PIL`。邮件推送用标准库 `smtplib`/`email`。

## 调试脚本

- `jxjy_remote_login.py --demo`：只截一次二维码验证（不进入循环）；加 `--headless` 可验证锁屏场景下的救援能力。
- `jxjy_login_guard.py --status`：一行看清进程 / 报告 / 日志 / 登录态新鲜度，排障首选。
- `jxjy_pubcourse_list.py`：枚举全部公需课（分类 / 名称 / 时长 / 学分 / 状态），挑课时用。

> 注：早期版本文档曾列过 jxjy_chain_diag / jxjy_course_diag / jxjy_video_diag 三个调试脚本，
> 但它们在仓库中从未存在；对应的 cookie、登录态、video 链路排查请改用上面三条等价命令。

### 救援链路自检（跨天长跑前必做，约 3 分钟）

长跑前建议跑一遍，确认"掉线时真的救得回来"（2026-09-11 全部实测通过）：

1. **邮件通道**（不真发信，只验证 SSL + 授权码）：
   ```python
   import smtplib, json
   cfg = json.load(open('jxjy_mail_config.json', encoding='utf-8'))
   s = smtplib.SMTP_SSL(cfg.get('smtp_host','smtp.qq.com'), int(cfg.get('smtp_port',465)), timeout=30)
   s.login(cfg['from_addr'], cfg['pass']); print(s.noop()); s.quit()   # 期望 250 OK
   ```
2. **二维码截图**：`python jxjy_remote_login.py --demo --headless` → 检查 `jxjy_login_qr.png`
   是否为 ~9 KB 的**真二维码**（而非整页兜底截图）。无头可用 = **锁屏时也能救援**。
3. **邮件报文构造**（用假 SMTP，不真发信）：把 `jxjy_remote_login.smtplib.SMTP_SSL` 替换为记录型假类，
   调 `send_qr_email('jxjy_login_qr.png')`，再用 `email.message_from_string` 解析 ——
   应得到 3 段 MIME、Subject「继续教育登录二维码」、附件 `login_qr.png`（`image/png`，
   解码后字节数与原图一致）＝ 报文构造无误，只差网络投递。
4. **接力启动**：在**隔离目录**放一份 `jxjy_login_guard.py` + `jxjy_daily_study.py`，调用
   `launch_study(5, '测试')` —— 期望子进程被分离拉起、自行拿到 `jxjy_study.lock`、日志写进
   该目录的 `jxjy_study.log`（隔离目录没有 `jxjy_state.json`，故会打印"未找到登录态文件"后干净退出并释放锁）。
   因为锁与状态文件都在隔离目录，**这样测不会干扰真实会话**。

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
