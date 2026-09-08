# -*- coding: utf-8 -*-
"""
更新独立「继续教育看板.html」的内嵌数据。
数据来源：jxjy_dashboard_data.json（汇总）+ jxjy_courses.json（课程清单）。

用法：
  python jxjy_kanban_updater.py
"""
import os, json, re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WB = os.path.join(BASE, ".workbuddy")
DATA_FILE = os.path.join(WB, "jxjy_dashboard_data.json")
COURSES_FILE = os.path.join(WB, "jxjy_courses.json")
KANBAN = os.path.join(BASE, "继续教育看板.html")


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_kanban_data():
    d = load(DATA_FILE)
    c = load(COURSES_FILE)
    return {
        "updated_at": d.get("updated_at", ""),
        "student": d.get("student", ""),
        "year": d.get("year", 2026),
        "total": d.get("total", {"got": 0, "need": 90}),
        "major": d.get("major", {"got": 0, "need": 60}),
        "public": d.get("public", {"got": 0, "need": 18}),
        "today_got": d.get("today_got", 0.0),
        "current_course": d.get("current_course", ""),
        "current_section": d.get("current_section", ""),
        "schedule": d.get("schedule", "每日 09:00 · 8 小时"),
        "completed": c.get("completed", []),
        "in_progress": c.get("in_progress", {}),
        "upcoming": c.get("upcoming", []),
    }


def main():
    data = build_kanban_data()
    with open(KANBAN, "r", encoding="utf-8") as f:
        html = f.read()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    new_html, n = re.subn(
        r'<script type="application/json" id="jxjy-data">.*?</script>',
        '<script type="application/json" id="jxjy-data">\n' + payload + '\n</script>',
        html, count=1, flags=re.S
    )
    if n == 0:
        print("警告：未匹配到看板数据块")
        return
    with open(KANBAN, "w", encoding="utf-8") as f:
        f.write(new_html)
    print("已更新看板:", KANBAN)


if __name__ == "__main__":
    main()
