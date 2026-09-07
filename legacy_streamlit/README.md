# 🧠 AI Note — 업무 관리 · AI 회의록 · 자동 업무 업데이트 대시보드

회의 녹음 파일 하나로 **회의록 요약 → 안건/액션 아이템 추출 → 업무 현황 자동 업데이트**까지 처리하는 사내용 Streamlit 대시보드입니다.

## 주요 기능

| 기능 | 설명 |
|---|---|
| 인증 & RBAC | bcrypt 비밀번호 해싱, 세션 기반 로그인, ADMIN/LEADER/MEMBER 3단계 권한 |
| 칸반 보드 | `시작전 / 진행중 / 검토필요 / 완료` 4단 칸반, 카드 이동·진행률·이슈 즉시 수정, 모달 등록/편집 |
| AI 회의실 | 파일 업로드 또는 브라우저 녹음 → Whisper STT → LLM 구조화 파싱 → **사람 검토(Human-in-the-Loop)** → 업무 일괄 반영 |
| AI 리포트 | 주간/월간/분기/연간 집계 + LLM 경영진 요약 리포트(성과·병목·리스크) 생성 및 다운로드 |
| 관리자 콘솔 | 사용자 생성/권한·부서 변경/비밀번호 초기화, 부서 트리 관리 |

## 권한 정책 (RBAC)

| 역할 | 조회 범위 | 수정 범위 |
|---|---|---|
| `MEMBER` | 본인 업무 + 소속 팀 업무 | 본인 담당 업무만 |
| `LEADER` | 소속 부서 + 모든 하위 부서 | 소속 부서 + 하위 부서 |
| `ADMIN` | 전사 전체 | 전사 전체 + 사용자/부서 관리 |

모든 DB 조회는 `auth.visible_tasks_stmt()` 를 거치며, 쓰기 작업은 `auth.can_edit_task()` 로 한 번 더 검증합니다.

## 설치 및 실행

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env          # macOS/Linux: cp .env.example .env
# .env 에 OPENAI_API_KEY 입력

streamlit run app.py
```

> API 키가 없어도 실행됩니다. `ALLOW_MOCK_AI=True` 이면 STT/LLM 호출이 데모 응답으로 대체되어 전체 워크플로우를 그대로 체험할 수 있습니다.

첫 실행 시 `ainote.db` 가 생성되고 시드 데이터(부서 2개, 사용자 4명, 업무 5건)가 자동 입력됩니다.

## 테스트 계정

| 역할 | 아이디 | 비밀번호 | 소속 |
|---|---|---|---|
| ADMIN | `admin` | `admin123` | 경영지원본부 |
| LEADER | `leader1` | `leader123` | 개발팀 |
| MEMBER | `member1` | `member123` | 개발팀 |
| MEMBER | `member2` | `member123` | 개발팀 |

## 환경 변수 (`.env`)

| 키 | 기본값 | 설명 |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai` 또는 `gemini` |
| `OPENAI_API_KEY` | – | Whisper STT + GPT 파싱용 (STT 는 항상 OpenAI 사용) |
| `OPENAI_TEXT_MODEL` | `gpt-4o-mini` | 파싱/요약 모델 (`gpt-4o` 권장 시 변경) |
| `OPENAI_STT_MODEL` | `whisper-1` | STT 모델 |
| `GEMINI_API_KEY` / `GEMINI_TEXT_MODEL` | – / `gemini-1.5-flash` | Gemini 사용 시 |
| `DB_URL` | `sqlite:///ainote.db` | SQLAlchemy 접속 URL |
| `ALLOW_MOCK_AI` | `True` | 키가 없을 때 데모 응답 사용 여부 |

## 파일 구조

```
├── app.py                  # Streamlit 엔트리포인트, 네비게이션, 관리자 콘솔
├── config.py               # 환경변수·상태값·색상 등 전역 설정
├── database.py             # SQLAlchemy 모델, 엔진, 시드 데이터
├── auth.py                 # bcrypt 해싱, 세션 로그인, RBAC 유틸
├── ai_engine.py            # Whisper STT, LLM JSON 파싱, 리포트 생성
├── components/
│   ├── kanban.py           # 칸반 보드
│   ├── meeting_room.py     # 녹음/STT/검토/제출 워크플로우
│   └── ai_analytics.py     # 주기별 AI 요약 대시보드
├── smoke_test.py           # DB·인증·RBAC·AI 파이프라인 스모크 테스트
└── requirements.txt
```

## AI 회의실 사용 흐름

1. **음성 입력** — `.mp3 / .m4a / .wav` 업로드, 브라우저 마이크 녹음, 또는 텍스트 직접 입력
2. **STT** — Whisper 로 전사, 결과 텍스트는 직접 수정 가능
3. **AI 분석** — LLM 이 `response_format={"type":"json_object"}` 로 요약·안건·액션 아이템·업무 업데이트를 구조화
4. **검토** — 안건 카드에서 연결 업무/담당자/상태/진행률/마감일/이슈를 수정하고 반영 여부 선택
5. **최종 제출** — 선택된 항목이 `Tasks` 테이블에 반영되고 회의록이 `Meetings` 에 저장 (권한 없는 업무는 자동 skip)

LLM 응답은 `ai_engine.normalize_parsed()` 에서 상태값 검증, 진행률 0~100 클램프, 업무명 유사도 매칭(`difflib`), 담당자 ID 매칭을 거치므로 잘못된 출력이 그대로 DB 에 들어가지 않습니다.

## 검증

```bash
python smoke_test.py
```

DB 초기화 → 로그인/실패 케이스 → 역할별 조회·수정 범위 → STT → 회의 파싱 → 업무 CRUD → 리포트 생성까지 순차 확인합니다.
