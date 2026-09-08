# -*- coding: utf-8 -*-
"""
浙江会计继续教育每日自动刷课脚本。

功能：
1. 从 jxjy_state.json 恢复登录态
2. 进入正保会计网校学习中心
3. 自动找到当前未完成的课程并播放
4. 持续挂视频，定时检查播放状态、关闭弹窗、处理暂停
5. 视频结束后自动进入下一课程/下一讲
6. 输出学习进度报告

用法：
  python jxjy_daily_study.py [分钟数]   # 默认运行 60 分钟
"""
import os, sys, json, time, datetime, traceback, re, subprocess
from playwright.sync_api import sync_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
REPORT_FILE = os.path.join(BASE, "jxjy_study_report.json")
LOG_FILE = os.path.join(BASE, "jxjy_study.log")
DASH_DATA_FILE = os.path.join(BASE, "jxjy_dashboard_data.json")
UPDATER_FILE = os.path.join(BASE, "jxjy_dashboard_updater.py")

DEFAULT_MINUTES = 480

# 刷完自动关机功能已停用（默认不会关闭计算机）。
# 如需临时关机，请在操作系统层面单独执行 shutdown 命令。

# 浙江会计继续教育年度学分要求
CREDIT_REQUIREMENT = {"total": 90.0, "major": 60.0, "public": 18.0}


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def save_report(data):
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_credit_overview(page):
    """从学习中心页面抓取 2026 年度学分总览。"""
    try:
        page.wait_for_selector("table tr", timeout=15000)
        rows = page.locator("table tr").all()
        for row in rows:
            try:
                text = row.inner_text().replace("\n", " ").replace("\t", " ")
            except Exception:
                continue
            if "2026" not in text:
                continue
            # 提取数字：年度 总学分 公需学分 专业学分
            nums = re.findall(r"\d+\.?\d*", text)
            if len(nums) >= 4:
                return {
                    "year": 2026,
                    "total_got": float(nums[1]),
                    "public_got": float(nums[2]),
                    "major_got": float(nums[3]),
                }
    except Exception as e:
        log(f"抓取学分总览失败: {e}")
    return None


def load_dashboard_data():
    """加载现有看板数据。"""
    if not os.path.exists(DASH_DATA_FILE):
        return {}
    try:
        with open(DASH_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_dashboard_data(overview, current_course=None, current_section=None, today_minutes=0):
    """保存/更新继续教育看板数据文件。"""
    try:
        old = load_dashboard_data()
        total_need = CREDIT_REQUIREMENT["total"]
        major_need = CREDIT_REQUIREMENT["major"]
        pub_need = CREDIT_REQUIREMENT["public"]
        total_got = overview.get("total_got", 0.0) if overview else old.get("total", {}).get("got", 0.0)
        major_got = overview.get("major_got", 0.0) if overview else old.get("major", {}).get("got", 0.0)
        pub_got = overview.get("public_got", 0.0) if overview else old.get("public", {}).get("got", 0.0)

        # 今日已获取学分：用上次记录值与当前值的差额（首次运行则为 0）
        last_total = old.get("total", {}).get("got", total_got)
        today_got = round(total_got - last_total, 2)
        if today_got < 0:
            today_got = 0.0

        data = {
            "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "year": 2026,
            "student": old.get("student", "学员"),
            "total": {"got": total_got, "need": total_need},
            "major": {"got": major_got, "need": major_need},
            "public": {"got": pub_got, "need": pub_need},
            "today_got": today_got,
            "today_got_note": "较上次记录增加",
            "today_minutes": today_minutes or old.get("today_minutes", 0),
            "current_course": current_course or old.get("current_course", ""),
            "current_section": current_section or old.get("current_section", ""),
            "schedule": old.get("schedule", "每日 09:00 · 8 小时"),
            "source": old.get("source", "学习中心页面 + 刷课日志"),
        }
        with open(DASH_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"看板数据已保存: {DASH_DATA_FILE}")
    except Exception as e:
        log(f"保存看板数据失败: {e}")


def update_dashboard_html():
    """调用 updater 脚本刷新本地 HTML 看板。"""
    try:
        if not os.path.exists(UPDATER_FILE):
            return
        subprocess.run(
            [sys.executable, UPDATER_FILE, DASH_DATA_FILE],
            cwd=BASE,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        log("本地 HTML 看板已刷新")
    except Exception as e:
        log(f"刷新 HTML 看板失败: {e}")


def close_annoying(page):
    """关闭弹窗、点击继续学习等可能中断播放的元素。"""
    try:
        # 常见中断按钮：继续学习、继续播放、确定、知道了、下一讲、下一节
        texts = ["继续学习", "继续播放", "确定", "知道了", "继续", "下一讲", "下一节", "关闭", "下次再说"]
        for txt in texts:
            try:
                btns = page.locator(f"button:has-text('{txt}'):visible, a:has-text('{txt}'):visible").all()
                for btn in btns:
                    try:
                        if btn.is_visible():
                            btn.click(timeout=2000)
                            log(f"[click] {txt}")
                            time.sleep(0.5)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as e:
        log(f"[close_annoying err] {e}")


def video_status(page):
    """读取 video 元素状态。NaN 一律归零，防止下游格式化崩溃。"""
    try:
        st = page.evaluate("""() => {
            const v = document.querySelector('video');
            if (!v) return null;
            return {
                currentTime: v.currentTime,
                duration: v.duration,
                paused: v.paused,
                ended: v.ended,
                muted: v.muted,
                volume: v.volume,
                readyState: v.readyState,
                playbackRate: v.playbackRate,
                src: v.src ? v.src.slice(0, 80) : ''
            };
        }""")
        if st:  # JS 返回的 NaN 经 JSON 序列化会变 None 或非法值，统一兜底
            for k in ("currentTime", "duration"):
                v = st.get(k)
                if v is None or v != v:
                    st[k] = 0
        return st
    except Exception as e:
        return {"error": str(e)}


def ensure_playing(page):
    """确保视频在播放。"""
    try:
        page.evaluate("""() => {
            const v = document.querySelector('video');
            if (v) {
                v.muted = true;
                if (v.paused) { v.play(); }
                v.playbackRate = 1.0;
            }
        }""")
    except Exception as e:
        log(f"[ensure_playing err] {e}")


def persist_state(ctx, path=STATE_FILE):
    """把当前 context 的 storage_state 写回文件，持久化正保等动态 cookie。"""
    try:
        state = ctx.storage_state()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        log(f"登录态已刷新保存: {path}")
    except Exception as e:
        log(f"保存登录态失败: {e}")


def click_next_section(play_page):
    """在当前课程页点击下一讲（第02讲/第03讲...），返回是否成功。"""
    try:
        links = play_page.locator('a.akuo:visible').all()
        if not links:
            return False
        current_idx = -1
        for i, link in enumerate(links):
            cls = (link.get_attribute('class') or '').lower()
            if 'active' in cls or 'current' in cls or 'on' in cls:
                current_idx = i
                break
        next_idx = current_idx + 1 if current_idx >= 0 else 1
        if next_idx >= len(links):
            return False
        nxt = links[next_idx]
        txt = nxt.inner_text().strip()
        nxt.click(timeout=5000)
        log(f"点击下一讲: {txt}")
        for _ in range(25):
            play_page.wait_for_timeout(2000)
            try:
                if play_page.evaluate("() => document.querySelectorAll('video').length") > 0:
                    log("下一讲视频已加载")
                    return True
            except Exception:
                pass
        return False
    except Exception as e:
        log(f"点击下一讲失败: {e}")
    return False


def open_learning_center(ctx):
    """进入浙江继续教育学习中心 → 点继续学习进选课页 → 点正保继续学习，返回正保学习中心页面。

    注意：选课页 goSelectSchoolNew.html 直接访问会被服务端重定向回首页，
    必须先经过学习中心 golearncenterNew.html 的"继续学习"按钮进入（带 referer）。
    """
    page = ctx.new_page()

    # 第一步：进入学习中心（学分总览页），带重试防止偶发重定向回首页
    # 第一阶段：直接访问，绕过"首页"中转；如被重定向到政务网登录页，则用方案 B
    for attempt in range(4):
        page.goto("https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if "golearncenterNew" in page.url:
            break
        log(f"学习中心被重定向到 {page.url}，第 {attempt + 1} 次重试")
    # 兜底：如果最终仍被踢到政务网登录页，先访问首页建立会话，再跳转学习中心
    if "user.zjzwfw.gov.cn" in page.url:
        log("登录态过期，先访问首页建立会话")
        page.goto("https://jxjy.czt.zj.gov.cn/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        # 从首页跳学习中心（带 referer）
        page.goto("https://jxjy.czt.zj.gov.cn/front/golearncenterNew.html",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
    log(f"学习中心已打开: {page.url}")

    # 抓取 2026 年度学分总览并保存（用于看板展示）
    try:
        overview = fetch_credit_overview(page)
        if overview:
            log(f"学分总览: 总{overview['total_got']} / 专业{overview['major_got']} / 公需{overview['public_got']}")
            save_dashboard_data(overview)
    except Exception as e:
        log(f"记录学分总览时出错: {e}")

    # 第二步：点击"继续学习"进入选课页（网校列表）
    # 兼容：如果不在学习中心，仍被踢到首页/政务网，截图后抛错以便排错
    if "golearncenterNew" not in page.url:
        shot = os.path.join(BASE, f"jxjy_fail_no_center_{datetime.datetime.now():%H%M%S}.png")
        try:
            page.screenshot(path=shot, full_page=True)
        except Exception:
            pass
        log(f"未能进入学习中心（停留在 {page.url}），截图 {shot}")
        raise RuntimeError(f"未能进入学习中心页面: {page.url}")
    btn1 = page.locator('a.btn-success:has-text("继续学习"):visible').first
    btn1.wait_for(state="visible", timeout=15000)
    btn1.click()
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5000)
    log(f"选课页已打开: {page.url}")

    # 第三步：点击"正保会计网校"所在行的"继续学习"按钮，进入正保学习中心。
    # 选课页有多个网校，每个网校一行都有"继续学习"，必须精确限定到正保这一行，
    # 否则可能点到其他未报名网校，导致 cookie 和课程列表错误。
    page.locator('text=正保会计网校').wait_for(state="visible", timeout=15000)
    zhengbao_row = page.locator('div.row:has-text("正保会计网校")').first
    # 兼容可能的 DOM 结构变化：div.row / div.panel / tr / 通用容器
    if not zhengbao_row.count():
        for sel in ('div.panel:has-text("正保会计网校")', 'tr:has-text("正保会计网校")',
                    'div:has(> :has-text("正保会计网校"))'):
            zhengbao_row = page.locator(sel).first
            if zhengbao_row.count():
                break
    if not zhengbao_row.count():
        raise RuntimeError("选课页未找到 正保会计网校 所在容器")
    btn2 = zhengbao_row.locator('a:has-text("继续学习"), button:has-text("继续学习")').first
    btn2.wait_for(state="visible", timeout=15000)
    with ctx.expect_page(timeout=60000) as info:
        btn2.click()
    study = info.value
    study.wait_for_load_state("domcontentloaded")
    study.wait_for_timeout(5000)
    log(f"正保学习中心已打开: {study.url}")
    # 此时正保 cookie 已建立，持久化登录态以便下次复用
    persist_state(ctx)
    return study


def is_course_row_completed(row_text):
    """根据课程行文本判断该课程学分是否已经拿满。

    判断依据（任一满足即认为已完成）：
    1. 已完成/要求学分：已完成 >= 要求学分（如 3.34/3.34 学分）
    2. 剩余学习时长为 0（如 0/150 分钟）
    3. 学习状态列包含"完成学习"或"已完成"
    """
    row_text = row_text.replace("\n", " ").replace("\t", " ")

    # 1. 学分已满
    m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*学分', row_text)
    if m:
        try:
            got = float(m.group(1))
            need = float(m.group(2))
            if need > 0 and got >= need - 0.01:
                return True, f"学分已满 {got}/{need}"
        except (ValueError, TypeError):
            pass

    # 2. 剩余时长为 0（已完成整个课程）
    m2 = re.search(r'(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*分钟', row_text)
    if m2:
        try:
            left = float(m2.group(1))
            if left <= 0.01:
                return True, "剩余时长为 0"
        except (ValueError, TypeError):
            pass

    # 3. 学习状态文字兜底
    if "完成学习" in row_text or "已完成" in row_text:
        return True, "状态显示已完成"

    return False, ""


def find_current_course(study_page, skip=None):
    """在学习中心选择要播放的课程行。

    选择优先级：
    1. 「继续学习」按钮 + 未完成 → in-progress，最优先（避免重启后切到新课）
    2. 「开始学习」按钮 + 未完成 → 新课，回退选项
    3. 已完成 / 在 skip 列表里的行一律跳过

    课程表格数据由 AJAX 异步加载，domcontentloaded 后可能需要数秒才渲染，
    因此这里带重试等待，避免过早判定"没有课程"。
    skip: list[str]，包含任意关键字的行将被跳过（用于跳过打不开的课程）。
    """
    def _pick(button_keyword, label):
        for _ in range(8):
            rows = study_page.locator("table tr")
            if rows.count() > 0:
                for i in range(rows.count()):
                    row = rows.nth(i)
                    try:
                        text = row.inner_text()
                    except Exception:
                        continue
                    if button_keyword not in text:
                        continue
                    if skip and any(s in text for s in skip):
                        continue
                    completed, reason = is_course_row_completed(text)
                    if completed:
                        log(f"跳过已完成课程 ({reason}) [{label}]: {text[:80].replace(chr(10), ' ')}")
                        continue
                    return row
            study_page.wait_for_timeout(3000)
        return None

    row = _pick("继续学习", "in-progress")
    if row is not None:
        return row
    return _pick("开始学习", "new")


def enter_course(study_page, ctx, skip=None):
    """从学习中心点击课程行的继续学习/开始学习，返回 (播放页, 课程行文本)。

    兼容三种打开方式：新标签页 / 学习中心本页跳转 / 复用已有标签页。
    """
    row = find_current_course(study_page, skip=skip)
    if not row:
        return None, None
    text = row.inner_text().replace("\n", " ")
    log(f"选中课程: {text[:80]}")
    link = row.locator('a:has-text("继续学习"), a:has-text("开始学习")').first
    before_urls = set()
    try:
        before_urls = {pg.url for pg in ctx.pages}
    except Exception:
        pass
    before_study_url = study_page.url

    # 方式1：新开标签页（常规情况）
    try:
        with ctx.expect_page(timeout=30000) as info:
            try:
                link.click(timeout=10000)
            except Exception as ce:
                log(f"点击课程链接失败: {ce}")
                return None, text
        play = info.value
        play.wait_for_load_state("domcontentloaded", timeout=30000)
        play.wait_for_timeout(3000)
        log(f"进入课程页(新标签页): {play.url}")
        return play, text
    except Exception:
        log("30秒内未等到新标签页，尝试识别同页跳转/已有页复用…")

    # 方式2：学习中心本页跳转；方式3：复用已有标签页导航到课程页
    for _ in range(15):
        study_page.wait_for_timeout(2000)
        try:
            if study_page.url != before_study_url:
                study_page.wait_for_load_state("domcontentloaded", timeout=15000)
                log(f"进入课程页(本页跳转): {study_page.url}")
                return study_page, text
            for pg in ctx.pages:
                u = pg.url
                if (u and u not in before_urls and "courseware" in u
                        and "golearncenter" not in u and "goSelectSchool" not in u):
                    try:
                        pg.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    log(f"进入课程页(复用页面): {u}")
                    return pg, text
        except Exception:
            pass
    log(f"等待课程页打开超时，跳过该课程: {text[:60]}")
    return None, text


def wait_for_video(page, timeout_seconds=50):
    """在当前页面内等待 video 元素出现，或 URL 变为视频播放页。"""
    for _ in range(timeout_seconds // 2):
        try:
            if 'VideoPlayH5' in page.url:
                if page.evaluate("() => document.querySelectorAll('video').length") > 0:
                    return True
            elif page.evaluate("() => document.querySelectorAll('video').length") > 0:
                return True
        except Exception:
            pass
        page.wait_for_timeout(2000)
    return False


def start_video(play_page):
    """在课程页点击"继续学习/开始学习"大按钮，或点击章节目录，进入视频播放。"""
    try:
        # 1. 优先尝试"继续学习/开始学习"大按钮（已学课程常见）
        selectors = [
            'a.continue_studyNew',
            'a:has-text("开始学习")',
            'a:has-text("继续学习")',
            'button:has-text("开始学习")',
            'button:has-text("继续学习")',
        ]
        for sel in selectors:
            try:
                btn = play_page.locator(f'{sel}:visible').first
                if btn.count() > 0:
                    btn.click(timeout=5000)
                    log(f"点击学习大按钮 ({sel})")
                    if wait_for_video(play_page):
                        log("大按钮进入视频成功")
                        return play_page
                    break
            except Exception:
                continue

        # 2. 新版课程页（0/117分钟）是章节目录结构，没有大按钮，需点某一讲进入
        zhang = None
        for txt in ["第01讲", "第1讲", "第一讲"]:
            z = play_page.locator(f'a:has-text("{txt}"):visible').first
            if z.count() > 0:
                zhang = z; break
        if not zhang:
            z = play_page.locator('a.akuo:visible').first
            if z.count() > 0:
                zhang = z
        if zhang:
            zhang.click(timeout=5000)
            log("点击课程章节（第01讲）进入视频")
            if wait_for_video(play_page):
                log("章节进入视频成功")
                return play_page

        log("未找到学习入口或视频加载失败")
    except Exception as e:
        log(f"进入视频失败: {e}")
    return play_page


def main():
    minutes = DEFAULT_MINUTES
    if len(sys.argv) > 1:
        try:
            minutes = int(sys.argv[1])
        except ValueError:
            pass
    log(f"=== 浙江会计继续教育每日刷课启动，目标运行 {minutes} 分钟 ===")

    if not os.path.exists(STATE_FILE):
        log("错误：未找到登录态文件 jxjy_state.json，请先运行 jxjy_login_window.py 登录")
        sys.exit(1)

    end_time = time.time() + minutes * 60
    report = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_minutes": minutes,
        "courses": [],
        "status": "running"
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=STATE_FILE, viewport={"width":1600,"height":1000})

        try:
            study_page = open_learning_center(ctx)
            skipped_courses = []   # 打不开的课程，跳过避免死循环
            entry_fail = 0         # 连续进入课程失败计数

            while time.time() < end_time:
                # 学习中心本页被跳转走时（同页进入课程），重新打开学习中心
                try:
                    if "learningCenter" not in study_page.url:
                        study_page = open_learning_center(ctx)
                except Exception:
                    study_page = open_learning_center(ctx)

                try:
                    play_page, row_text = enter_course(study_page, ctx, skip=skipped_courses)
                except Exception as e:
                    log(f"进入课程异常: {e}")
                    play_page, row_text = None, None

                if not play_page:
                    if row_text:
                        # 该课程打不开，记入跳过名单并重试下一个
                        key = row_text.split("\t")[0].strip()[:30]
                        skipped_courses.append(key)
                        entry_fail += 1
                        log(f"课程 [{key}] 无法进入，已加入跳过名单")
                        if entry_fail >= 8:
                            log("连续 8 门课程无法进入，结束今日任务")
                            report["status"] = "too_many_entry_failures"
                            break
                        continue
                    log("学习中心没有可继续学习的课程，今日任务完成")
                    report["status"] = "done_no_more_courses"
                    break
                entry_fail = 0

                play_page = start_video(play_page)
                course_url = play_page.url
                course_title = play_page.title()
                # 清理标题中的网校后缀
                course_title_clean = course_title.replace("-正保会计网校", "").replace("-中华会计网校", "").strip()
                log(f"开始播放: {course_title} | {course_url}")

                # 更新看板当前课程
                try:
                    save_dashboard_data(None, current_course=course_title_clean)
                except Exception:
                    pass

                course_entry = {
                    "title": course_title,
                    "url": course_url,
                    "start": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "end": None,
                    "watched_seconds": 0
                }
                last_t = time.time()
                last_ct = None

                # 循环监控当前课程播放
                while time.time() < end_time:
                    close_annoying(play_page)
                    ensure_playing(play_page)
                    st = video_status(play_page)
                    now = time.time()
                    elapsed = now - last_t
                    last_t = now

                    if st and not st.get("error"):
                        current = st.get("currentTime", 0)
                        duration = st.get("duration", 0)
                        paused = st.get("paused", True)
                        ended = st.get("ended", False)
                        course_entry["watched_seconds"] += elapsed

                        # 每隔一段时间更新看板当前讲次进度
                        try:
                            section_num = "第 1 讲"
                            # 从 URL 或标题中推断讲次
                            url_lower = course_url.lower()
                            if "video" in url_lower:
                                m = re.search(r'video[^/]*/(\d+)', url_lower)
                                if m:
                                    section_num = f"第 {int(m.group(1))} 讲"
                            current_section = f"{section_num} · 约 {fmt(current)} / {fmt(duration)}"
                            save_dashboard_data(None, current_section=current_section, today_minutes=sum(c.get("watched_seconds", 0) for c in report["courses"]) // 60)
                        except Exception:
                            pass

                        log_msg = f"  {course_title[:20]} | current={fmt(current)}/{fmt(duration)} paused={paused} ended={ended}"
                        log(log_msg)

                        if ended or (duration > 0 and current >= duration - 5):
                            log("当前视频已播完")
                            course_entry["end"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            report["courses"].append(course_entry)
                            save_report(report)
                            # 先尝试同一课程下一讲
                            if click_next_section(play_page):
                                course_url = play_page.url
                                course_title = play_page.title()
                                log(f"开始播放下一讲: {course_title} | {course_url}")
                                course_entry = {
                                    "title": course_title,
                                    "url": course_url,
                                    "start": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    "end": None,
                                    "watched_seconds": 0
                                }
                                last_t = time.time()
                                last_ct = None
                                continue
                            # 否则刷新学习中心，看是否有新课程
                            log("准备进入下一课程")
                            try:
                                if "learningCenter" in study_page.url:
                                    study_page.reload(wait_until="domcontentloaded", timeout=30000)
                                    study_page.wait_for_timeout(3000)
                                else:
                                    # 同页跳转场景：学习中心页已被课程页占用，重新打开
                                    study_page = open_learning_center(ctx)
                            except Exception as e:
                                log(f"刷新学习中心失败: {e}")
                                try:
                                    study_page = open_learning_center(ctx)
                                except Exception as e2:
                                    log(f"重新打开学习中心失败: {e2}")
                            break

                        last_ct = current
                    else:
                        log(f"  未检测到 video 元素或出错: {st}")

                    # 每 20 秒检查一次
                    time.sleep(20)
                else:
                    # 时间到了
                    course_entry["end"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    report["courses"].append(course_entry)
                    report["status"] = "time_up"
                    log("达到设定运行时长，退出")
                    break

        except Exception as e:
            log(f"运行异常: {e}\n{traceback.format_exc()}")
            report["status"] = "error"
            report["error"] = str(e)
        finally:
            save_report(report)
            # 结束时刷新看板数据与 HTML
            try:
                today_seconds = sum(c.get("watched_seconds", 0) for c in report.get("courses", []))
                save_dashboard_data(None, today_minutes=today_seconds // 60)
                update_dashboard_html()
            except Exception as e:
                log(f"结束时刷新看板失败: {e}")
            try:
                ctx.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            log(f"=== 今日刷课结束，报告保存至 {REPORT_FILE} ===")
            # 刷完自动关机功能已停用——不再触发操作系统关机。
            # 保持浏览器/上下文清理与日志记录，照常退出。


def fmt(seconds):
    """秒数格式化为 mm:ss（NaN/None/负数一律返回 00:00，防止崩溃）"""
    try:
        if seconds is None or seconds != seconds or seconds < 0:  # seconds != seconds 即 NaN
            return "00:00"
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"
    except (TypeError, ValueError):
        return "00:00"


if __name__ == "__main__":
    main()
