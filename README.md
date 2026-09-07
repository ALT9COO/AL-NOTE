# AI Note — 업무 관리 · AI 회의 요약 대시보드

회의 녹음 한 번으로 회의록 요약부터 담당자별 업무 진행률 업데이트까지 자동화하는 사내용 B2B SaaS 스타일 대시보드입니다.

- **Frontend** — Next.js 14 (App Router) · TypeScript · Tailwind CSS · shadcn/ui · Recharts · @hello-pangea/dnd
- **Backend** — FastAPI · Pydantic v2 · SQLAlchemy 2.0 · SQLite
- **AI** — OpenAI GPT-4o / Anthropic Claude / Google Gemini 중 선택 연동 (JSON 구조화 파싱 · 경영 리포트) · Whisper STT
- **Auth** — JWT Bearer + passlib[bcrypt] + 역할 기반 접근 제어(RBAC)
- **Calendar** — 구성원별 Microsoft 365 캘린더 연동(Graph OAuth, 읽기 전용) → 일정 기준 회의록 작성

---

## 1. 빠른 시작

### 1) 백엔드 (터미널 1)

```bash
cd backend
python -m venv .venv                 # 최초 1회 (루트의 .venv 를 재사용해도 됩니다)
.venv\Scripts\activate               # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env               # macOS/Linux: cp .env.example .env
uvicorn main:app --reload --port 8000
```

- API 문서: http://127.0.0.1:8000/docs  (이 PC에서만)
- 최초 실행 시 `ainote.db` 가 생성되고 시드 데이터가 자동 입력됩니다.

### 2) 프런트엔드 (터미널 2)

```bash
cd frontend
npm install
npm run dev
```

- 접속: https://localhost:3001  (자체 서명 인증서 — 브라우저에서 고급 → 계속)
- API는 화면 주소의 `/api` 로만 호출되며, FastAPI는 PC 안에서만 동작합니다.

### 3) 테스트 계정

| 역할 | 아이디 | 비밀번호 | 소속 | 권한 |
| --- | --- | --- | --- | --- |
| ADMIN | `admin` | `admin123` | 경영지원본부 | 전사 업무 조회·수정, 전사 애널리틱스 |
| LEADER | `leader1` | `leader123` | 개발팀 | 소속 부서 + 하위 부서 업무 조회·수정 |
| MEMBER | `member1` | `member123` | 개발팀 | 팀 업무 조회, 본인 담당 업무만 수정 |
| MEMBER | `member2` | `member123` | 개발팀 | 동일 |

로그인 화면의 테스트 계정 카드를 클릭하면 자동 입력됩니다.

---

## 2. AI 프로바이더 연동

OpenAI · Anthropic Claude · Google Gemini 중 하나를 골라 연결합니다. 권장 경로는
**설정 → API 연동 탭**(ADMIN 전용)에서 키를 입력하고 *연결 테스트* 후 *이 엔진 사용* 을 누르는 것입니다.
DB(`api_settings`)에 저장되므로 서버를 재시작해도 유지되고, 응답에는 마스킹된 키만 노출됩니다.

| 프로바이더 | 기본 모델 | 키 발급 | 비고 |
| --- | --- | --- | --- |
| OpenAI | `gpt-4o` | platform.openai.com | 음성 전사(Whisper)까지 단일 키로 지원 |
| Anthropic Claude | `claude-3-5-sonnet-latest` | console.anthropic.com | 텍스트 전용 |
| Google Gemini | `gemini-2.0-flash` | aistudio.google.com | 텍스트 전용, `AIza` 로 시작하는 키 |

초기값을 파일로 넣고 싶다면 `backend/.env` 를 사용합니다.

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=AIza...
```

**음성 전사(STT)는 Whisper 전용**이라 활성 엔진과 무관하게 OpenAI 키가 필요합니다. Claude/Gemini 만
연결한 경우 요약·리포트는 실제 AI 로, 전사는 데모 응답으로 동작합니다.

키가 하나도 없으면 `ALLOW_MOCK_AI=True` 설정에 따라 **데모 모드**로 동작합니다. 데모 모드에서도 전사 →
요약 → 안건 검토 → 업무 반영까지 전체 플로우를 그대로 체험할 수 있으며, 사이드바의 *AI 엔진 상태*
배지와 결과 화면 상단 배너로 데모 여부를 표시합니다.

---

## 3. 주요 기능

### 인증 & RBAC
- JWT Bearer 토큰(localStorage 저장) + bcrypt 해싱
- 부서 트리를 재귀 탐색해 LEADER 의 하위 부서 업무까지 권한 범위에 포함
- 조회 권한과 수정 권한을 분리해 응답의 `can_edit` 플래그로 UI(잠금 아이콘, 드래그 비활성화)에 반영

### 업무 진행 현황 (`/dashboard`) — 칸반 · 타임라인 · 캘린더
상단 토글로 같은 데이터를 세 가지 방식으로 봅니다. 검색·담당자 필터와 통계 카드는 뷰와 무관하게 공통 적용됩니다.

- **칸반** — `시작전 / 진행중 / 검토필요 / 완료` 4개 컬럼, 드래그 앤 드롭으로 상태 변경.
  드롭 즉시 `PATCH /api/tasks/{id}/status` 호출 → 상태별 기본 진행률(0/50/90/100%)로 자동 보정하고,
  낙관적 업데이트 후 실패 시 이전 상태로 롤백합니다.
  카드는 업무 ID · 담당자 아바타 · 진행률 바 · D-day 배지 · 이슈 태그를 표시합니다.
- **타임라인** — 착수일~마감일을 간트 형태 막대로 표시. 담당자별 / 상태별 / 전체 그룹 전환, 막대 내부에
  진행률 채움, 오늘 날짜 세로선, 지연 업무 강조, 주말 음영 처리. 막대를 클릭하면 수정 다이얼로그가 열립니다.
- **캘린더** — 마감일 기준 월간 그리드. 상태 색상 칩(실선)은 마감일, 점선 칩은 착수일이며 하루 3건 초과 시
  `+N건` 으로 접힙니다. 기한이 없는 업무는 하단에 따로 모아 보여줍니다.
- 공통: 업무 생성/수정/삭제 다이얼로그, 담당자·키워드 필터

### AI 회의실 (`/meetings`)
1. **음성 입력** — 브라우저 녹음(MediaRecorder) 또는 오디오 파일 업로드(최대 200MB), 텍스트 직접 입력도 지원
2. **전사 확인** — Whisper 전사 결과를 직접 수정 가능
3. **안건 검토 · 제출** — GPT-4o 가 요약·안건·액션 아이템·리스크·업무 업데이트를 JSON 으로 추출하고,
   각 업무 제안을 카드에서 담당자/상태/진행률/마감일/이슈까지 수정한 뒤 선택 제출
4. **일괄 반영** — 제출 시 Tasks 테이블 업데이트(권한 없는 항목은 자동 제외) + 회의록 저장

### 내 캘린더 연동 (Microsoft 365 · Graph)
회의실 상단의 **내 캘린더 일정** 카드에서 구성원이 각자 자기 Microsoft 계정을 연결합니다(위임 권한,
읽기 전용). 조직 전체에서 **Azure AD 앱 등록 1건**만 준비하면 됩니다.

**① 관리자: Azure 앱 등록 (최초 1회)**
1. Azure Portal → Microsoft Entra ID → 앱 등록 → 새 등록
2. 이름은 자유롭게(예: AI Note 캘린더), 계정 유형은 보통 '이 조직 디렉터리의 계정만'
3. 리디렉션 URI: 플랫폼 **웹**, 값은 `https://localhost:3001/api/calendar/callback`
   (배포 시 실제 백엔드 주소로 변경, Azure 등록값과 **문자 단위로 동일**해야 함)
4. API 사용 권한 → Microsoft Graph → **위임된 권한** → `Calendars.Read` · `offline_access` · `User.Read`
5. 인증서 및 비밀 → 새 클라이언트 비밀 → 생성된 **값**을 복사(다시 볼 수 없음)
6. 앱에서 **설정 → 캘린더 연동** 탭에 클라이언트 ID · 테넌트 ID · 비밀 · 리디렉션 URI 입력
   (또는 `backend/.env` 의 `MS_CLIENT_ID` / `MS_CLIENT_SECRET` / `MS_TENANT_ID` / `MS_REDIRECT_URI`)

`Calendars.Read` 는 사용자 동의만으로 부여되는 권한이라 보통 관리자 동의가 필요 없습니다. 테넌트에서
사용자 동의를 막아 두었다면 관리자가 '관리자 동의 허용'을 한 번 눌러야 합니다.

**② 구성원: 내 계정 연결**
AI 회의실 → **Microsoft 계정 연결** → Microsoft 로그인 → 자동으로 회의실 화면으로 복귀. 서버는 그 사용자의
액세스·리프레시 토큰만 보관하며, 만료 5분 전에 자동 갱신합니다. 갱신이 불가능해지면(비밀번호 변경·동의 철회 등)
카드에 재연결 안내가 뜹니다.

**동작**
- Graph `calendarView` 로 앞뒤 2주 일정을 가져오며, **반복 일정은 회차별로 펼쳐진 상태**로 옵니다.
  `Prefer: outlook.timezone` 헤더로 한국 시간 기준으로 받습니다.
- 일정의 **이 회의 기록** 을 누르면 그 회의가 선택되고, 이후 저장되는 회의록에 일정 제목·시작 시각·장소가
  함께 기록됩니다. 회의 제목을 매번 타이핑할 필요가 없습니다.
- 참석자 명단을 사내 계정과 자동 대조해(`사내 N명 매칭`) AI 파싱 시 담당자 지목 정확도를 높입니다.
- Teams 회의는 참가 링크를 인식해 **Teams** 배지를 붙입니다.
- 이미 회의록이 저장된 일정에는 **회의록 저장됨** 배지가 붙어 중복 작성을 막습니다(열람 권한이 있는 회의록만).
- 연결 없이 **샘플로 미리보기** 를 눌러 동작만 먼저 확인할 수 있습니다.
- 캘린더는 **읽기 전용**으로만 접근하며, 회의록을 캘린더에 되쓰거나 메일을 보내지 않습니다.

### AI 경영 리포트 (`/analytics`)
- 주간/월간/분기/연간 · 부서별 필터
- Recharts: 상태 분포 도넛, 완료 추이 영역 차트, 담당자별 막대, 부서별 평균 진행률
- GPT-4o 기반 경영진 요약 보고서(총평 / 주요 성과 / 지연·병목 / 리스크 / 권고 액션)

### 설정 (`/settings`) — ADMIN 전용
사이드바 메뉴 자체가 ADMIN 계정에만 노출되며, URL 로 직접 접근해도 안내 카드로 차단됩니다(API 도 403).

- **사용자 관리** — 계정 등록(아이디·이름·초기 비밀번호·권한·부서), 소속 부서 즉시 변경, 비밀번호 초기화,
  계정 삭제. 담당 업무가 있는 계정은 인수인계 대상을 지정해야 삭제되며 업무가 함께 이관됩니다.
- **조직 관리** — 부서 등록·이름 변경·상위 부서 재지정(트리 들여쓰기 표시), 부서별 인원/업무 건수 표시.
  하위 부서·소속 구성원·등록된 업무가 남아 있으면 삭제를 차단합니다.
- **권한 설정** — ADMIN / LEADER / MEMBER 등급별 권한 범위를 카드로 안내하고, 구성원을 다른 등급으로 이동.
  본인 권한 변경과 마지막 관리자 계정의 강등·삭제는 잠금 처리되어 관리자 부재 상태를 만들 수 없습니다.
- **API 연동** — OpenAI / Claude / Gemini 카드에서 키 등록·모델 선택·연결 테스트·활성 엔진 지정.
  키는 마스킹 표시되며 삭제 시 활성 엔진은 키가 있는 다른 프로바이더로 자동 이관됩니다.
  아래 **실시간 사용량** 패널은 8초 주기로 폴링(일시정지 가능)하며 호출 수·토큰·추정 비용·평균 응답시간,
  일자별 추이, 기능별(음성 전사 / 회의 파싱 / 경영 리포트 / 연결 테스트) 분포, 프로바이더별 집계,
  최근 호출 로그(성공·실패·데모 구분, 실패 사유 툴팁)를 보여줍니다.
- **캘린더 연동** — Microsoft 365 캘린더용 Azure 앱 등록 정보(클라이언트 ID · 테넌트 ID · 비밀 · 리디렉션 URI)를
  입력합니다. 비밀은 마스킹되어 표시되고, 오른쪽에 Azure 앱 등록 절차와 요청할 권한 목록이 함께 있어 IT 담당자에게
  그대로 전달할 수 있습니다. 등록을 삭제하면 모든 구성원의 캘린더 연결도 함께 해제됩니다.

---

## 4. 프로젝트 구조

```
├── backend/
│   ├── main.py              # FastAPI 엔트리포인트, CORS · 예외 핸들러
│   ├── config.py            # 환경 변수(Pydantic Settings), 상태값 상수
│   ├── database.py          # SQLAlchemy 엔진 · 모델 · 시드 데이터
│   ├── auth.py              # JWT 발급/검증, bcrypt, RBAC 유틸
│   ├── ai_engine.py         # 멀티 프로바이더 엔진(OpenAI/Claude/Gemini) · STT · 사용량 기록
│   ├── calendar_service.py  # Graph OAuth 토큰 교환/갱신 · 일정 조회 · 참석자 매칭
│   ├── schemas.py           # Pydantic v2 요청/응답 스키마
│   ├── serializers.py       # ORM → 응답 스키마 변환
│   ├── smoke_test.py        # API 통합 스모크 테스트
│   └── routers/
│       ├── auth_router.py   # 로그인, 내 정보, 사용자/부서 목록
│       ├── task_router.py   # 업무 CRUD · 상태 변경 · 애널리틱스
│       ├── meeting_router.py# STT · 회의 파싱 · 안건 제출 · 회의록
│       ├── calendar_router.py # MS 로그인/콜백 · 일정 조회 · (ADMIN) Azure 앱 설정
│       └── admin_router.py  # (ADMIN) 사용자 · 조직 · 권한 · API 연동 · 사용량
│
├── frontend/
│   ├── app/
│   │   ├── login/           # 로그인 페이지
│   │   └── (app)/           # 인증 필요 영역 (dashboard · meetings · analytics · settings)
│   ├── components/
│   │   ├── ui/              # shadcn/ui 프리미티브
│   │   ├── layout/          # 사이드바 · 앱 셸
│   │   ├── kanban/          # KanbanBoard · TaskCard · TaskDialog
│   │   ├── views/           # TimelineView(간트) · CalendarView(월간)
│   │   ├── meetings/        # AudioRecorder · CalendarPanel · AgendaReview · MeetingHistory
│   │   ├── analytics/       # Recharts 차트 카드
│   │   └── settings/        # UserManager · DepartmentManager · RoleGuide
│   │                        # · ApiIntegrations · UsageMonitor
│   ├── lib/                 # API 클라이언트 · 인증 컨텍스트 · 유틸
│   └── types/               # 공용 TypeScript 인터페이스
│
└── legacy_streamlit/        # 이전 Streamlit 버전 (참고용, 삭제해도 무방)
```

---

## 5. API 요약

| Method | Endpoint | 설명 |
| --- | --- | --- |
| POST | `/api/auth/login` | 로그인 → JWT 발급 |
| GET | `/api/auth/me` | 내 정보 |
| GET | `/api/auth/users` · `/departments` | 권한 범위 내 사용자·부서 목록 |
| GET/POST | `/api/tasks` | 업무 목록 조회 / 생성 |
| PATCH | `/api/tasks/{id}` | 업무 수정 |
| PATCH | `/api/tasks/{id}/status` | 칸반 드래그 상태 변경 |
| DELETE | `/api/tasks/{id}` | 업무 삭제 |
| POST | `/api/meetings/transcribe` | 오디오 → Whisper 전사 |
| POST | `/api/meetings/parse` | 전사 → GPT-4o 구조화 JSON |
| POST | `/api/meetings/submit` | 안건 확정 → 업무 일괄 반영 + 회의록 저장 |
| GET | `/api/meetings` | 회의록 목록 |
| GET/DELETE | `/api/calendar/connection` | 내 캘린더 연결 상태 조회 / 해제 |
| GET | `/api/calendar/login-url` | Microsoft 로그인 주소 발급(state 서명 포함) |
| GET | `/api/calendar/callback` | OAuth 콜백 — 토큰 저장 후 회의실로 리디렉트 |
| POST | `/api/calendar/sync` | 토큰 갱신 + 일정 재조회 |
| GET | `/api/calendar/events?days_ahead=14` | 내 일정 목록(참석자 매칭 · 회의록 연결 여부) |
| GET/PUT/DELETE | `/api/calendar/app` | (ADMIN) Azure 앱 등록 정보 조회 / 저장 / 삭제 |
| GET/POST | `/api/admin/users` | (ADMIN) 전체 사용자 목록 / 사용자 등록 |
| PATCH | `/api/admin/users/{id}` | (ADMIN) 이름·부서·권한 등급·비밀번호 변경 |
| DELETE | `/api/admin/users/{id}?reassign_to=` | (ADMIN) 사용자 삭제 + 담당 업무 인수인계 |
| GET/POST | `/api/admin/departments` | (ADMIN) 조직도 조회 / 부서 등록 |
| PATCH/DELETE | `/api/admin/departments/{id}` | (ADMIN) 부서명·상위 부서 변경 / 삭제 |
| GET | `/api/admin/integrations` | (ADMIN) 프로바이더별 연동 상태 (키 마스킹) |
| PATCH | `/api/admin/integrations/{provider}` | (ADMIN) 키 저장·삭제, 모델 변경, 활성 엔진 지정 |
| POST | `/api/admin/integrations/{provider}/test` | (ADMIN) 실제 호출로 연결 테스트 |
| GET/DELETE | `/api/admin/usage?days=7` | (ADMIN) 사용량 집계 조회 / 로그 초기화 |
| GET | `/api/analytics/summary` | 기간·부서별 통계 |
| POST | `/api/analytics/report` | AI 경영 리포트 생성 |
| GET | `/api/health` | 헬스 체크 + AI 엔진 상태 |

---

## 6. 검증

백엔드를 띄운 뒤 아래를 실행하면 인증·RBAC·CRUD·회의 파이프라인·애널리틱스·관리자 기능·API 연동·
캘린더 연동을 한 번에 점검합니다(총 28개 항목). 캘린더 항목은 실제 Microsoft 로그인 없이 검증할 수 있도록
Azure 앱 설정 권한·마스킹·로그인 URL 생성과 샘플 일정 기반 회의록 연결을 확인하며, 테스트로 저장한 앱 정보와
회의록은 실행 끝에 자동으로 정리됩니다.

```bash
cd backend
python smoke_test.py
```

데이터를 초기 상태로 되돌리려면 `backend/ainote.db` 를 삭제하고 서버를 재시작하세요.
