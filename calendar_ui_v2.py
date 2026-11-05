"""[고도화] 진짜 달력 같은 다크 캘린더 + 상세 일정(텍스트·음성) + 추천 To-do."""
import calendar
import html
from datetime import date, time

import streamlit as st

from app_state import get_client, korea_today
from meeting_planner import add_schedule, add_todo
from png_utils import calendar_png, event_color, has_korean_font
from voice_utils import finish_voice, take_new_voice, voice_to_schedule

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]


@st.cache_data(show_spinner=False)
def _calendar_png_cached(year, month, events_key, today):
    events = [dict(zip(("id", "date", "time", "schedule"), e)) for e in events_key]
    return calendar_png(year, month, events, today)


def _events_key(events):
    """캐시 키로 쓸 수 있도록 일정 목록을 tuple로 바꿉니다."""
    return tuple((e["id"], e["date"], e.get("time", ""), e["schedule"]) for e in events)


def _label(item):
    return (item.get("time", "") + " " + item["schedule"]).strip()


def _sorted(items):
    return sorted(items, key=lambda e: (e["date"], e.get("time") or "99"))


def _move_month(step):
    y, m = st.session_state.calendar_year, st.session_state.calendar_month + step
    if m < 1:
        y, m = y - 1, 12
    elif m > 12:
        y, m = y + 1, 1
    st.session_state.calendar_year, st.session_state.calendar_month = y, m


def _go_today():
    today = korea_today()
    st.session_state.calendar_year, st.session_state.calendar_month = today.year, today.month
    st.session_state.selected_date = today


def _select_day(day: date):
    st.session_state.selected_date = day
    st.session_state.calendar_year, st.session_state.calendar_month = day.year, day.month


def _event_cards_html(events, year, month):
    prefix = f"{year}-{month:02d}-"
    items = _sorted([e for e in events if e["date"].startswith(prefix)])
    parts = ['<div class="ev-title">이번 달 일정</div>']
    if not items:
        parts.append('<div class="ev-empty">등록된 일정이 없습니다.<br>날짜를 눌러 일정을 추가해 보세요.</div>')
    for e in items[:7]:
        d = date.fromisoformat(e["date"])
        meta = f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})"
        if e.get("time"):
            meta += f" · {e['time']}"
        if e.get("assignee"):
            meta += f" · {html.escape(e['assignee'])}"
        parts.append(
            f'<div class="ev-card" style="background:{event_color(e)}">'
            f'<div class="ev-day">{d.day}</div>'
            f'<div class="ev-body"><div class="ev-name">{html.escape(e["schedule"])}</div>'
            f'<div class="ev-meta">{meta}</div></div></div>'
        )
    if len(items) > 7:
        parts.append(f'<div class="ev-empty">외 {len(items) - 7}건</div>')
    return "".join(parts)


def render_calendar():
    year, month = st.session_state.calendar_year, st.session_state.calendar_month
    today = korea_today()
    selected = st.session_state.selected_date
    events = st.session_state.schedules

    with st.container(key="cal_panel"):
        # 상단: 월 제목 + 이동 버튼 + PNG
        t1, t2, t3, t4, t5 = st.columns([3.2, 0.55, 0.8, 0.55, 1.3], vertical_alignment="center")
        t1.markdown(
            f'<div class="cal-month">{calendar.month_name[month]} {year}</div>'
            f'<div class="cal-month-sub">{year}년 {month}월 · 날짜를 누르면 상세 일정을 볼 수 있어요</div>',
            unsafe_allow_html=True,
        )
        t2.button("◀", key="nav_prev", on_click=_move_month, args=(-1,), width="stretch")
        t3.button("오늘", key="nav_today", on_click=_go_today, width="stretch")
        t4.button("▶", key="nav_next", on_click=_move_month, args=(1,), width="stretch")
        try:
            png = _calendar_png_cached(year, month, _events_key(events), today)
            # on_click="ignore": 다운로드 시 앱이 다시 실행되지 않아 클릭 오류가 사라집니다.
            t5.download_button("📥 달력 PNG", png, file_name=f"calendar_{year}_{month:02d}.png",
                               mime="image/png", key="cal_png", on_click="ignore", width="stretch")
        except Exception as exc:
            t5.caption(f"PNG 생성 오류: {exc}")

        grid_col, side_col = st.columns([3.3, 1], gap="medium")
        with grid_col:
            for col, (i, name) in zip(st.columns(7), enumerate(WEEKDAYS)):
                cls = "sat" if i == 5 else "sun" if i == 6 else ""
                col.markdown(f'<div class="cal-wd {cls}">{name}</div>', unsafe_allow_html=True)

            by_day = {}
            for e in events:
                by_day.setdefault(e["date"], []).append(e)

            for week in calendar.Calendar(0).monthdatescalendar(year, month):
                for col, day in zip(st.columns(7), week):
                    flags = []
                    if day.weekday() >= 5:
                        flags.append("zwk")
                    if day.month != month:
                        flags.append("zout")
                    if day == today:
                        flags.append("ztoday")
                    if day == selected:
                        flags.append("zsel")
                    iso = day.isoformat()
                    with col:
                        with st.container(key=f"calcell_{iso}_{'_'.join(flags) or 'z'}"):
                            st.button(str(day.day), key=f"calday_{iso}", on_click=_select_day,
                                      args=(day,), width="stretch")
                            items = sorted(by_day.get(iso, []), key=lambda e: e.get("time") or "99")
                            shown = items if len(items) <= 3 else items[:2]
                            pills = "".join(
                                f'<div class="cal-pill" style="background:{event_color(e)}" '
                                f'title="{html.escape(_label(e))}">{html.escape(_label(e))}</div>'
                                for e in shown
                            )
                            if len(items) > len(shown):
                                pills += f'<div class="cal-more">+{len(items) - len(shown)}개 더</div>'
                            if pills:
                                st.markdown(pills, unsafe_allow_html=True)
        with side_col:
            st.markdown(_event_cards_html(events, year, month), unsafe_allow_html=True)

    if not has_korean_font():
        st.caption("⚠️ 서버에 한글 폰트가 없어 PNG의 한글이 깨질 수 있습니다. packages.txt(fonts-nanum)를 확인하세요.")


def _recommended(title):
    if "회의" in title:
        return ["회의 안건 정리", "회의 자료 준비", "참석자 확인"]
    if "발표" in title:
        return ["발표 자료 작성", "발표 대본 준비", "발표 리허설"]
    if "보고서" in title:
        return ["자료 조사", "보고서 초안 작성", "최종 검토"]
    return [f"{title} 준비 사항 확인"]


def _render_schedule_voice(selected: date):
    """[고도화] 상세 일정 음성 등록."""
    audio = st.audio_input("🎙️ 음성으로 일정 추가 (예: \"오후 3시 고객사 미팅\")",
                           key=f"schedule_voice_{st.session_state.voice_version}")
    data = take_new_voice(audio)
    if data is None:
        return
    with st.spinner("음성을 일정으로 바꾸는 중..."):
        try:
            text, parsed = voice_to_schedule(get_client(), data, selected)
        except Exception as exc:
            st.error(f"음성 처리 오류: {exc}")
            return
    title = str(parsed.get("title", "")).strip()
    day = str(parsed.get("date") or selected.isoformat())
    when = str(parsed.get("time") or "")
    try:
        added = add_schedule(title, day, when)
    except ValueError:
        st.warning(f"'{text}'에서 일정을 찾지 못했습니다. 다시 말씀해 주세요.")
        return
    if added:
        st.session_state.calendar_recommendations = _recommended(title)
        _select_day(date.fromisoformat(day))
        st.toast(f"🗓️ '{title}' 일정을 {day}{' ' + when if when else ''}에 등록했어요.")
    else:
        st.toast("이미 등록된 일정입니다.")
    finish_voice()
    st.rerun()


def render_details():
    selected = st.session_state.selected_date
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.subheader(f"📝 {selected.month}월 {selected.day}일 ({WEEKDAYS[selected.weekday()]}) 상세 일정")
        matches = _sorted([x for x in st.session_state.schedules if x["date"] == selected.isoformat()])
        if not matches:
            st.info("선택한 날짜의 일정이 없습니다.")
        for item in matches:
            a, b = st.columns([8, 1], vertical_alignment="center")
            extra = " · ".join(v for v in (item.get("assignee", ""), item.get("parent", "")) if v)
            a.markdown(
                f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;'
                f'background:{event_color(item)};margin-right:8px"></span>'
                f"**{html.escape(_label(item))}**" + (f" <small style='color:#7B8394'>({html.escape(extra)})</small>" if extra else ""),
                unsafe_allow_html=True,
            )
            if b.button("✕", key=f"del_schedule_{item['id']}", help="일정 삭제"):
                st.session_state.schedules.remove(item)
                st.rerun()

        # [고도화] 일정 추가: 날짜를 직접 고를 수 있도록 개선
        with st.container(border=True):
            st.markdown("**➕ 일정 추가** — 텍스트 또는 음성으로 등록할 수 있어요")
            has_time = st.checkbox("시간 지정", key="has_time")
            with st.form("schedule_form", clear_on_submit=True):
                title = st.text_input("일정 내용", placeholder="예: 주간 보고 회의")
                c1, c2 = st.columns(2)
                day = c1.date_input("날짜", value=selected, format="YYYY-MM-DD")
                when = c2.time_input("시간", value=time(9, 0), step=600) if has_time else None
                submitted = st.form_submit_button("일정 등록", type="primary", width="stretch")
            if submitted:
                try:
                    if add_schedule(title, day.isoformat(), when.strftime("%H:%M") if when else ""):
                        st.session_state.calendar_recommendations = _recommended(title)
                        _select_day(day)
                        st.rerun()
                    st.info("이미 등록된 일정입니다.")
                except ValueError as exc:
                    st.warning(str(exc))
            _render_schedule_voice(selected)

    with right:
        st.subheader("💡 추천 To-do List")
        analysis = st.session_state.get("meeting_analysis") or {}
        recs = [{"title": x["title"], "assignee": x.get("assignee", ""), "parent": x.get("parent", "")}
                for x in analysis.get("todos", [])]
        recs += [{"title": x, "assignee": "", "parent": ""} for x in st.session_state.calendar_recommendations]
        existing = {t["task"] for t in st.session_state.todos}
        recs = [r for r in recs if r["title"] not in existing]
        if not recs:
            st.caption("회의록 분석 또는 일정 등록 후 추천이 나타납니다.")
        for i, item in enumerate(recs):
            a, b = st.columns([5, 1.3], vertical_alignment="center")
            sub = f" <small style='color:#7B8394'>· {html.escape(item['assignee'])}</small>" if item["assignee"] else ""
            a.markdown("• " + html.escape(item["title"]) + sub, unsafe_allow_html=True)
            if b.button("추가", key=f"add_rec_{i}", width="stretch"):
                add_todo(item["title"], item["assignee"], item["parent"])
                st.rerun()
