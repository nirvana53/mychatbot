"""전역 설정.

경로, DB 위치, 사용할 LLM 백엔드 등 프로그램 전체에서 공유하는 값을 모아둔다.
회사 내부 AI agent API가 준비되면 ACTIVE_LLM_BACKEND 값만 "internal_agent"로
바꾸고 llm/internal_agent_client.py 안의 요청 코드만 채우면 된다.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# 결산 원본 엑셀/CSV 파일을 넣어두는 폴더. 사용자는 이 폴더에 파일만 갖다 놓으면 된다.
RAW_DATA_DIR = BASE_DIR / "data" / "raw"

# 원본 파일을 적재해서 만드는 SQLite DB (질문에 답할 때 이 DB를 조회한다)
DB_PATH = BASE_DIR / "data" / "finance.db"

# 사용자 질문/답변 로그 (감사 목적, 외부 전송 없음, 로컬 파일로만 저장)
QUERY_LOG_PATH = BASE_DIR / "data" / "query_log.csv"

# 접속 비밀번호 등 민감 설정. 실제 값은 auth_config.json에 두고 이 파일은
# 코드 저장소에 올리지 않는다(.gitignore 처리).
AUTH_CONFIG_PATH = BASE_DIR / "auth_config.json"

# 사용할 LLM 백엔드: "mock"(현재 기본값) 또는 "internal_agent"(회사 내부 AI agent 연동 후)
ACTIVE_LLM_BACKEND = "mock"

# 내부 AI agent API 연동 정보 (현재는 비어 있음, 나중에 값만 채우면 됨)
INTERNAL_AGENT_CONFIG = {
    "endpoint": "",   # 예: "https://internal-ai-agent.company.local/v1/chat"
    "api_key": "",    # 예: 사내 발급 키. 환경변수나 별도 secret 파일 사용을 권장
    "model": "",      # 예: 사내 LLM 모델 이름
    "timeout": 30,
}
