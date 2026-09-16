# -*- coding: utf-8 -*-
"""
首次使用向导 —— 生成 jxjy_config.json

用法：
  python jxjy_setup.py            # 交互式问答
  python jxjy_setup.py --yes      # 全部用默认值，不问（批量/无人值守场景）
  python jxjy_setup.py --show     # 只打印当前配置，不修改

关于「账号密码」：
  浙江省继续教育走浙里办 / 浙江政务服务网 SSO，只能扫码或短信验证码登录，
  平台没有开放账密接口。本工具从头到尾不接触、不存储任何账号密码 —— 这是
  安全边界，不是功能缺失。首次登录只需跑一次登录窗口扫码，之后凭证保存在
  本地 jxjy_state.json（切勿拷贝给别人，共用会互踢下线）。
"""
import os
import sys
import json
import datetime

import jxjy_conf as CONF

BASE = CONF.BASE
CONFIG_FILE = CONF.CONFIG_FILE
STATE_FILE = os.path.join(BASE, "jxjy_state.json")
MAIL_FILE = os.path.join(BASE, "jxjy_mail_config.json")

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
except Exception:
    pass


def ask(prompt, default, cast=str):
    """带默认值的提问；直接回车采用默认值。"""
    raw = input(f"{prompt}  [默认: {default}] > ").strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except Exception:
        print(f"  输入无效，采用默认值 {default}")
        return default


def ask_bool(prompt, default=True):
    tip = "y/n" if default is None else ("Y/n" if default else "y/N")
    raw = input(f"{prompt} ({tip}) > ").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "是", "1", "true")


def show_current():
    if not os.path.exists(CONFIG_FILE):
        print("尚无配置文件，当前使用内置默认值：")
    print("  " + CONF.summary())
    print(f"  配置文件: {CONFIG_FILE}")
    print(f"  登录凭证: {'已生成 ✅' if os.path.exists(STATE_FILE) else '未生成 ❌（需扫码登录）'}")
    print(f"  邮件通知: {'已配置 ✅' if os.path.exists(MAIL_FILE) else '未配置'}")


def build_config(interactive=True):
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}
    else:
        cur = {}

    base = json.loads(json.dumps(CONF.DEFAULTS))
    CONF._deep_merge(base, cur)

    this_year = datetime.datetime.now().year

    if not interactive:
        base["year"] = this_year
        return base

    print("=" * 62)
    print("浙江会计继续教育 自动刷课 —— 首次使用向导")
    print("=" * 62)
    print()
    print("平台：浙江省（jxjy.czt.zj.gov.cn）+ 正保会计网校")
    print("登录：浙里办 / 浙江政务服务网 扫码，无需账号密码")
    print()

    print("—— 学习年度 ——")
    print(f"  跨年补学请填往年（例：2027 年补 2026 年度则填 2026）")
    base["year"] = ask("学习年度", this_year, int)

    print()
    print("—— 学分目标 ——")
    print("  浙江默认：总 90（专业课 ≥60、公需课 ≥18）")
    base["credit"]["total"] = ask("总学分目标", base["credit"]["total"], float)
    base["credit"]["major"] = ask("专业课学分要求", base["credit"]["major"], float)
    base["credit"]["public"] = ask("公需课学分要求", base["credit"]["public"], float)

    print()
    print("—— 运行参数 ——")
    print("  单次上限=一次连着刷多久后收工；未达标第二天继续，不会丢进度")
    base["study"]["max_minutes_per_run"] = ask(
        "单次刷课时长上限（分钟）", base["study"]["max_minutes_per_run"], int)
    base["study"]["login_wait_minutes"] = ask(
        "登录窗口最长等待（分钟）", base["study"]["login_wait_minutes"], int)
    base["study"]["cert_wait_minutes"] = ask(
        "达标的拉证书轮询上限（分钟）", base["study"]["cert_wait_minutes"], int)

    print()
    print("—— 达标收尾 ——")
    base["finish"]["download_cert"] = ask_bool("达标后自动下载学习证明 PDF？",
                                               base["finish"]["download_cert"])
    if base["finish"]["download_cert"]:
        base["finish"]["auto_cleanup"] = ask_bool(
            "结算后允许无人值守自动清理？（选 N 则每次先给你过目再清）", False)
    return base


def main():
    args = [a.lower() for a in sys.argv[1:]]

    if "--show" in args:
        show_current()
        return 0

    interactive = "--yes" not in args and "-y" not in args

    cfg = build_config(interactive)

    # 自动清理必须建立在先下载证明之上，否则白刷
    if cfg["finish"]["auto_cleanup"] and not cfg["finish"]["download_cert"]:
        print("[提示] 未开启自动下载证明，已强制关闭自动清理（避免没拿证就清）")
        cfg["finish"]["auto_cleanup"] = False

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    CONF.load(force=True)

    print()
    print("=" * 62)
    print(f"配置已保存到: {CONFIG_FILE}")
    print("  " + CONF.summary())
    print(f"  达标拉证: {'是' if cfg['finish']['download_cert'] else '否'}"
          f"  |  自动清理: {'是' if cfg['finish']['auto_cleanup'] else '否（会先问你）'}")
    print("=" * 62)
    print()
    print("下一步 —— 只需做一次：")
    print("  运行登录窗口扫码：python jxjy_login_window.py --wait 90")
    print("  之后即可一键闭环：python jxjy_full_run.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
