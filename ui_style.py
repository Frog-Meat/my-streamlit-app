"""[고도화] 공통 스타일(CSS)과 캐릭터 히어로 영역."""
import os

import streamlit as st

CHARACTER_IMG = "able_character.webp"
AVATAR_IMG = "able_avatar.jpg"

CSS = """
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
html, body, [class*="st-"], .stMarkdown, button, input, textarea {
  font-family: 'Pretendard', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif;
}
.block-container { padding-top: 2.2rem; }

/* ---------- 히어로 (캐릭터) ---------- */
.st-key-hero {
  background: linear-gradient(120deg, #FFF4EA 0%, #F4F1F6 55%, #E6F8F7 100%);
  border-radius: 22px; padding: 6px 28px 6px 10px; border: 1px solid #F1E4D8;
}
.hero-title { font-size: 1.75rem; font-weight: 800; color: #1F2937; margin: 0 0 4px 0; }
.hero-title span { color: #F07C2A; }
.hero-sub { color: #5B6474; font-size: 1rem; margin-bottom: 14px; }
.hero-chips { display: flex; gap: 10px; flex-wrap: wrap; }
.hero-chip { background: #FFFFFF; border-radius: 14px; padding: 10px 16px; min-width: 120px;
  box-shadow: 0 2px 10px rgba(31,41,55,.06); }
.hero-chip b { display: block; font-size: 1.45rem; color: #1F2937; }
.hero-chip small { color: #7B8394; }
.hero-chip.teal b { color: #16A9BC; } .hero-chip.orange b { color: #F07C2A; } .hero-chip.pink b { color: #F0457E; }

/* ---------- 다크 캘린더 패널 (참고 디자인) ---------- */
.st-key-cal_panel { background: #1F2029; border-radius: 20px; padding: 22px 22px 18px 22px;
  box-shadow: 0 10px 30px rgba(17,18,26,.25); }
.st-key-cal_panel p, .st-key-cal_panel span, .st-key-cal_panel label { color: #E6E8F0; }
.cal-month { font-size: 2.1rem; font-weight: 300; color: #FFFFFF; line-height: 1.1; }
.cal-month-sub { color: #9CA0B0; font-size: .9rem; }
.cal-wd { text-align: left; padding-left: 8px; font-size: .78rem; font-weight: 700;
  letter-spacing: .08em; color: #9CA0B0; }
.cal-wd.sat { color: #7FA8FF; } .cal-wd.sun { color: #FF7A9C; }
.st-key-cal_panel [data-testid="stHorizontalBlock"] { gap: 6px; }

/* 날짜 칸 */
[class*="st-key-calcell_"] { background: #262733; border: 1px solid #30323E; border-radius: 10px;
  min-height: 104px; padding: 4px 5px 6px 5px; gap: 3px; overflow: hidden; }
[class*="st-key-calcell_"][class*="zwk"] { background: #21222B; }
[class*="st-key-calcell_"][class*="zout"] { opacity: .38; }
[class*="st-key-calcell_"][class*="zsel"] { border: 2px solid #16A9BC; box-shadow: 0 0 0 3px rgba(22,169,188,.18); }

/* 날짜 숫자 버튼: 칸 상단 전체를 클릭 영역으로 */
[class*="st-key-calday_"] button { background: transparent !important; border: none !important;
  color: #E6E8F0 !important; min-height: 28px; padding: 0 6px; justify-content: flex-start; box-shadow: none !important; }
[class*="st-key-calday_"] button p { font-weight: 700; font-size: .9rem; }
[class*="st-key-calday_"] button:hover { background: rgba(255,255,255,.06) !important; }
[class*="ztoday"] [class*="st-key-calday_"] button p {
  background: #F0457E; color: #FFFFFF; border-radius: 999px; padding: 1px 7px; }

/* 일정 pill */
.cal-pill { color: #FFFFFF; font-size: .72rem; font-weight: 600; border-radius: 999px; padding: 2px 8px;
  margin: 0 0 3px 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cal-more { color: #9CA0B0; font-size: .7rem; padding-left: 6px; }

/* 상단 버튼 (◀ 오늘 ▶ PNG) */
.st-key-cal_panel [class*="st-key-nav_"] button, .st-key-cal_panel .st-key-cal_png button {
  background: #2A2B36; color: #FFFFFF; border: 1px solid #3A3C48; border-radius: 999px; }
.st-key-cal_panel [class*="st-key-nav_"] button p, .st-key-cal_panel .st-key-cal_png button p { color: #FFFFFF; }

/* 우측 이벤트 카드 */
.ev-title { color: #FFFFFF; font-weight: 700; margin: 2px 0 10px 2px; }
.ev-card { display: flex; gap: 12px; align-items: center; border-radius: 12px; padding: 10px 12px; margin-bottom: 9px; }
.ev-day { font-size: 1.7rem; font-weight: 800; color: #FFFFFF; min-width: 38px; text-align: center; line-height: 1; }
.ev-name { color: #FFFFFF; font-weight: 700; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ev-meta { color: rgba(255,255,255,.88); font-size: .74rem; }
.ev-body { min-width: 0; }
.ev-empty { color: #9CA0B0; font-size: .85rem; }

/* ---------- To-do 삭제 버튼 (✕ 잘림 해결) ---------- */
[class*="st-key-del_todo_"] button, [class*="st-key-del_schedule_"] button {
  min-height: 30px; height: 30px; width: 30px; padding: 0 !important; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; }
[class*="st-key-del_todo_"] button p, [class*="st-key-del_schedule_"] button p { font-size: .85rem; line-height: 1; margin: 0; }

/* 요약 카드 */
.st-key-summary_card { background: #FFF8F1; border: 1px solid #F6DCC6; border-radius: 16px; padding: 14px 16px; }
</style>
"""


def apply_style() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def avatar():
    """채팅 아바타: 캐릭터 이미지가 없으면 이모지로 대체."""
    return AVATAR_IMG if os.path.exists(AVATAR_IMG) else "🤖"


def render_hero(today_count: int, open_todos: int, month_count: int) -> None:
    with st.container(key="hero"):
        img_col, text_col = st.columns([1, 2.4], vertical_alignment="center")
        with img_col:
            if os.path.exists(CHARACTER_IMG):
                st.image(CHARACTER_IMG, width=300)
            else:
                st.markdown("<div style='font-size:5rem;text-align:center'>☁️</div>", unsafe_allow_html=True)
        with text_col:
            st.markdown(
                f"""
<div class="hero-title">안녕하세요, 김 대리님! 저는 <span>에이블</span>이에요 ☁️</div>
<div class="hero-sub">회의록을 올려 주시면 요약해서 읽어 드리고, 일정과 할 일을 캘린더에 정리해 드릴게요.</div>
<div class="hero-chips">
  <div class="hero-chip pink"><b>{today_count}</b><small>오늘 일정</small></div>
  <div class="hero-chip teal"><b>{month_count}</b><small>이번 달 일정</small></div>
  <div class="hero-chip orange"><b>{open_todos}</b><small>남은 할 일</small></div>
</div>""",
                unsafe_allow_html=True,
            )
