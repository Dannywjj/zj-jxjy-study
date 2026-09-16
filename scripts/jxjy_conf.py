# -*- coding: utf-8 -*-
"""
统一配置读取层（zj-jxjy-study）

优先级：
    jxjy_config.json  >  环境变量  >  内置默认值

设计目标：
- 没有 jxjy_config.json 时行为与旧版完全一致，存量工作流不受影响
- 所有可调项集中在一处，新使用者跑一次 jxjy_setup.py 即可，无需改代码
"""
import os
import json
import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE, "jxjy_config.json")

DEFAULTS = {
    # 平台地区。当前仅浙江省可用；其他省份需自行适配选择器与 URL
    "province": "zhejiang",
    # 学习年度。null = 跟随当前自然年
    "year": None,
    # 学分要求
    "credit": {"total": 90.0, "major": 60.0, "public": 18.0},
    # 运行参数
    "study": {
        "max_minutes_per_run": 480,   # 单次刷课最长分钟
        "login_wait_minutes": 90,     # 登录窗口最长等待分钟
        "cert_wait_minutes": 180,     # 拉证书轮询最长等待分钟
    },
    # 达标收尾
    "finish": {
        "download_cert": True,        # 达标后自动拉学习证明
        "auto_cleanup": False,        # 确认无误后自动清理（False = 每次都问）
        "reset_state_after_cleanup": True,  # 清理后复位，便于下一年直接用
    },
    # 远程登录通知（登录态过期时邮件推送二维码）
    "notify": {"smtp_enabled": False},
}

_cache = None


def _deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst


def load(force=False):
    """读取配置。首次调用后缓存，force=True 强制重读。"""
    global _cache
    if _cache is not None and not force:
        return _cache
    cfg = json.loads(json.dumps(DEFAULTS))

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                _deep_merge(cfg, json.load(f))
        except Exception as e:
            print(f"[conf] jxjy_config.json 解析失败({e})，回落默认值")

    # 环境变量覆盖（便于临时改年度，不必动配置文件）
    env_year = os.environ.get("JXJY_YEAR")
    if env_year and str(env_year).isdigit():
        cfg["year"] = int(env_year)

    if cfg.get("year") is None:
        cfg["year"] = datetime.datetime.now().year

    _cache = cfg
    return cfg


def year():
    return load()["year"]


def credit_total():
    return float(load()["credit"]["total"])


def credit_major():
    return float(load()["credit"]["major"])


def credit_public():
    return float(load()["credit"]["public"])


def study_minutes():
    return int(load()["study"]["max_minutes_per_run"])


def login_wait_minutes():
    return int(load()["study"]["login_wait_minutes"])


def cert_wait_minutes():
    return int(load()["study"]["cert_wait_minutes"])


def summary():
    """给日志用的一行摘要。"""
    c = load()
    cr = c["credit"]
    return (f"年度={c['year']} 地区={c['province']} "
            f"目标(总{cr['total']}/专业{cr['major']}/公需{cr['public']}) "
            f"单次上限={c['study']['max_minutes_per_run']}分")


if __name__ == "__main__":
    if not os.path.exists(CONFIG_FILE):
        print(f"未找到 {CONFIG_FILE}，当前生效的是默认值：")
    print(summary())
