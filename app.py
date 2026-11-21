"""
防熬夜小助手 —— 基于 Streamlit 的防熬夜 Demo
================================================

功能概览
1. 侧边栏可设置每天的强制睡觉时间（默认 23:30）。
2. 主界面实时显示距离强制睡觉还剩多少小时 / 分钟 / 秒。
3. 一旦超过设定时间，页面显示红色警告："你已经熬夜了，立刻去睡觉！"
4. 点击"我已准时睡觉"完成打卡，触发庆祝动画。
5. 首页 / 侧边栏均可自由输入目标睡觉时间（HH:MM）。
6. 首页提供"记录起床时间"按钮，记录当天的起床时间。
7. 自动统计近 7 天睡眠历史，周总时长 >= 49 小时给予鼓励，否则进行督促。

运行方式
    pip install streamlit
    streamlit run app.py
"""

from datetime import datetime, time, timedelta, timezone
import inspect
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ============================================================
# 一、页面基础配置
# ============================================================
st.set_page_config(
    page_title="防熬夜小助手",
    layout="centered",
    initial_sidebar_state="expanded",
)

# 熬夜"宽限期"：超过睡觉时间后，只有 6 小时以内才算"正在熬夜"；
# 超过 6 小时（例如第二天早上），说明新的一天已经开始了，
# 页面会自动切换回对"下一次睡觉时间"的倒计时。
GRACE_PERIOD = timedelta(hours=6)

# 应用面向国内用户，统一使用北京时间（UTC+8，无夏令时）。
# 不能直接使用服务器本地时间：Streamlit Cloud 的服务器时区是 UTC，
# 否则部署后倒计时、熬夜判定和打卡时间都会与北京时间相差 8 小时。
LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def now_local() -> datetime:
    """返回北京时间的 naive datetime，便于和"每天的睡觉时间"直接比较。"""
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)

# 打卡时间保存在 session_state 中，键名统一管理，避免手写字符串出错。
CHECKIN_KEY = "checkin_at"
# 标记"刚刚完成打卡"，用于在重跑后只播放一次庆祝动画。
JUST_CHECKED_KEY = "just_checked"
# 目标睡觉时间（单一数据源）：侧边栏输入和首页输入框都读写它。
BEDTIME_KEY = "bedtime"
# 两个自由输入框各自的控件 key（Streamlit 控件不能共用同一个 key）。
SIDEBAR_TEXT_KEY = "bedtime_sidebar_text"
MAIN_TEXT_KEY = "bedtime_main_text"
BEDTIME_ERROR_KEY = "bedtime_input_error"
# 起床时间记录。
WAKE_KEY = "wake_at"
JUST_WOKE_KEY = "just_woke"

# 每周睡眠目标：49 小时（约合每天 7 小时）。
# 近 7 天累计 >= 该值时鼓励用户，低于该值时进行督促。
WEEKLY_TARGET_MINUTES = 49 * 60

# 历史记录持久化文件：保存在脚本同目录，刷新页面 / 重启应用都不会丢。
HISTORY_FILE = Path(__file__).with_name("sleep_history.json")

# 用户设置持久化文件：保存上次设置的目标睡觉时间，重启后继续生效。
SETTINGS_FILE = Path(__file__).with_name("settings.json")

# ============================================================
# 二、全局样式（夜空渐变 + 玻璃拟态）
# ============================================================
GLOBAL_CSS = """
<style>
    /* ---------- 全局：深色夜空渐变背景 ---------- */
    .stApp {
        background:
            radial-gradient(1200px 620px at 12% -12%, rgba(124, 92, 255, .30), transparent 62%),
            radial-gradient(900px 520px at 92% -4%, rgba(34, 211, 238, .16), transparent 58%),
            radial-gradient(900px 620px at 50% 112%, rgba(255, 77, 94, .10), transparent 60%),
            linear-gradient(160deg, #070b18 0%, #0b1026 46%, #120c26 100%);
        color: #e8ecff;
        /* 让原生时间选择器等控件跟随深色主题 */
        color-scheme: dark;
        font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    }

    /* 隐藏 Streamlit 自带的页眉与菜单，界面更干净 */
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu, footer { visibility: hidden; }

    /* 收紧主内容区宽度，视觉更聚焦 */
    .block-container {
        padding-top: 2.4rem;
        padding-bottom: 3rem;
        max-width: 780px;
    }

    /* ---------- 侧边栏 ---------- */
    section[data-testid="stSidebar"] {
        background: rgba(10, 14, 30, .82);
        border-right: 1px solid rgba(255, 255, 255, .08);
        backdrop-filter: blur(18px);
    }
    section[data-testid="stSidebar"] label {
        color: #cfd6ff !important;
        letter-spacing: .02em;
    }
    section[data-testid="stSidebar"] input {
        background: rgba(255, 255, 255, .06) !important;
        color: #e8ecff !important;
        border: 1px solid rgba(255, 255, 255, .14) !important;
        border-radius: 10px !important;
    }
    [data-testid="stCaptionContainer"] p {
        color: rgba(232, 236, 255, .48);
        letter-spacing: .02em;
    }

    /* 侧边栏标题 */
    .side-kicker {
        font-size: .72rem;
        letter-spacing: .32em;
        color: rgba(232, 236, 255, .38);
    }
    .side-title {
        margin: .3rem 0 1rem;
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: .06em;
        color: #e6eaff;
    }
    /* 侧边栏小贴士卡片 */
    .side-note {
        margin-top: 1.4rem;
        padding: 1rem 1.1rem;
        border-radius: 16px;
        background: rgba(124, 92, 255, .10);
        border: 1px solid rgba(124, 92, 255, .28);
        font-size: .82rem;
        line-height: 1.9;
        color: rgba(226, 232, 255, .72);
    }
    .side-note b {
        display: block;
        margin-bottom: .25rem;
        color: #b9c6ff;
        letter-spacing: .08em;
    }

    /* ---------- 主界面 Hero 标题 ---------- */
    .hero {
        padding: .4rem 0 1.4rem;
        text-align: center;
    }
    .hero-badge {
        display: inline-flex;
        align-items: center;
        gap: .5rem;
        padding: .38rem .95rem;
        border-radius: 999px;
        font-size: .76rem;
        letter-spacing: .16em;
        color: #b9c6ff;
        background: rgba(124, 92, 255, .12);
        border: 1px solid rgba(124, 92, 255, .35);
    }
    .hero-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #22d3ee;
        box-shadow: 0 0 10px #22d3ee;
        animation: heroDot 1.8s ease-in-out infinite;
    }
    @keyframes heroDot {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%      { opacity: .35; transform: scale(.72); }
    }
    .hero h1 {
        margin: .95rem 0 .45rem;
        font-size: 2.3rem;
        font-weight: 800;
        letter-spacing: .03em;
        background: linear-gradient(100deg, #ffffff, #c9d4ff 55%, #8fe7ff);
        -webkit-background-clip: text;
        background-clip: text;
        -webkit-text-fill-color: transparent;
        color: transparent;
    }
    .hero p {
        margin: 0;
        font-size: .95rem;
        letter-spacing: .05em;
        color: rgba(232, 236, 255, .55);
    }

    /* ---------- 熬夜红色警告条 ---------- */
    .warn-card {
        display: flex;
        align-items: center;
        gap: .85rem;
        margin: .2rem 0 1rem;
        padding: 1.05rem 1.25rem;
        border-radius: 18px;
        font-size: 1.02rem;
        font-weight: 700;
        letter-spacing: .03em;
        color: #ffd9dd;
        background: linear-gradient(135deg, rgba(255, 77, 94, .24), rgba(255, 77, 94, .08));
        border: 1px solid rgba(255, 77, 94, .55);
        animation: warnPulse 1.6s ease-in-out infinite;
    }
    .warn-card .dot {
        flex: none;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #ff4d5e;
        box-shadow: 0 0 12px #ff4d5e;
    }
    @keyframes warnPulse {
        0%, 100% { box-shadow: 0 0 0 0 rgba(255, 77, 94, .38); }
        50%      { box-shadow: 0 0 0 10px rgba(255, 77, 94, 0); }
    }

    /* ---------- 按钮：主操作（渐变） + 次操作（玻璃描边） ---------- */
    div.stButton > button {
        width: 100%;
        padding: .95rem 1rem;
        border: 1px solid rgba(255, 255, 255, .18);
        border-radius: 16px;
        background: linear-gradient(135deg, #7c5cff, #22d3ee);
        color: #06101f;
        font-size: 1.02rem;
        font-weight: 800;
        letter-spacing: .12em;
        box-shadow: 0 12px 32px rgba(124, 92, 255, .35);
        transition: transform .18s ease, box-shadow .18s ease,
                    background .18s ease, border-color .18s ease;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        border-color: rgba(255, 255, 255, .35);
        box-shadow: 0 18px 42px rgba(124, 92, 255, .52);
        color: #06101f;
    }
    div.stButton > button:focus {
        color: #06101f;
        border-color: rgba(255, 255, 255, .35);
        box-shadow: 0 12px 32px rgba(124, 92, 255, .35);
    }

    /* 次级按钮：半透明玻璃 + 主题紫描边，用于"记录起床时间"等辅助操作 */
    div.stButton > button[kind="secondary"],
    div.stButton > button[data-testid="stBaseButton-secondary"] {
        padding: .7rem .8rem;
        border: 1px solid rgba(124, 92, 255, .45);
        border-radius: 14px;
        background: rgba(124, 92, 255, .10);
        color: #c9d4ff;
        font-size: .92rem;
        font-weight: 600;
        letter-spacing: .06em;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, .06);
    }
    div.stButton > button[kind="secondary"]:hover,
    div.stButton > button[data-testid="stBaseButton-secondary"]:hover {
        background: rgba(124, 92, 255, .22);
        border-color: rgba(124, 92, 255, .78);
        color: #eef1ff;
        transform: translateY(-1px);
        box-shadow: 0 10px 26px rgba(124, 92, 255, .22);
    }
    div.stButton > button[kind="secondary"]:focus,
    div.stButton > button[data-testid="stBaseButton-secondary"]:focus {
        color: #eef1ff;
        border-color: rgba(124, 92, 255, .78);
        box-shadow: none;
    }
    div.stButton > button:disabled {
        opacity: .65;
        transform: none;
        cursor: not-allowed;
    }

    /* ---------- 侧边栏展开 / 收起按钮：放大 + 主题渐变，避免找不到 ---------- */
    /* 注意：展开按钮的 data-testid 直接挂在 button 上，收起按钮则包了一层 div */
    [data-testid="stExpandSidebarButton"],
    [data-testid="stExpandSidebarButton"] button,
    [data-testid="stSidebarCollapseButton"] button {
        width: 46px;
        height: 46px;
        border-radius: 15px;
        background: linear-gradient(135deg, #7c5cff, #22d3ee);
        border: 1px solid rgba(255, 255, 255, .28);
        box-shadow: 0 10px 26px rgba(124, 92, 255, .45);
        transition: transform .18s ease, box-shadow .18s ease, filter .18s ease;
    }
    [data-testid="stExpandSidebarButton"]:hover,
    [data-testid="stExpandSidebarButton"] button:hover,
    [data-testid="stSidebarCollapseButton"] button:hover {
        transform: translateY(-1px) scale(1.04);
        box-shadow: 0 14px 32px rgba(124, 92, 255, .62);
        filter: brightness(1.08);
    }
    [data-testid="stExpandSidebarButton"] svg,
    [data-testid="stSidebarCollapseButton"] button svg {
        width: 24px;
        height: 24px;
        color: #06101f !important;
        fill: #06101f !important;
    }

    /* ---------- 首页设置卡片（st.container(border=True)） ---------- */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 22px !important;
        border-color: rgba(255, 255, 255, .10) !important;
        background: rgba(255, 255, 255, .035);
        backdrop-filter: blur(10px);
    }
    .sec-title {
        font-size: .76rem;
        letter-spacing: .24em;
        color: rgba(232, 236, 255, .45);
    }
    .sec-hint {
        margin: .35rem 0 .2rem;
        font-size: .78rem;
        letter-spacing: .03em;
        color: rgba(232, 236, 255, .45);
    }

    /* ---------- 时间自由输入框：字号加大、加粗居中，保证数字清晰 ---------- */
    /* 新版 Streamlit 的边框和背景直接画在 input 元素上，因此要选中 input 本身 */
    div[data-testid="stTextInput"] input[data-testid="stTextInputField"] {
        min-height: 3.3rem;
        padding: .45rem 1rem;
        background: #ffffff !important;  /* 纯白底 */
        border: 1px solid rgba(124, 92, 255, .55) !important;
        border-radius: 14px !important;
        color: #000000 !important;       /* 纯黑数字 */
        font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
        font-size: 1.45rem;
        font-weight: 700;
        letter-spacing: .16em;
        text-align: left;                /* 左对齐，不再居中 */
        caret-color: #7c5cff;
        transition: border-color .18s ease, box-shadow .18s ease;
    }
    div[data-testid="stTextInput"] input[data-testid="stTextInputField"]:focus {
        border-color: #0891b2 !important;
        box-shadow: 0 0 0 3px rgba(34, 211, 238, .25);
        outline: none;
    }
    div[data-testid="stTextInput"] input[data-testid="stTextInputField"]::placeholder {
        color: rgba(20, 24, 35, .35);
        font-weight: 500;
        letter-spacing: .1em;
    }
    .input-error {
        margin-top: .35rem;
        font-size: .78rem;
        color: #ff8a95;
    }
    .wake-line {
        margin: .5rem 0 .9rem;
        font-size: .92rem;
        color: rgba(232, 236, 255, .75);
    }
    .wake-line b {
        color: #8fe7ff;
        font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
        font-size: 1.15rem;
        text-shadow: 0 0 16px rgba(34, 211, 238, .5);
    }

    /* ---------- 睡眠历史统计 ---------- */
    .sleep-total {
        margin-top: .45rem;
        font-family: ui-monospace, "Cascadia Code", Consolas, monospace;
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1.2;
        color: #ffffff;
        text-shadow: 0 0 20px rgba(124, 92, 255, .4);
    }
    .sleep-total span {
        font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
        font-size: .8rem;
        font-weight: 500;
        letter-spacing: .04em;
        color: rgba(232, 236, 255, .45);
    }
    /* 距离 49 小时目标的进度条 */
    .sleep-bar {
        height: 10px;
        margin: .8rem 0 .9rem;
        overflow: hidden;
        border-radius: 999px;
        background: rgba(255, 255, 255, .08);
    }
    .sleep-bar i {
        display: block;
        height: 100%;
        border-radius: 999px;
        background: linear-gradient(90deg, #7c5cff, #22d3ee);
        transition: width .6s ease;
    }
    .sleep-bar.good i { background: linear-gradient(90deg, #34d399, #22d3ee); }
    .sleep-bar.bad i { background: linear-gradient(90deg, #fbbf24, #ff4d5e); }

    /* 鼓励 / 督促提示 */
    .sleep-msg {
        padding: .8rem 1rem;
        border-radius: 14px;
        font-size: .88rem;
        line-height: 1.75;
        letter-spacing: .02em;
    }
    .sleep-msg.good {
        background: rgba(52, 211, 153, .12);
        border: 1px solid rgba(52, 211, 153, .35);
        color: #d8fff0;
    }
    .sleep-msg.bad {
        background: rgba(251, 191, 36, .10);
        border: 1px solid rgba(251, 191, 36, .38);
        color: #ffeec2;
    }
    .sleep-msg.idle {
        background: rgba(255, 255, 255, .04);
        border: 1px dashed rgba(255, 255, 255, .14);
        color: rgba(232, 236, 255, .55);
    }

    /* 历史记录列表 */
    .history {
        margin-top: 1rem;
        padding-top: .4rem;
        border-top: 1px dashed rgba(255, 255, 255, .10);
    }
    .history-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: .6rem;
        padding: .45rem 0;
        font-size: .82rem;
        color: rgba(232, 236, 255, .66);
        border-bottom: 1px solid rgba(255, 255, 255, .05);
    }
    .history-row:last-child { border-bottom: none; }
    .history-row b {
        font-weight: 600;
        white-space: nowrap;
        color: #e8ecff;
    }
    .history-date {
        min-width: 48px;
        font-family: ui-monospace, Consolas, monospace;
        color: rgba(232, 236, 255, .42);
    }
    .history-empty {
        padding: .6rem 0;
        font-size: .82rem;
        color: rgba(232, 236, 255, .4);
    }

    /* 侧边栏空间较窄：历史卡片整体更紧凑一些 */
    section[data-testid="stSidebar"] .sleep-total { font-size: 1.22rem; }
    section[data-testid="stSidebar"] .sleep-total span {
        display: block;          /* 目标说明单独成行，避免在词中间折行 */
        margin-top: .25rem;
    }
    section[data-testid="stSidebar"] .sleep-msg {
        padding: .7rem .8rem;
        font-size: .78rem;
        line-height: 1.7;
    }
    section[data-testid="stSidebar"] .history-row {
        gap: .35rem;
        font-size: .74rem;
    }
    section[data-testid="stSidebar"] .history-date { min-width: 38px; }

    /* ---------- 页脚 ---------- */
    .footer {
        margin-top: 2.4rem;
        text-align: center;
        font-size: .74rem;
        letter-spacing: .18em;
        color: rgba(232, 236, 255, .28);
    }
</style>
"""

# ============================================================
# 三、主界面标题区（Hero）
# ============================================================
HERO_HTML = """
<div class="hero">
    <div class="hero-badge"><span class="hero-dot"></span>睡眠守护 · 实时倒计时</div>
    <h1>防熬夜小助手</h1>
    <p>设定强制睡觉时间，时间一到，立刻放下手机。</p>
</div>
"""

# ============================================================
# 四、倒计时组件模板
# ------------------------------------------------------------
# 为什么用 iframe 组件而不是每次 st.rerun()？
# 因为 st.rerun() 会让整页重新执行、界面闪烁；而把倒计时交给
# 浏览器用 JavaScript 每秒刷新，既能做到"秒级实时"，又不会打扰
# Streamlit 的服务端状态。
# ============================================================
COUNTDOWN_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
        height: 100%;
        overflow: hidden;
        background: transparent;
        font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    }

    /* 卡片主体：玻璃拟态 + 双层柔光 */
    .wrap {
        position: relative;
        display: flex;
        flex-direction: column;
        justify-content: center;
        height: 100%;
        padding: 22px;
        overflow: hidden;
        border-radius: 26px;
        border: 1px solid rgba(255, 255, 255, .12);
        background:
            radial-gradient(120% 150% at 8% 0%, rgba(124, 92, 255, .30), transparent 55%),
            radial-gradient(120% 150% at 100% 0%, rgba(34, 211, 238, .16), transparent 55%),
            rgba(255, 255, 255, .045);
        box-shadow:
            0 26px 60px rgba(4, 8, 24, .55),
            inset 0 1px 0 rgba(255, 255, 255, .08);
        transition: border-color .4s ease, box-shadow .4s ease;
    }

    /* 左下 / 右下两团缓慢漂浮的光晕 */
    .glow {
        position: absolute;
        width: 220px;
        height: 220px;
        border-radius: 50%;
        filter: blur(60px);
        opacity: .55;
        animation: drift 9s ease-in-out infinite alternate;
        transition: background .5s ease;
    }
    .glow.a { top: -90px; left: -40px; background: #7c5cff; }
    .glow.b { bottom: -120px; right: -30px; background: #22d3ee; animation-delay: -3s; }
    @keyframes drift {
        from { transform: translate3d(0, 0, 0) scale(1); }
        to   { transform: translate3d(24px, 16px, 0) scale(1.14); }
    }

    .content { position: relative; z-index: 2; }

    /* 顶部说明文字 */
    .label {
        text-align: center;
        font-size: 13px;
        letter-spacing: .26em;
        color: rgba(232, 236, 255, .55);
        transition: color .4s ease;
    }

    /* 时 / 分 / 秒 三块数字 */
    .digits {
        display: flex;
        align-items: flex-end;
        justify-content: center;
        gap: 10px;
        margin: 14px 0 8px;
    }
    .cell {
        flex: 1 1 0;               /* 三块数字等分可用宽度，窄屏时自动收缩 */
        min-width: 0;
        max-width: 104px;
        padding: 12px 4px 10px;
        text-align: center;
        border-radius: 18px;
        border: 1px solid rgba(255, 255, 255, .10);
        background: linear-gradient(180deg, rgba(255, 255, 255, .10), rgba(255, 255, 255, .02));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, .12);
    }
    .num {
        font-family: ui-monospace, "Cascadia Code", Consolas, "Courier New", monospace;
        /* 字号随容器宽度缩放，保证任何窗口下三块数字都完整可见 */
        font-size: clamp(28px, 8.5vw, 46px);
        font-weight: 700;
        line-height: 1;
        letter-spacing: .02em;
        color: #ffffff;
        text-shadow: 0 0 22px rgba(124, 92, 255, .55);
        transition: color .4s ease, text-shadow .4s ease;
    }
    .unit {
        margin-top: 6px;
        font-size: 11px;
        letter-spacing: .22em;
        color: rgba(232, 236, 255, .45);
    }
    .sep {
        padding-bottom: 22px;
        font-size: 40px;
        font-weight: 700;
        color: rgba(232, 236, 255, .25);
    }

    /* 底部信息行：目标时间 / 当前时间 */
    .meta {
        display: flex;
        justify-content: space-between;
        gap: 8px;
        padding: 0 6px;
        font-size: 12px;
        letter-spacing: .08em;
        color: rgba(232, 236, 255, .42);
    }

    /* 窄屏适配：缩小间距与字号，避免任何元素被裁切 */
    @media (max-width: 520px) {
        .wrap { padding: 16px; border-radius: 20px; }
        .digits { gap: 6px; }
        .sep { padding-bottom: 18px; font-size: 26px; }
        .unit { font-size: 10px; letter-spacing: .12em; }
        .meta { font-size: 10px; letter-spacing: .02em; }
        .label { letter-spacing: .16em; }
    }

    /* ---------- 熬夜状态：整体转为红色警示 ---------- */
    .wrap.night {
        border-color: rgba(255, 77, 94, .55);
        box-shadow:
            0 26px 60px rgba(255, 77, 94, .26),
            inset 0 1px 0 rgba(255, 255, 255, .06);
    }
    .wrap.night .glow.a { background: #ff4d5e; }
    .wrap.night .glow.b { background: #ff8d99; }
    .wrap.night .label { color: #ff8d99; }
    .wrap.night .num {
        color: #ffb3bb;
        text-shadow: 0 0 24px rgba(255, 77, 94, .75);
        animation: beat 1.1s ease-in-out infinite;
    }
    @keyframes beat {
        0%, 100% { transform: scale(1); }
        50%      { transform: scale(1.045); }
    }
</style>
</head>
<body>
<div class="wrap" id="wrap">
    <div class="glow a"></div>
    <div class="glow b"></div>

    <div class="content">
        <div class="label" id="label">距离强制睡觉还有</div>

        <div class="digits">
            <div class="cell"><div class="num" id="hh">00</div><div class="unit">小时</div></div>
            <div class="sep">:</div>
            <div class="cell"><div class="num" id="mm">00</div><div class="unit">分钟</div></div>
            <div class="sep">:</div>
            <div class="cell"><div class="num" id="ss">00</div><div class="unit">秒</div></div>
        </div>

        <div class="meta">
            <span>目标时间 __BEDTIME__</span>
            <span id="clock">当前 --:--:--</span>
        </div>
    </div>
</div>

<script>
    (function () {
        // 目标时间戳（毫秒）由 Python 端注入：
        // - 未到点时是"下一次睡觉时间"，剩余时间为正，显示倒计时；
        // - 已过点时是"最近一次睡觉时间"，剩余时间为负，显示已熬夜时长。
        var target = __TARGET_MS__;

        var wrap = document.getElementById('wrap');
        var label = document.getElementById('label');
        var hhEl = document.getElementById('hh');
        var mmEl = document.getElementById('mm');
        var ssEl = document.getElementById('ss');
        var clockEl = document.getElementById('clock');

        function pad(n) { return n < 10 ? '0' + n : '' + n; }

        function tick() {
            var now = new Date();

            // 右下角的实时时钟
            clockEl.textContent = '当前 ' + pad(now.getHours()) + ':' +
                                  pad(now.getMinutes()) + ':' + pad(now.getSeconds());

            // 计算剩余秒数：负数代表已经超过目标时间
            var remaining = Math.floor((target - now.getTime()) / 1000);
            var overtime = remaining < 0;

            var total = Math.abs(remaining);
            var hours = Math.floor(total / 3600);
            var minutes = Math.floor((total % 3600) / 60);
            var seconds = total % 60;

            hhEl.textContent = pad(hours);
            mmEl.textContent = pad(minutes);
            ssEl.textContent = pad(seconds);

            // 切换红色警示样式与文案
            wrap.classList.toggle('night', overtime);
            label.textContent = overtime ? '已超过睡觉时间' : '距离强制睡觉还有';
        }

        tick();
        setInterval(tick, 500);   // 每 0.5 秒刷新一次，秒数切换更跟手
    })();
</script>
</body>
</html>
"""


# ============================================================
# 五、打卡成功卡片模板（含彩色纸屑庆祝动画）
# ------------------------------------------------------------
# 卡片同样放在 iframe 中渲染，原因是：
#   1. 动画由浏览器自己播放，不受 Streamlit 重跑影响；
#   2. iframe 渲染完成后可以主动把自己滚动到视野内，
#      避免用户点了按钮却看不到结果。
# ============================================================
CHECKIN_CARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    html, body {
        height: 100%;
        overflow: hidden;
        background: transparent;
        font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    }

    /* 绿色成功卡片 */
    .card {
        position: relative;
        display: flex;
        align-items: center;
        gap: 16px;
        height: 100%;
        padding: 16px 22px;
        overflow: hidden;
        border-radius: 20px;
        background: linear-gradient(135deg, rgba(34, 197, 94, .18), rgba(34, 211, 238, .08));
        border: 1px solid rgba(52, 211, 153, .45);
        box-shadow: 0 18px 40px rgba(16, 185, 129, .16);
        animation: cardIn .5s cubic-bezier(.22, 1, .36, 1);
    }
    @keyframes cardIn {
        from { opacity: 0; transform: translateY(12px) scale(.98); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
    }

    /* 对勾描边动画 */
    .check circle {
        stroke: #34d399;
        stroke-width: 3;
        fill: none;
        stroke-dasharray: 151;
        stroke-dashoffset: 151;
        animation: draw .7s ease forwards;
    }
    .check path {
        stroke: #34d399;
        stroke-width: 4;
        fill: none;
        stroke-linecap: round;
        stroke-linejoin: round;
        stroke-dasharray: 40;
        stroke-dashoffset: 40;
        animation: draw .5s .5s ease forwards;
    }
    @keyframes draw {
        to { stroke-dashoffset: 0; }
    }

    .text { position: relative; z-index: 2; }
    .title {
        font-size: 1.02rem;
        font-weight: 800;
        letter-spacing: .02em;
        color: #d8fff0;
    }
    .sub {
        margin-top: .3rem;
        font-size: .82rem;
        letter-spacing: .03em;
        color: rgba(216, 255, 240, .65);
    }

    /* 彩色纸屑：从卡片顶部飘落，播放一次后由 JS 清理 */
    .confetti {
        position: absolute;
        top: -16px;
        z-index: 1;
        width: 7px;
        height: 12px;
        border-radius: 2px;
        animation-name: fall;
        animation-timing-function: linear;
        animation-fill-mode: forwards;
    }
    @keyframes fall {
        to { transform: translateY(170px) rotate(540deg); opacity: 0; }
    }
</style>
</head>
<body>
<div class="card" id="card">
    <svg class="check" width="44" height="44" viewBox="0 0 52 52" aria-hidden="true">
        <circle cx="26" cy="26" r="24" />
        <path d="M14.5 27.2 L22.5 35 L38 18.5" />
    </svg>
    <div class="text">
        <div class="title">打卡成功，准时睡觉！</div>
        <div class="sub">记录时间 __TIME__ · 明早的你，会感谢今晚的你</div>
    </div>
</div>

<script>
    (function () {
        var card = document.getElementById('card');

        // 1. 生成随机位置的彩色纸屑，营造"下彩带"的庆祝效果
        var colors = ['#7c5cff', '#22d3ee', '#34d399', '#fbbf24', '#ff7ab6', '#ffffff'];
        for (var i = 0; i < 24; i++) {
            var piece = document.createElement('i');
            piece.className = 'confetti';
            piece.style.left = (Math.random() * 100) + '%';
            piece.style.background = colors[i % colors.length];
            piece.style.animationDuration = (1.4 + Math.random() * 1.1) + 's';
            piece.style.animationDelay = (Math.random() * 0.5) + 's';
            card.appendChild(piece);
        }

        // 2. 动画结束 3 秒后清理纸屑，避免反复重跑时元素堆积
        setTimeout(function () {
            var pieces = card.querySelectorAll('.confetti');
            for (var i = 0; i < pieces.length; i++) {
                pieces[i].remove();
            }
        }, 3000);

        // 3. 只在"刚刚打卡"时把卡片滚动到视野内，避免后续每次重跑都跳动页面
        if (__SCROLL__) {
            try {
                if (window.frameElement) {
                    window.frameElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            } catch (e) {
                /* 浏览器禁止访问 frameElement 时静默失败即可 */
            }
        }
    })();
</script>
</body>
</html>
"""


# ============================================================
# 六、业务逻辑函数
# ============================================================
def build_schedule(now: datetime, bedtime: time) -> dict:
    """根据"当前时间"和"设定的睡觉时间"计算出倒计时所需的时间点。

    睡觉时间是一个"每天重复"的时间点，所以同时查看昨天 / 今天 / 明天
    三个候选时间，分别取：
        - 最近一次已经过去的睡觉时间 last_target
        - 下一次即将到来的睡觉时间 next_target

    若距离 last_target 不超过 GRACE_PERIOD，就认为用户仍处于"熬夜中"；
    否则（例如第二天白天）则进入新一轮倒计时。
    """
    today_target = datetime.combine(now.date(), bedtime)
    candidates = [today_target + timedelta(days=offset) for offset in (-1, 0, 1)]

    last_target = max(t for t in candidates if t <= now)
    next_target = min(t for t in candidates if t > now)

    is_overtime = (now - last_target) < GRACE_PERIOD

    return {
        "last_target": last_target,
        "next_target": next_target,
        "is_overtime": is_overtime,
    }


def _embed_html(html: str, height: int) -> None:
    """把"带 JavaScript 的 HTML"放进 iframe 中渲染。

    Streamlit 1.4x 起 `st.components.v1.html` 已被标记弃用，
    推荐改用 `st.iframe`；这里做兼容处理：
        - 新版本：使用 st.iframe（同样支持 srcdoc + JavaScript）；
        - 旧版本：回退到 components.html。
    """
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=False)


def render_countdown(target: datetime, bedtime: time) -> None:
    """把目标时间注入 HTML 模板，交给浏览器实时刷新倒计时。"""
    html = (
        COUNTDOWN_TEMPLATE
        # target 是 naive 的北京时间，必须显式带上 UTC+8 再转时间戳；
        # 否则 Cloud 服务器会按 UTC 解释，浏览器端就会差 8 小时。
        .replace("__TARGET_MS__", str(int(target.replace(tzinfo=LOCAL_TZ).timestamp() * 1000)))
        .replace("__BEDTIME__", bedtime.strftime("%H:%M"))
    )
    _embed_html(html, height=252)


def render_checkin_card(checkin_at: datetime, scroll_into_view: bool = False) -> None:
    """展示"打卡成功"卡片：对勾描边 + 彩色纸屑动画。

    scroll_into_view=True 时，卡片渲染完成后会把自己滚动到视野中央，
    确保用户点击打卡后立刻看到结果。
    """
    html = (
        CHECKIN_CARD_TEMPLATE
        .replace("__TIME__", checkin_at.strftime("%H:%M:%S"))
        .replace("__SCROLL__", "true" if scroll_into_view else "false")
    )
    _embed_html(html, height=112)


def _load_history() -> dict:
    """读取本地 JSON 历史记录；文件不存在或内容损坏时返回空结构。"""
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            return {
                "sleeps": list(data.get("sleeps", [])),
                "wakes": list(data.get("wakes", [])),
            }
        except (OSError, json.JSONDecodeError):
            pass
    return {"sleeps": [], "wakes": []}


def _add_record(kind: str, at: datetime) -> None:
    """把一次睡觉 / 起床事件追加到历史文件，刷新页面后记录不会丢。"""
    data = _load_history()
    data[kind].append(at.isoformat(timespec="seconds"))
    try:
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 磁盘不可写时静默忽略，不影响页面其它功能
        pass


def _build_sessions(data: dict) -> list[dict]:
    """把"睡觉时间"和"起床时间"两两配对，得到每次睡眠的时长。

    配对规则：对每一次睡觉，取它之后、下一次睡觉之前、且间隔不超过
    24 小时的最后一次起床记录（这样"重新记录起床时间"会覆盖旧值）。
    少于 30 分钟的记录视为误点，直接忽略。
    """
    try:
        sleeps = sorted(datetime.fromisoformat(s) for s in data.get("sleeps", []))
        wakes = sorted(datetime.fromisoformat(w) for w in data.get("wakes", []))
    except ValueError:
        return []

    sessions = []
    for index, sleep_at in enumerate(sleeps):
        next_sleep = sleeps[index + 1] if index + 1 < len(sleeps) else None
        candidates = [
            w for w in wakes
            if w > sleep_at
            and (next_sleep is None or w < next_sleep)
            and (w - sleep_at) <= timedelta(hours=24)
        ]
        if not candidates:
            continue

        wake_at = max(candidates)
        minutes = int((wake_at - sleep_at).total_seconds() // 60)
        if minutes < 30:
            continue
        sessions.append({"sleep_at": sleep_at, "wake_at": wake_at, "minutes": minutes})
    return sessions


def _weekly_stats(sessions: list[dict], now: datetime) -> dict:
    """统计近 7 天（按起床时间算）的睡眠总时长。"""
    cutoff = now - timedelta(days=7)
    recent = [s for s in sessions if s["wake_at"] >= cutoff]
    total = sum(s["minutes"] for s in recent)
    return {"recent": recent, "total_minutes": total}


def _weekly_message(total_minutes: int, has_sessions: bool) -> tuple[str, str]:
    """根据近 7 天总睡眠时长返回（色调, 提示文案）。

    >= 49 小时：鼓励；< 49 小时：督促。
    """
    total_text = _format_duration(total_minutes)
    if not has_sessions:
        return (
            "idle",
            "还没有睡眠记录。完成一次「我已准时睡觉」和「记录起床时间」，就能开始统计啦。",
        )
    if total_minutes >= WEEKLY_TARGET_MINUTES:
        return (
            "good",
            f"太棒了！近 7 天累计睡眠 {total_text}，已经达到 49 小时目标，保持这个节奏！",
        )
    gap = _format_duration(WEEKLY_TARGET_MINUTES - total_minutes)
    return (
        "bad",
        f"近 7 天累计睡眠 {total_text}，距离 49 小时目标还差 {gap}，今晚记得早点睡！",
    )


def _format_duration(minutes: int) -> str:
    """把分钟数格式化为「X 小时 Y 分」。"""
    return f"{minutes // 60} 小时 {minutes % 60} 分"


def render_sleep_history(now: datetime) -> None:
    """渲染近 7 天睡眠统计、鼓励/督促提示与最近几次睡眠记录。"""
    sessions = _build_sessions(_load_history())
    stats = _weekly_stats(sessions, now)
    total = stats["total_minutes"]
    tone, message = _weekly_message(total, bool(sessions))
    pct = min(total / WEEKLY_TARGET_MINUTES, 1.0) * 100

    rows = ""
    for session in reversed(sessions[-5:]):
        rows += (
            '<div class="history-row">'
            f'<span class="history-date">{session["wake_at"]:%m-%d}</span>'
            f'<span>{session["sleep_at"]:%H:%M} → {session["wake_at"]:%H:%M}</span>'
            f'<b>{_format_duration(session["minutes"])}</b>'
            "</div>"
        )
    if not rows:
        rows = '<div class="history-empty">暂无完成的睡眠记录</div>'

    st.markdown(
        f'<div class="sleep-total">{_format_duration(total)}'
        f'<span> / 目标 49 小时</span></div>'
        f'<div class="sleep-bar {tone}"><i style="width: {pct:.1f}%"></i></div>'
        f'<div class="sleep-msg {tone}">{message}</div>'
        f'<div class="history">{rows}</div>',
        unsafe_allow_html=True,
    )


def _parse_hhmm(raw: str) -> time | None:
    """把用户输入解析成 time；格式不合法时返回 None。

    支持 "23:30"、"9:05"、中文冒号，以及 "2330" / "930" 这类纯数字写法。
    """
    text = raw.strip().replace("：", ":")
    if not text:
        return None

    if ":" in text:
        parts = text.split(":")
        if len(parts) != 2:
            return None
        hour_text, minute_text = parts
    else:
        if not text.isdigit() or len(text) not in (3, 4):
            return None
        hour_text, minute_text = text[:-2], text[-2:]

    try:
        hour, minute = int(hour_text), int(minute_text)
    except ValueError:
        return None

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def _sync_time_texts(at: time) -> None:
    """把统一的目标时间写回两个输入框，保证侧边栏和首页显示一致。"""
    text = at.strftime("%H:%M")
    st.session_state[SIDEBAR_TEXT_KEY] = text
    st.session_state[MAIN_TEXT_KEY] = text


def _load_saved_bedtime() -> time:
    """读取上次保存的目标睡觉时间；文件缺失或内容非法时回退到默认 23:30。"""
    if SETTINGS_FILE.exists():
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")).get("bedtime", "")
            parsed = _parse_hhmm(str(raw))
            if parsed is not None:
                return parsed
        except (OSError, json.JSONDecodeError):
            pass
    return time(23, 30)


def _save_bedtime(at: time) -> None:
    """把目标睡觉时间写入 settings.json，重启应用后仍然生效。"""
    try:
        SETTINGS_FILE.write_text(
            json.dumps({"bedtime": at.strftime("%H:%M")}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 磁盘不可写时静默忽略，不影响页面其它功能
        pass


def _apply_text_time(source_key: str) -> None:
    """文本框回调：解析自由输入的时间并更新目标时间。

    输入不合法时保留原目标时间，并给出红色格式提示。
    """
    parsed = _parse_hhmm(st.session_state[source_key])
    if parsed is None:
        st.session_state[BEDTIME_ERROR_KEY] = "格式不正确，请按 HH:MM 输入，例如 23:30。"
        return

    st.session_state.pop(BEDTIME_ERROR_KEY, None)
    st.session_state[BEDTIME_KEY] = parsed
    # 统一写回规范化后的文本（如 "9:5" -> "09:05"）
    _sync_time_texts(parsed)
    # 落盘保存，重启应用后仍能记住这次设置
    _save_bedtime(parsed)


def _render_time_error() -> None:
    """显示输入格式错误的提示（无错误时不输出任何内容）。"""
    error = st.session_state.get(BEDTIME_ERROR_KEY)
    if error:
        st.markdown(f'<div class="input-error">{error}</div>', unsafe_allow_html=True)


def _handle_checkin() -> None:
    """打卡按钮的回调函数。

    把状态更新放在回调里，Streamlit 会"先执行回调、再重跑脚本"，
    这样重跑时按钮和卡片都能直接渲染成"已打卡"状态，
    点击后能立刻看到变化，而不是等到下一次交互才刷新。
    """
    now = now_local()
    st.session_state[CHECKIN_KEY] = now
    st.session_state[JUST_CHECKED_KEY] = True
    _add_record("sleeps", now)


def _handle_wake() -> None:
    """记录起床时间（同样放在回调里，重跑后立刻显示结果）。"""
    now = now_local()
    st.session_state[WAKE_KEY] = now
    st.session_state[JUST_WOKE_KEY] = True
    _add_record("wakes", now)


def _button(label: str, *, on_click=None, args=None,
            disabled: bool = False, primary: bool = False) -> bool:
    """st.button 的兼容封装。

    新版 Streamlit 的按钮默认只占内容宽度，需要 width="stretch" 才能占满整行；
    旧版本没有 width 参数，这里按版本自动省略。
    """
    kwargs = {"on_click": on_click, "args": args, "disabled": disabled}
    if primary:
        kwargs["type"] = "primary"
    if "width" in inspect.signature(st.button).parameters:
        kwargs["width"] = "stretch"
    return st.button(label, **kwargs)


# ============================================================
# 七、页面主体
# ============================================================
def main() -> None:
    # 注入全局样式
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # 目标睡觉时间的唯一数据源：侧边栏输入、首页输入框都读写它
    # 首次加载时从 settings.json 恢复上次设置，没有记录则默认 23:30
    if BEDTIME_KEY not in st.session_state:
        st.session_state[BEDTIME_KEY] = _load_saved_bedtime()

    # 两个自由输入框的初始文本（与恢复后的目标时间一致）
    default_text = st.session_state[BEDTIME_KEY].strftime("%H:%M")
    if SIDEBAR_TEXT_KEY not in st.session_state:
        st.session_state[SIDEBAR_TEXT_KEY] = default_text
    if MAIN_TEXT_KEY not in st.session_state:
        st.session_state[MAIN_TEXT_KEY] = default_text

    # 当前时间在整次渲染中只取一次，保证侧边栏和主界面用的是同一个时间点
    now = now_local()

    # ---------------- 侧边栏：睡觉时间设置 ----------------
    with st.sidebar:
        st.markdown(
            '<div class="side-kicker">SLEEP SCHEDULE</div>'
            '<div class="side-title">作息设置</div>',
            unsafe_allow_html=True,
        )

        # 支持自由输入任意分钟，例如 23:07
        st.text_input(
            "每天的强制睡觉时间（HH:MM）",
            key=SIDEBAR_TEXT_KEY,
            on_change=_apply_text_time,
            args=(SIDEBAR_TEXT_KEY,),
            placeholder="例如 23:30",
            help="支持直接输入任意时间，如 23:07；超过这个时间仍未打卡，就会触发熬夜警告。",
        )
        _render_time_error()

        st.caption("建议在 22:30 - 23:30 之间入睡，给身体留出修复时间。")

        st.markdown(
            '<div class="side-note">'
            "<b>小贴士</b>"
            "睡前 1 小时远离手机蓝光<br>"
            "熬夜后的补觉无法完全抵消伤害<br>"
            "坚持打卡，养成稳定生物钟"
            "</div>",
            unsafe_allow_html=True,
        )

        # ---------------- 侧边栏：睡眠历史与周目标 ----------------
        st.markdown(
            '<div class="side-kicker">SLEEP HISTORY</div>'
            '<div class="side-title">睡眠历史</div>',
            unsafe_allow_html=True,
        )

        with st.container(border=True):
            st.markdown('<div class="sec-title">近 7 天</div>', unsafe_allow_html=True)
            render_sleep_history(now)

    # 统一读取当前目标时间（自由输入、快捷按钮的修改都已写入该状态）
    bedtime = st.session_state[BEDTIME_KEY]

    # ---------------- 主界面：标题 ----------------
    st.markdown(HERO_HTML, unsafe_allow_html=True)

    # ---------------- 主界面：倒计时 / 警告 ----------------
    schedule = build_schedule(now, bedtime)

    # 已超过睡觉时间：页面顶部显示醒目红色警告
    if schedule["is_overtime"]:
        st.markdown(
            '<div class="warn-card"><span class="dot"></span>你已经熬夜了，立刻去睡觉！</div>',
            unsafe_allow_html=True,
        )

    # 未到点 -> 倒计时到下一次睡觉时间；已过点 -> 显示已熬夜时长（时间戳为负差值）
    reference = schedule["last_target"] if schedule["is_overtime"] else schedule["next_target"]
    render_countdown(reference, bedtime)

    st.caption("倒计时由浏览器每秒自动刷新；时间一到，卡片会立刻变成红色熬夜提醒。")

    # ---------------- 主界面：目标睡觉时间（自由输入） ----------------
    with st.container(border=True):
        st.markdown(
            '<div class="sec-title">目标睡觉时间</div>'
            '<div class="sec-hint">直接输入任意时间，例如 23:07。</div>',
            unsafe_allow_html=True,
        )
        st.text_input(
            "目标睡觉时间",
            key=MAIN_TEXT_KEY,
            on_change=_apply_text_time,
            args=(MAIN_TEXT_KEY,),
            placeholder="例如 23:30",
            label_visibility="collapsed",
        )
        _render_time_error()

    # ---------------- 主界面：打卡 ----------------
    checkin_at = st.session_state.get(CHECKIN_KEY)
    # 只认"今天"的打卡记录：换一天后按钮会重新可用
    checked_today = checkin_at is not None and checkin_at.date() == now.date()

    # 点击打卡后，本次重跑会立即播放气球 + 右上角提示（只播一次）
    just_checked = st.session_state.pop(JUST_CHECKED_KEY, False)
    if just_checked:
        st.balloons()
        if hasattr(st, "toast"):
            st.toast("打卡成功，今晚好好休息")

    if checked_today:
        # 已打卡：按钮变为完成状态，用户一眼就能看到点击生效了
        _button(f"已打卡 · {checkin_at:%H:%M}", disabled=True)
        render_checkin_card(checkin_at, scroll_into_view=just_checked)
    else:
        # 未打卡：交给回调函数记录时间，重跑后直接进入"已打卡"分支
        _button("我已准时睡觉", on_click=_handle_checkin, primary=True)

    # ---------------- 主界面：起床记录 ----------------
    wake_at = st.session_state.get(WAKE_KEY)
    # 同样只展示当天的记录
    woke_today = wake_at is not None and wake_at.date() == now.date()

    if st.session_state.pop(JUST_WOKE_KEY, False) and hasattr(st, "toast"):
        st.toast("已记录起床时间，早安")

    with st.container(border=True):
        st.markdown('<div class="sec-title">起床记录</div>', unsafe_allow_html=True)
        if woke_today:
            st.markdown(
                f'<div class="wake-line">今日起床时间 <b>{wake_at:%H:%M}</b></div>',
                unsafe_allow_html=True,
            )
            _button("重新记录起床时间", on_click=_handle_wake)
        else:
            _button("记录起床时间", on_click=_handle_wake)

    # ---------------- 页脚 ----------------
    st.markdown('<div class="footer">STREAMLIT DEMO · 早睡一小时，效率高一整天</div>',
                unsafe_allow_html=True)


if __name__ == "__main__":
    main()
