
import os, json
import smtplib
from email.mime.text import MIMEText
import streamlit as st
from openai import OpenAI

# OpenAI 클라이언트 생성
# - Streamlit Community Cloud의 Secrets에 등록한 OPENAI_API_KEY를 환경 변수로 읽음 [02 교안]
client = OpenAI()

# 페이지 설정 [02 교안 템플릿]
st.set_page_config(page_title="AI 개인비서 에이블", page_icon="🤖", layout="wide")
st.title("음성인식 AI 개인비서 '에이블'")
st.write("회의록을 올리고 음성으로 요청하시면 요약해 드리고, 원하시면 이메일로 보내드립니다.")


# ------------------------------------------------------------
# 이메일 발송 함수 [미션 1 그대로]
# - GMAIL_ADDRESS, GMAIL_APP_PASSWORD는 Secrets에 등록 → os.getenv()로 읽음
# ------------------------------------------------------------
def send_email(to, subject, body):
    sender = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")

    # 메일 구성 (본문, 제목, 발신자, 수신자)
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to

    # 메일 보내기 (with 구문: 오류가 나도 연결이 닫힘)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(sender, password)
            s.sendmail(sender, to, msg.as_string())
        return {"status": "success"}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


# ------------------------------------------------------------
# 도구 정의 [미션 7 그대로]
# ------------------------------------------------------------
tools = [{
    "type": "function",
    "name": "send_email",
    "description": "이메일을 발송합니다.",
    "parameters": {
        "type": "object",
        "properties": {
            "to": {
                "type": "string",
                "description": "이메일 수신자. 예: 'test@gmail.com'"
            },
            "subject": {
                "type": "string",
                "description": "이메일 제목. 예: '마케팅 전략 초안'"
            },
            "body": {
                "type": "string",
                "description": "이메일 본문. 예: '안녕하세요? 김대리입니다.'"
            }
        },
        "required": ["to", "subject", "body"],
        "additionalProperties": False
    },
    "strict": True
}]


# ------------------------------------------------------------
# 역할 지정 [미션 6 + 미션 7 역할을 합침]
# ------------------------------------------------------------
sys_role = """
당신은 '김 대리'의 개인 비서 '에이블'입니다.
김대리가 요청한 업무를 최선을 다해 처리합니다.
당신의 업무는 다음과 같습니다.
1. 미팅 내용을 읽고 핵심 내용을 간결히 요약합니다.
2. 미팅 중 김 대리에게 배정된 업무가 있을 시 그 내용, 기한, 관련자를 자세히 정리합니다.
3. 김 대리에게 배정된 업무가 없으면 "배정된 업무가 없습니다"라고 알려줍니다.
4. 미팅 내용에 없는 사실은 지어내지 않는다.
5. 답변은 한국어로 정중히 작성한다.
6. 이메일로 보내달라고 명확히 요청한 경우엔 send_email 도구를 사용함.
7. 이메일 요청이 없다면 도구를 사용하지 않고 텍스트로만 답변.
8. 이메일 본문에는 미팅 요약, 김 대리에게 배정된 업무의 내용을 함께 적는다.
9. 미팅과 관계없는 질문에도 친절하게 답변한다.
10. 답변은 음성으로 읽어줄 것이므로 마크다운 기호(#, *, - 등)나 표를 쓰지 않고,
    자연스럽게 말하듯이 문장으로 작성한다.
"""


# ------------------------------------------------------------
# 상태 초기화 [02 교안 템플릿 / Streamlit 교안: 상태 키 초기화 패턴]
# ------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


# ------------------------------------------------------------
# 사이드바 [Streamlit 교안: 사이드바, st.image / 프로젝트 교안 p.62 이미지 경로]
# ------------------------------------------------------------
with st.sidebar:
    st.image("https://raw.githubusercontent.com/Jangrae/img/master/ai_robot.png")
    st.header("설정")
    my_email = st.text_input("김 대리 이메일 주소", value="kwakminjay@gmail.com")
    st.caption("'이메일로 보내줘'라고 요청하면 이 주소로 보냅니다.")

    if st.button("대화 초기화"):
        st.session_state.messages = []
        st.rerun()


# ------------------------------------------------------------
# 이전 대화 출력 [Streamlit 교안: 챗봇 구현 예시]
# ------------------------------------------------------------
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# ------------------------------------------------------------
# 지시 영역 [02 교안 템플릿]
# ------------------------------------------------------------
with st.form("task_form"):
    uploaded_file = st.file_uploader("회의록 파일 업로드 (meeting.txt, test.txt)", type=["txt"])
    audio_value = st.audio_input("무엇을 도와드릴까요?")
    text_value = st.text_input("음성 대신 글로 요청하기 (선택)")
    submit = st.form_submit_button("실행")


# 버튼을 눌렀을 때만 실행
if submit:
    # 업로드 된 파일이 있으면 디코딩
    text = ""
    if uploaded_file is not None:
        text = uploaded_file.read().decode("utf-8")

    # 녹음도 글도 없으면 요청
    if audio_value is None and not text_value:
        st.warning("음성을 녹음하거나 요청 내용을 입력해주세요.")
        st.stop()

    # 사용자 요청 만들기
    if audio_value is not None:
        # STT: 음성 → 텍스트 [02 교안 템플릿]
        with st.spinner("음성을 인식하고 있습니다..."):
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", audio_value, "audio/wav"))
        user_text = transcript.text
    else:
        user_text = text_value

    # 사용자 요청 화면에 표시 (STT 결과로 음성 인식 정확성 확인) [프로젝트 교안 p.61]
    with st.chat_message("user"):
        st.markdown(user_text)

    # 시스템 메세지 [02 교안 템플릿]
    system_content = sys_role + f"\n\n김 대리 이메일 주소: {my_email}"
    if text:
        system_content += f"\n\n다음 미팅 내용을 참고하세요:\n[미팅 내용]\n{text}"

    # 대화 기록 저장: 최근 10개만 유지 [OpenAI 교안: 대화 히스토리 관리]
    st.session_state.messages.append({"role": "user", "content": user_text})
    st.session_state.messages = st.session_state.messages[-10:]

    input_messages = [{"role": "system", "content": system_content}] + st.session_state.messages

    # LLM 호출 및 응답 듣기
    with st.chat_message("assistant"):
        with st.spinner("답변을 준비하고 있습니다..."):
            try:
                # 1단계: 모델에게 질문 + 도구 정의 전달 [미션 7]
                response = client.responses.create(
                    model="gpt-4o-mini",
                    input=input_messages,
                    tools=tools,
                    tool_choice="auto"
                )

                # 도구 필요 여부 확인
                tool_calls = [
                    item for item in response.output
                    if item.type == "function_call"
                ]

                if not tool_calls:
                    # 도구가 필요 없으면 답변 그대로 사용
                    answer = response.output_text

                else:
                    # 2단계: 모델이 요청한 tool 실행
                    tool_outputs = []

                    for item in tool_calls:
                        args = json.loads(item.arguments)

                        if item.name == "send_email":
                            result = send_email(**args)

                            if result["status"] == "success":
                                st.success(f"{args['to']} 로 이메일을 보냈습니다.")
                            else:
                                st.error(f"이메일 발송 실패: {result['error']}")

                            tool_outputs.append({
                                "type": "function_call_output",
                                "call_id": item.call_id,
                                "output": json.dumps(result, ensure_ascii=False)
                            })

                    # 3단계: tool 결과를 모델에 다시 전달
                    final_response = client.responses.create(
                        model="gpt-4o-mini",
                        previous_response_id=response.id,
                        input=tool_outputs
                    )
                    answer = final_response.output_text

            except Exception as e:
                # [Streamlit 교안: 챗봇 구현 예시의 예외 처리]
                answer = f"오류가 발생했습니다: {e}"

        # 응답 출력 (텍스트)
        st.markdown(answer)

        # TTS: 텍스트 → 음성 [미션 5]
        # [변경] IPython의 Audio()는 Streamlit에서 동작하지 않으므로 st.audio()로 재생
        with st.spinner("음성을 만들고 있습니다..."):
            try:
                speech_response = client.audio.speech.create(
                    model="gpt-4o-mini-tts",
                    voice="nova",
                    input=answer
                )
                speech_response.stream_to_file("answer.mp3")
                st.audio("answer.mp3", autoplay=True)
            except Exception as e:
                st.warning(f"음성 답변을 만들지 못했습니다: {e}")

    # 답변 기록 저장
    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.messages = st.session_state.messages[-10:]
