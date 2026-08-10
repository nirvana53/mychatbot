"""결산 챗봇 Streamlit 앱.

같은 본부 인원이 내부망에서 브라우저로 접속해서 사용하는 채팅형 UI.
데이터는 로컬 SQLite(data/finance.db)만 조회하며 외부로 전송되지 않는다.
LLM 답변 생성은 llm.get_llm_client()가 반환하는 백엔드(현재는 Mock)가
담당하며, 내부 AI agent API가 준비되면 config.ACTIVE_LLM_BACKEND만
바꿔서 교체한다.
"""

import pandas as pd
import streamlit as st

import auth
import chatbot
import charts
import config
from data_pipeline import ingest as ingest_module
from query_engine import query

st.set_page_config(page_title="결산 챗봇", page_icon="📊")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("결산 챗봇 - 접속 인증")
    st.caption("본부 내부 결산 데이터를 다루는 프로그램입니다. 담당자에게 받은 접속 비밀번호를 입력하세요.")
    name = st.text_input("이름 또는 사번 (질문 기록에 남습니다)")
    pw = st.text_input("접속 비밀번호", type="password")
    if st.button("입장"):
        if not name.strip():
            st.error("이름 또는 사번을 입력해 주세요.")
        elif auth.check_password(pw):
            st.session_state.authenticated = True
            st.session_state.user_name = name.strip()
            st.rerun()
        else:
            st.error("비밀번호가 올바르지 않습니다.")
    st.stop()

if auth.using_default_password():
    st.warning(
        "기본 비밀번호(changeme)를 아직 변경하지 않았습니다. "
        f"{config.AUTH_CONFIG_PATH} 파일에서 반드시 변경하세요.",
        icon="⚠️",
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "followup_context" not in st.session_state:
    st.session_state.followup_context = None

FAQ_QUESTIONS = [
    "이번분기 영업이익 알려줘",
    "매출 추이 보여줘",
    "작년 4분기랑 이번분기 순이익 비교해줘",
    "영업이익 법인별로 보여줘",
    "판관비 세부적으로 보여줘",
    "매출 이상치 있는 법인 알려줘",
    "계정 목록 보여줘",
]

st.title("📊 결산 챗봇")
st.caption("로컬 연결결산 데이터(SQLite)를 기반으로 답변합니다. 데이터는 외부로 전송되지 않습니다.")

with st.sidebar:
    st.header("사용 안내")
    st.caption("자유롭게 표현해도 되고, 아래 버튼을 눌러 바로 물어볼 수도 있습니다.")
    for faq in FAQ_QUESTIONS:
        if st.button(faq, key=f"faq-{faq}", use_container_width=True):
            st.session_state.pending_prompt = faq
            st.rerun()
    st.caption("답변 기본값은 '연결 기준'(법인 20개 + 연결조정 합산)입니다. 법인명을 언급하면 그 법인만 조회합니다.")

    accounts = query.list_accounts()
    entities = query.list_entities()
    if accounts.get("level1"):
        st.success(f"대분류 {len(accounts['level1'])}개 · 중분류 {len(accounts['level2'])}개 · 세부계정 {len(accounts['level3'])}개 · 법인 {len(entities)}개")
        with st.expander("대분류 / 계산지표 목록"):
            st.write("대분류: " + ", ".join(accounts["level1"]))
            st.write("계산지표: " + ", ".join(accounts["metrics"]))
            st.write("비율지표: " + ", ".join(accounts.get("ratios", [])))
        with st.expander("법인 목록"):
            st.write(", ".join(entities))
    else:
        st.error("적재된 결산 데이터가 없습니다. data/raw에 파일을 넣고 아래 버튼을 눌러 적재하세요.")

    if st.button("결산 데이터 다시 적재"):
        with st.spinner("data/raw 폴더의 파일을 읽는 중..."):
            ingest_module.ingest()
        st.success("적재가 끝났습니다.")
        st.rerun()

    st.divider()
    with st.expander("최근 미해결 질문 (관리용)"):
        if config.QUERY_LOG_PATH.exists():
            log_df = pd.read_csv(config.QUERY_LOG_PATH)
            unresolved = log_df[log_df.get("status") == "unresolved"] if "status" in log_df.columns else log_df.iloc[0:0]
            if unresolved.empty:
                st.caption("미해결로 남은 질문이 없습니다.")
            else:
                cols = [c for c in ["timestamp", "user", "question"] if c in unresolved.columns]
                st.dataframe(unresolved[cols].tail(20), hide_index=True, use_container_width=True)
        else:
            st.caption("로그가 아직 없습니다.")

    st.divider()
    st.caption(f"로그인: {st.session_state.get('user_name', '-')} · 현재 LLM 백엔드: {config.ACTIVE_LLM_BACKEND}")


def _render_chart(chart: dict):
    if not chart:
        return
    if chart["type"] == "line":
        st.altair_chart(charts.trend_line_chart(chart["rows"], chart["label"], chart["unit"]), use_container_width=True)
    elif chart["type"] == "bar":
        st.altair_chart(charts.breakdown_bar_chart(chart["rows"], chart["label"], chart["unit"]), use_container_width=True)


def _render_download(table: list, key: str):
    if not table:
        return
    csv_bytes = pd.DataFrame(table).to_csv(index=False).encode("utf-8-sig")
    st.download_button("결과 CSV로 받기", data=csv_bytes, file_name="결산_조회결과.csv", mime="text/csv", key=key)


for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        _render_chart(msg.get("chart"))
        _render_download(msg.get("table"), key=f"download-{i}")
        is_last = i == len(st.session_state.messages) - 1
        if is_last and msg.get("suggestions"):
            st.caption("이렇게 더 물어볼 수 있어요:")
            cols = st.columns(len(msg["suggestions"]))
            for col, suggestion in zip(cols, msg["suggestions"]):
                if col.button(suggestion, key=f"suggestion-{i}-{suggestion}"):
                    st.session_state.pending_prompt = suggestion
                    st.rerun()

prompt = st.session_state.pending_prompt or st.chat_input("결산 관련 질문을 입력하세요 (예: 이번분기 영업이익 알려줘)")
st.session_state.pending_prompt = None

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        with st.spinner("조회 중..."):
            result = chatbot.answer(
                prompt, user=st.session_state.get("user_name", ""),
                followup_context=st.session_state.followup_context,
            )
        st.write(result["text"])
        _render_chart(result["chart"])
        _render_download(result["table"], key=f"download-new-{len(st.session_state.messages)}")

    if result["followup_context"]:
        st.session_state.followup_context = result["followup_context"]

    st.session_state.messages.append({
        "role": "assistant",
        "content": result["text"],
        "chart": result["chart"],
        "table": result["table"],
        "suggestions": result["suggestions"],
    })
    st.rerun()
