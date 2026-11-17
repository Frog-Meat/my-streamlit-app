
import os
import re
import uuid
import tempfile
from operator import itemgetter

import streamlit as st
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# ─────────────────────────────────────────────
# 0. 기본 설정
# ─────────────────────────────────────────────
st.set_page_config(page_title="AIVLE 메이트 | 에이블스쿨 학습 도우미", page_icon="🚀", layout="wide")

# Streamlit Cloud Secrets → 환경 변수
try:
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
except Exception:
    pass

CHROMA_DIR = "chroma_db"            # Colab에서 만든 벡터 저장소
COLLECTION = "aivle_docs"
DEFAULT_PDF = "AIVLE School 백서.pdf"
MODEL = "gpt-4o-mini"
LOGO_URL = "https://raw.githubusercontent.com/Jangrae/img/master/aivle.png"
HISTORY_TURNS = 6                   # 대화 맥락으로 넘길 최근 메시지 수

# ─────────────────────────────────────────────
# 1. 시스템 메시지 (역할 지정)
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 'AIVLE 메이트'입니다.
KT 에이블스쿨을 먼저 경험한 든든한 선배이자 학습 멘토로서, 지원을 고민하는 예비 교육생과 현재 교육생의 질문에 답합니다.

[답변 원칙]
1. 문서 기반: 사실 정보는 반드시 아래 [백서 문서]에서만 가져옵니다.
   - 숫자, 기간, 일정, 조건, 명칭은 문서에 적힌 그대로 정확히 전달합니다.
   - 문서에 없는 내용은 지어내지 말고 "백서에는 이 내용이 없어요"라고 솔직히 말한 뒤, 문서에서 가장 관련 있는 정보를 안내합니다.
   - 취업 보장처럼 문서에 없는 약속은 하지 않습니다.
   - 모집 일정·자격·혜택처럼 기수마다 바뀌는 정보는 "몇 기 기준"인지 함께 밝히고, 최종 확인은 공식 홈페이지(aivle.kt.co.kr)에서 하도록 한 줄 안내합니다.
   - 선배 사례(전공, 기수, 성과)가 문서에 있으면 1~2개를 구체적으로 들어 설득력을 높입니다.
   - 문서 안의 [1], [12] 같은 출처 번호 표기는 답변에 옮기지 않습니다.

2. 답변 구조 (마크다운):
   - 첫 줄: 질문에 대한 **핵심 답변 한 문장**을 굵게 씁니다.
   - 본문: 질문 성격에 맞게 한눈에 보이도록 시각화합니다.
     · 비교 (트랙, 과정 종류, 장단점, 전/후 변화) → 마크다운 표
     · 과정, 일정, 절차, 성장 단계 → 단계 흐름 (예: 1단계 ➜ 2단계 ➜ 3단계) 과 기간이 있으면 표
     · 학습 팁, 준비 방법, 전략 → 이모지 불릿 3~5개
     · 소제목이 필요하면 #### 수준의 짧은 제목을 사용합니다.
   - 마지막 줄: "💪 " 로 시작하는 응원 한마디.
     질문자의 상황(비전공자, 직장인, 불안함, 진로 고민 등)을 짚어 구체적으로, 지금 바로 도전하고 싶어지게 씁니다.

3. 톤: 친근한 존댓말. 선배가 후배에게 말하듯 따뜻하지만 자신감 있게. 불필요한 서론 없이 바로 핵심부터.

4. 분량: 핵심 위주로 간결하게. 표나 단계 흐름은 적극 활용하되 같은 내용을 반복하지 않습니다.

5. 에이블스쿨과 관계없는 질문에는 짧게 답하고, 에이블스쿨 관련 질문으로 자연스럽게 이어 줍니다.

[백서 문서]
{context}"""

FOLLOWUP_PROMPT = """다음은 에이블스쿨 학습 도우미와 사용자의 대화입니다.
사용자가 이어서 궁금해할 만한 후속 질문 3개를 만들어 주세요.
- 에이블스쿨 백서로 답할 수 있는 내용이어야 합니다.
- 각 질문은 30자 이내, 사용자가 직접 묻는 말투로 씁니다.
- 번호나 기호 없이 한 줄에 하나씩만 출력합니다.

[질문]
{q}

[답변]
{a}"""


# ─────────────────────────────────────────────
# 2. RAG 파이프라인
# ─────────────────────────────────────────────
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def get_embedding():
    return OpenAIEmbeddings(model="text-embedding-3-small")


CONDENSE_PROMPT = """이전 대화를 참고해, 마지막 질문을 앞의 맥락 없이도 이해되는 하나의 검색용 질문으로 바꿔 주세요.
질문만 한 줄로 출력합니다.

[이전 대화]
{history}

[마지막 질문]
{input}"""


def build_chain(retriever):
    """검색 결과(docs)와 답변(answer)을 함께 돌려주는 RAG 체인"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("history"),
        ("human", "{input}"),
    ])
    llm = ChatOpenAI(model=MODEL, temperature=0.3, streaming=True)
    condense_llm = ChatOpenAI(model=MODEL, temperature=0)

    # "그럼 DX 트랙은요?" 같은 이어지는 질문도 백서에서 잘 찾도록 검색어 재작성
    def search_query(x):
        if not x.get("history"):
            return x["input"]
        hist = "\n".join(
            f"{'사용자' if isinstance(m, HumanMessage) else '도우미'}: {m.content[:300]}"
            for m in x["history"][-4:])
        try:
            return condense_llm.invoke(CONDENSE_PROMPT.format(history=hist, input=x["input"])).content.strip()
        except Exception:
            return x["input"]

    answer_chain = (
        RunnablePassthrough.assign(context=lambda x: format_docs(x["docs"]))
        | prompt
        | llm
        | StrOutputParser()
    )
    return (
        RunnablePassthrough.assign(docs=RunnableLambda(search_query) | retriever)
        .assign(answer=answer_chain)
    )


def rag_pipeline(path):
    """01번 노트북의 rag_pipeline(): PDF 경로 → 로드 → 분할 → 임베딩 → 벡터 저장소 → RAG 체인"""
    docs = PyMuPDF4LLMLoader(path).load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", " ", ""])
    chunks = splitter.split_documents(docs)

    # 업로드 문서는 메모리 저장소에 (이름 충돌 방지용 고유 컬렉션)
    vectorstore = Chroma.from_documents(
        chunks,
        get_embedding(),
        collection_name=f"upload_{uuid.uuid4().hex[:8]}")

    retriever = vectorstore.as_retriever(
        search_type="mmr", search_kwargs={"k": 6, "fetch_k": 20})
    return build_chain(retriever)


@st.cache_resource(show_spinner="백서를 불러오는 중입니다...")
def get_default_chain():
    """앱 시작 시 기본 백서 체인 (한 번만 생성되어 모든 세션이 공유)"""
    if os.path.isdir(CHROMA_DIR):
        vectorstore = Chroma(
            collection_name=COLLECTION,
            embedding_function=get_embedding(),
            persist_directory=CHROMA_DIR)
        if vectorstore._collection.count() > 0:
            retriever = vectorstore.as_retriever(
                search_type="mmr", search_kwargs={"k": 6, "fetch_k": 20})
            return build_chain(retriever)
    if os.path.exists(DEFAULT_PDF):
        return rag_pipeline(DEFAULT_PDF)
    return None


def suggest_followups(question, answer):
    try:
        llm = ChatOpenAI(model=MODEL, temperature=0.7)
        text = llm.invoke(FOLLOWUP_PROMPT.format(q=question, a=answer[:1500])).content
        lines = [re.sub(r"^[\s\-\d\.\)•·*]+", "", l).strip().strip('"') for l in text.splitlines()]
        return [l for l in lines if l][:3]
    except Exception:
        return []


# ─────────────────────────────────────────────
# 3. 세션 상태 (벡터화가 반복되지 않도록 State에 저장)
# ─────────────────────────────────────────────
defaults = {
    "messages": [],          # {"role", "content", "sources", "followups"}
    "chain": None,
    "document_name": None,
    "pending": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.chain is None:
    try:
        st.session_state.chain = get_default_chain()
        if st.session_state.chain is not None:
            st.session_state.document_name = DEFAULT_PDF
    except Exception as e:
        st.error(f"기본 백서를 불러오지 못했습니다: {e}")


def ask(q):
    st.session_state.pending = q


def clear_chat():
    st.session_state.messages = []
    st.session_state.pending = None


# ─────────────────────────────────────────────
# 4. 스타일
# ─────────────────────────────────────────────
st.markdown("""
<style>
:root { --aivle: #12B5A6; --aivle-dark: #0B8B80; --aivle-soft: #E8F8F6; }
.block-container { padding-top: 1.6rem; max-width: 1050px; }

/* 헤더 */
.hero {
  background: linear-gradient(120deg, #0B8B80 0%, #12B5A6 55%, #5FD3C6 100%);
  border-radius: 20px; padding: 26px 30px; color: #fff; margin-bottom: 18px;
  box-shadow: 0 10px 28px rgba(18,181,166,.25); position: relative; overflow: hidden;
}
.hero:after { content: "🚀"; position: absolute; right: 28px; top: 14px; font-size: 64px; opacity: .25; }
.hero h1 { color: #fff; font-size: 1.95rem; margin: 0 0 4px 0; padding: 0; }
.hero p { margin: 0; opacity: .93; font-size: 1.02rem; }
.badge { display: inline-block; background: rgba(255,255,255,.22); border-radius: 999px;
  padding: 3px 12px; font-size: .78rem; margin-bottom: 10px; }

/* 기능 카드 */
.feature { background: #fff; border: 1px solid #E3EEEC; border-radius: 16px; padding: 16px 18px;
  height: 100%; box-shadow: 0 2px 10px rgba(0,0,0,.03); }
.feature .ico { font-size: 1.6rem; }
.feature b { display: block; margin: 6px 0 2px; color: #134; }
.feature span { font-size: .86rem; color: #5b6b6a; }
.stat { background: #fff; border: 1px solid #E3EEEC; border-left: 5px solid var(--aivle);
  border-radius: 14px; padding: 12px 14px; }
.stat .num { font-size: 1.45rem; font-weight: 800; color: var(--aivle-dark); }
.stat .lbl { font-size: .8rem; color: #5b6b6a; }
.section-title { font-weight: 700; font-size: 1.08rem; margin: 22px 0 8px; color: #134; }

/* 버튼 */
div.stButton > button {
  border-radius: 12px; border: 1px solid #CFE9E5; background: #fff; color: #134;
  text-align: left; transition: all .15s ease; width: 100%;
}
div.stButton > button:hover { border-color: var(--aivle); background: var(--aivle-soft);
  color: var(--aivle-dark); transform: translateY(-1px); }

/* 사이드바 */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #F3FBFA 0%, #FFFFFF 100%); }
.doc-chip { background: var(--aivle-soft); border: 1px solid #BFE7E1; border-radius: 12px;
  padding: 8px 12px; font-size: .85rem; color: var(--aivle-dark); }

/* 채팅 */
[data-testid="stChatMessage"] { border-radius: 16px; padding: 10px 14px; }
[data-testid="stChatMessage"] table { width: 100%; }
[data-testid="stChatMessage"] th { background: var(--aivle-soft); }
.followup-label { font-size: .85rem; color: #5b6b6a; margin: 4px 0 2px; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# 5. 사이드바: 로고 / 관리자(문서 업로드) / 추천 질문 / 대화 삭제
# ─────────────────────────────────────────────
SIDEBAR_QUESTIONS = [
    "🎓 에이블스쿨은 어떤 곳인지 숫자로 한눈에 보여 주세요",
    "📊 AI 개발자 트랙과 DX 컨설턴트 트랙을 표로 비교해 주세요",
    "📝 지원 자격과 선발 절차를 단계별로 알려 주세요",
    "⏰ 하루 일정과 출석 규정은 어떻게 되나요?",
    "💼 수료 후에는 어떤 취업 지원을 받을 수 있나요?",
]

with st.sidebar:
    st.image(LOGO_URL)
    st.caption("에이블스쿨은 AI/DX 인재를 양성하는 KT의 교육 프로그램입니다.")

    st.markdown("#### 🔐 관리자")
    with st.expander("📂 백서 문서 업로드", expanded=st.session_state.chain is None):
        uploaded_file = st.file_uploader("PDF 업로드", type=["pdf"], label_visibility="collapsed")
        if uploaded_file:
            if st.session_state.document_name != uploaded_file.name:
                with st.spinner("문서를 처리하고 있습니다..."):
                    try:
                        # ① 임시 파일 생성 ② 내용 저장 ③ 경로 확보 ④ RAG 파이프라인에 '경로' 전달
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                            tmp.write(uploaded_file.read())
                            tmp_path = tmp.name
                        st.session_state.chain = rag_pipeline(tmp_path)
                        st.session_state.document_name = uploaded_file.name
                        st.session_state.messages = []
                        st.toast("새 문서로 학습 도우미가 준비되었어요! ✨")
                    except Exception as e:
                        st.error(f"문서 처리 중 오류: {e}")

    if st.session_state.document_name:
        st.markdown(f'<div class="doc-chip">📘 사용 중인 문서<br><b>{st.session_state.document_name}</b></div>',
                    unsafe_allow_html=True)
    else:
        st.warning("문서를 업로드해 주세요.")

    st.divider()
    st.markdown("#### 💡 추천 질문")
    for i, q in enumerate(SIDEBAR_QUESTIONS):
        st.button(q, key=f"side_q_{i}", on_click=ask, args=(q.split(" ", 1)[1],))

    st.divider()
    n_q = sum(1 for m in st.session_state.messages if m["role"] == "user")
    st.caption(f"💬 지금까지 나눈 질문: **{n_q}개**")
    st.button("🗑️ 대화 삭제", key="clear", on_click=clear_chat, type="primary")


# ─────────────────────────────────────────────
# 6. 헤더
# ─────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="badge">KT AIVLE School · 백서 기반 RAG 학습 도우미</div>
  <h1>AIVLE 메이트</h1>
  <p>먼저 걸어간 선배처럼, 백서에 근거해 정확하게 답하고 여러분의 도전을 진심으로 응원합니다.</p>
</div>
""", unsafe_allow_html=True)

user_input = st.chat_input("에이블스쿨에 대해 무엇이든 물어보세요 ✨")
if st.session_state.pending and not user_input:
    user_input = st.session_state.pending
st.session_state.pending = None


# ─────────────────────────────────────────────
# 7. 첫 화면 (대화가 없을 때)
# ─────────────────────────────────────────────
WELCOME_QUESTIONS = {
    "🤔 지원을 고민하고 있다면": [
        "비전공자인데 6개월 과정을 잘 따라갈 수 있을까요?",
        "저에게 맞는 트랙은 어떻게 고르면 되나요?",
    ],
    "📚 과정이 궁금하다면": [
        "입교하면 첫 8주는 어떻게 흘러가나요?",
        "미니프로젝트와 빅프로젝트는 뭐가 다른가요?",
    ],
    "🚀 성장과 수료 후가 궁금하다면": [
        "선배들은 어떤 공부법으로 성장했나요?",
        "에이블스쿨을 수료하면 무엇을 얻을 수 있나요?",
    ],
}

# 백서 01장 「숫자로 보는 에이블스쿨」
STATS = [("840시간", "이론·실습·프로젝트 (10기)"), ("약 3,500명", "누적 수료생"),
         ("500여 개", "수료생 진출 기업"), ("4회 연속", "KDT 해커톤 대상")]

if not st.session_state.messages and not user_input:
    st.markdown('<div class="section-title">📈 숫자로 보는 에이블스쿨</div>', unsafe_allow_html=True)
    for col, (num, label) in zip(st.columns(4), STATS):
        col.markdown(f'<div class="stat"><div class="num">{num}</div><div class="lbl">{label}</div></div>',
                     unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns(3)
    for col, (ico, title, desc) in zip(
        (c1, c2, c3),
        [("📘", "백서 기반 정확한 답변", "근거가 된 백서 내용을 함께 보여 드려요"),
         ("📊", "표·단계로 한눈에", "비교와 일정은 표와 흐름도로 정리해요"),
         ("💪", "도전을 응원해요", "내 상황에 맞춘 선배의 한마디까지")]):
        col.markdown(f'<div class="feature"><div class="ico">{ico}</div><b>{title}</b><span>{desc}</span></div>',
                     unsafe_allow_html=True)

    st.markdown('<div class="section-title">이런 것부터 물어보세요 👇</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for col, (cat, qs) in zip(cols, WELCOME_QUESTIONS.items()):
        with col:
            st.markdown(f"**{cat}**")
            for j, q in enumerate(qs):
                st.button(q, key=f"welcome_{cat}_{j}", on_click=ask, args=(q,))


# ─────────────────────────────────────────────
# 8. 대화 출력
# ─────────────────────────────────────────────
AVATAR = {"user": "🧑‍🎓", "assistant": "🤖"}


def render_sources(sources):
    if not sources:
        return
    with st.expander(f"📚 답변 근거 · 백서 발췌 {len(sources)}건"):
        for i, s in enumerate(sources, 1):
            page = f" · p.{s['page']}" if s.get("page") else ""
            st.markdown(f"**[{i}]{page}**")
            st.caption(s["text"])


def to_sources(docs):
    out = []
    for d in docs or []:
        page = d.metadata.get("page")
        if isinstance(page, int):
            page += 1
        text = d.page_content.strip().replace("\n", " ")
        out.append({"page": page, "text": text[:300] + ("…" if len(text) > 300 else "")})
    return out


last_idx = len(st.session_state.messages) - 1
for idx, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"], avatar=AVATAR[m["role"]]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            render_sources(m.get("sources"))
    # 마지막 답변 아래에 이어서 물어볼 질문
    if idx == last_idx and m["role"] == "assistant" and m.get("followups") and not user_input:
        st.markdown('<div class="followup-label">👉 이어서 물어보기</div>', unsafe_allow_html=True)
        fcols = st.columns(len(m["followups"]))
        for j, (fc, fq) in enumerate(zip(fcols, m["followups"])):
            fc.button(fq, key=f"follow_{idx}_{j}", on_click=ask, args=(fq,))


# ─────────────────────────────────────────────
# 9. 질문 처리
# ─────────────────────────────────────────────
if user_input:
    with st.chat_message("user", avatar=AVATAR["user"]):
        st.markdown(user_input)

    if st.session_state.chain is None:
        with st.chat_message("assistant", avatar=AVATAR["assistant"]):
            st.warning("먼저 왼쪽 '관리자' 메뉴에서 백서 PDF를 업로드해 주세요.")
        st.stop()

    history = []
    for m in st.session_state.messages[-HISTORY_TURNS:]:
        history.append(HumanMessage(m["content"]) if m["role"] == "user" else AIMessage(m["content"]))

    holder = {}

    def stream_answer():
        for chunk in st.session_state.chain.stream({"input": user_input, "history": history}):
            if "docs" in chunk:
                holder["docs"] = chunk["docs"]
            if "answer" in chunk:
                yield chunk["answer"]

    with st.chat_message("assistant", avatar=AVATAR["assistant"]):
        try:
            with st.spinner("백서에서 관련 내용을 찾고 있어요... 🔎"):
                answer = st.write_stream(stream_answer())
        except Exception as e:
            answer = f"⚠️ 답변 생성 중 문제가 발생했어요: {e}"
            st.error(answer)
        sources = to_sources(holder.get("docs"))
        render_sources(sources)

    with st.spinner("이어서 물어볼 질문을 고르는 중..."):
        followups = suggest_followups(user_input, answer if isinstance(answer, str) else "")

    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.messages.append({
        "role": "assistant", "content": answer if isinstance(answer, str) else str(answer),
        "sources": sources, "followups": followups,
    })
    st.rerun()
