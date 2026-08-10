"""아주 단순한 공용 비밀번호 게이트.

같은 본부 인원만 쓰도록 접속 시 비밀번호 하나를 확인한다. SSO 같은
정식 인증은 아니지만, 예산 0원 + 로컬 실행 + 내부망 한정 공유라는
조건에서 최소한의 접근 제한 역할을 한다. 비밀번호는 코드에 넣지 않고
auth_config.json(코드 저장소에 올리지 않는 파일)에만 둔다.
"""

import json

import config

DEFAULT_PASSWORD = "changeme"


def _ensure_config() -> None:
    if not config.AUTH_CONFIG_PATH.exists():
        config.AUTH_CONFIG_PATH.write_text(
            json.dumps({"password": DEFAULT_PASSWORD}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _load() -> dict:
    _ensure_config()
    return json.loads(config.AUTH_CONFIG_PATH.read_text(encoding="utf-8"))


def check_password(input_password: str) -> bool:
    return input_password == _load().get("password")


def using_default_password() -> bool:
    return _load().get("password") == DEFAULT_PASSWORD
