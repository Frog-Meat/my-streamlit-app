"""AI 개인비서 '에이블' — 기능 고도화 최종본 진입점."""
import hashlib
import os

import streamlit as st

from app_state import get_client, initialize_state, korea_today, reset_state, save_response
from assistant import ASSISTANT_BUILD, DEFAULT_SYS_ROLE
from audio_utils import text_to_speech
from calendar_ui_v2 import render_calendar, render_details
from command_service import MissingInputError, run_command
from meeting_planner import analyze_meeting, save_analysis
from meeting_utils import update_meeting_file
from todo_ui import render_todos
from ui_style import AVATAR_IMG, apply_style, avatar, render_hero

st.set_page_config(page_title="AI 개인비서 에이블", page_icon=AVATAR_IMG if os.path.exists(AVATAR_IMG) else "☁️",
                   layout="wide")
initialize_state()
apply_style()

# ---------------- 사이드바: 회의록 업로드 + 명령 ----------------
with st.sidebar:
    if os.path.exists(AVATAR_IMG):
        st.image(AVATAR_IMG, width=96)
    st.header("에이블")
    st.caption(f"메일 처리 버전: {ASSISTANT_BUILD}")
    st.subheader("📥 회의록과 명령")
    uploaded_file = st.file_uploader("회의록 텍스트 파일 (.txt)", type=["txt"],
                                     key=f"meeting_file_{st.session_state.upload_version}")
    try:
        meeting_content = update_meeting_file(uploaded_file)
    except UnicodeDecodeError:
        meeting_content = ""
        st.error("UTF-8 형식의 TXT 파일을 업로드해 주세요.")

    if uploaded_file is None:
        st.info("회의록을 올리면 요약을 읽어 드리고 일정을 캘린더에 등록합니다.")
    elif meeting_content:
        st.caption(f"업로드: {uploaded_file.name}")
        with st.expander("회의록 본문 보기"):
            st.text_area("미팅 본문", meeting_content, height=180, disabled=True)
        file_key = hashlib.sha256(meeting_content.encode("utf-8")).hexdigest()
        if st.session_state.get("meeting_analysis_hash") != file_key:
            with st.spinner("회의록 분석 중..."):
                try:
                    client = get_client()
                    analysis = analyze_meeting(client, meeting_content)
                    st.session_state.meeting_analysis = analysis
                    st.session_state.meeting_analysis_hash = file_key
                    st.session_state.meeting_summary = analysis.get("summary", "")
                    st.session_state.meeting_questions = analysis.get("questions", [])
                    # [고도화] 날짜 있는 일정은 캘린더에 바로 등록 (등록 후보 목록 제거)
                    added, _ = save_analysis(analysis, file_key)
                    # [고도화] 회의 요약 음성을 미리 만들어 오른쪽 상단에서 바로 재생
                    try:
                        st.session_state.summary_audio = text_to_speech(
                            client, "회의 요약입니다. " + analysis.get("summary", ""))
                        st.session_state.summary_autoplay = True
                    except Exception as exc:
                        st.session_state.summary_audio = None
                        st.warning(f"요약 음성 생성 오류: {exc}")
                    st.success(f"분석 완료! 일정 {added}건을 캘린더에 등록했어요.")
                except Exception as exc:
                    st.error(f"회의록 분석 오류: {exc}")

    st.divider()
    recipient_email = st.text_input("수신자 이메일 주소", value=os.getenv("RECIPIENT_EMAIL", ""))
    with st.expander("에이블 페르소나 (프롬프트)"):
        sys_role = st.text_area("시스템 역할", value=DEFAULT_SYS_ROLE, height=220)
    if st.button("대화 및 일정 초기화", width="stretch"):
        reset_state()
        st.rerun()
    with st.form("command_form"):
        text_query = st.text_input("텍스트 질문/명령")
        audio_query = st.audio_input("음성으로 질문하기")
        submitted = st.form_submit_button("실행하기", type="primary", width="stretch")

if submitted:
    if not text_query.strip() and audio_query is None:
        st.warning("텍스트 입력 또는 음성 녹음이 필요합니다.")
    else:
        with st.spinner("에이블이 처리 중입니다..."):
            try:
                result = run_command(get_client(), text_query, audio_query, meeting_content, sys_role,
                                     st.session_state.messages, recipient_email)
            except MissingInputError as exc:
                st.warning(str(exc))
            except Exception as exc:
                st.error(f"명령 실행 오류: {exc}")
            else:
                save_response(result.user_prompt, result.answer, result.audio_bytes)
                if result.email_status:
                    if result.email_status.startswith("이메일 발송 완료"):
                        st.success(result.email_status)
                    else:
                        st.error(result.email_status)
                if result.audio_error:
                    st.warning(f"음성 응답 생성 오류: {result.audio_error}")

# ---------------- 메인: 캐릭터 히어로 ----------------
today = korea_today()
schedules = st.session_state.schedules
month_prefix = f"{st.session_state.calendar_year}-{st.session_state.calendar_month:02d}-"
render_hero(
    today_count=sum(e["date"] == today.isoformat() for e in schedules),
    open_todos=sum(not t["done"] for t in st.session_state.todos),
    month_count=sum(e["date"].startswith(month_prefix) for e in schedules),
)
st.write("")

# 가운데 넓은 영역(캘린더·상세) / 오른쪽 좁은 영역(회의 요약·To-do)
main, right = st.columns([3.6, 1.15], gap="large")
with main:
    render_calendar()
    st.write("")
    render_details()
with right:
    with st.container(key="summary_card"):
        st.subheader("📋 회의 요약")
        if st.session_state.meeting_summary:
            if st.session_state.summary_audio:
                # [고도화] 분석 직후 한 번 자동 재생, 이후에는 재생 버튼으로 다시 듣기
                st.audio(st.session_state.summary_audio, format="audio/mp3",
                         autoplay=st.session_state.summary_autoplay)
                st.session_state.summary_autoplay = False
            st.write(st.session_state.meeting_summary)
            if st.session_state.meeting_questions:
                with st.expander("확인 필요한 사항"):
                    for question in st.session_state.meeting_questions:
                        st.write("• " + question)
        else:
            st.info("회의록을 업로드하면 요약이 나타나고 바로 음성으로 읽어 드려요.")
    st.divider()
    render_todos()

# ---------------- 에이블의 답변 (최신 답변이 위로) ----------------
st.divider()
st.subheader("💬 에이블의 답변")
messages = st.session_state.messages
if messages:
    turns = [messages[i:i + 2] for i in range(0, len(messages), 2)]
    for n, turn in enumerate(reversed(turns)):
        if n == 0:
            st.caption("🆕 최신 답변")
            if st.session_state.audio_bytes:
                st.audio(st.session_state.audio_bytes, format="audio/mp3")
        for message in turn:
            icon = avatar() if message["role"] == "assistant" else "🧑‍💼"
            with st.chat_message(message["role"], avatar=icon):
                st.write(message["content"])
        if n < len(turns) - 1:
            st.markdown("<hr style='margin:6px 0;border-color:#EEF0F4'>", unsafe_allow_html=True)
else:
    st.info("사이드바에서 텍스트 또는 음성 명령을 실행하면 답변이 표시됩니다.")

st.caption("일정·To-do는 현재 접속 세션에만 유지되며 서버 재시작 후 사라질 수 있습니다.")
