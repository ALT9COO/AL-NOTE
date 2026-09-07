"""관리자 전용 — 사용자 등록 · 조직 관리 · 권한 설정 · API 연동 라우터."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import ai_engine
from auth import CurrentUser, DbSession, hash_password, mark_password_state, require_roles
from config import AI_PROVIDERS
from secret_box import reveal, seal
from database import ApiSetting, ApiUsage, Department, Task, User, get_descendant_dept_ids
from schemas import (
    AdminDepartmentCreate,
    AdminDepartmentOut,
    AdminDepartmentUpdate,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    ConnectionTestResult,
    IntegrationListResponse,
    IntegrationOut,
    IntegrationUpdate,
    UsageByFeature,
    UsageByProvider,
    UsageDailyPoint,
    UsageLogOut,
    UsageResponse,
    UsageTotals,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_roles("ADMIN"))],
)


# --------------------------------------------------------------------------- #
# 공통 헬퍼
# --------------------------------------------------------------------------- #
def _task_counts(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(Task.assigned_to, func.count())
        .where(Task.deleted_at.is_(None))
        .group_by(Task.assigned_to)
    ).all()
    return {uid: count for uid, count in rows if uid}


def _dept_task_counts(db: Session) -> dict[int, int]:
    rows = db.execute(
        select(Task.dept_id, func.count())
        .where(Task.deleted_at.is_(None))
        .group_by(Task.dept_id)
    ).all()
    return {did: count for did, count in rows if did is not None}


def _dept_user_counts(db: Session) -> dict[int, int]:
    rows = db.execute(select(User.dept_id, func.count()).group_by(User.dept_id)).all()
    return {did: count for did, count in rows if did is not None}


def _admin_count(db: Session, exclude: str | None = None) -> int:
    stmt = select(func.count()).select_from(User).where(User.role_level == "ADMIN")
    if exclude:
        stmt = stmt.where(User.user_id != exclude)
    return int(db.scalar(stmt) or 0)


def _require_department(db: Session, dept_id: int | None) -> None:
    if dept_id is not None and db.get(Department, dept_id) is None:
        raise HTTPException(status_code=404, detail=f"부서 {dept_id} 를 찾을 수 없습니다.")


def _user_out(db: Session, user: User, current: User, counts: dict[str, int]) -> AdminUserOut:
    return AdminUserOut(
        user_id=user.user_id,
        user_name=user.user_name,
        role_level=user.role_level,  # type: ignore[arg-type]
        job_title=user.job_title or "",
        dept_id=user.dept_id,
        dept_name=user.department.dept_name if user.department else None,
        created_at=user.created_at,
        task_count=counts.get(user.user_id, 0),
        is_self=user.user_id == current.user_id,
    )


# --------------------------------------------------------------------------- #
# 사용자 관리
# --------------------------------------------------------------------------- #
@router.get("/users", response_model=list[AdminUserOut])
def list_users(current: CurrentUser, db: DbSession) -> list[AdminUserOut]:
    counts = _task_counts(db)
    users = db.scalars(select(User).order_by(User.role_level, User.user_name)).unique().all()
    return [_user_out(db, u, current, counts) for u in users]


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: AdminUserCreate, current: CurrentUser, db: DbSession) -> AdminUserOut:
    if db.get(User, payload.user_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 사용 중인 아이디입니다: {payload.user_id}",
        )
    _require_department(db, payload.dept_id)

    user = User(
        user_id=payload.user_id,
        user_name=payload.user_name,
        password_hash=hash_password(payload.password),
        role_level=payload.role_level,
        job_title=(payload.job_title or "").strip(),
        dept_id=payload.dept_id,
    )
    mark_password_state(user, payload.password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(db, user, current, _task_counts(db))


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str, payload: AdminUserUpdate, current: CurrentUser, db: DbSession
) -> AdminUserOut:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    data = payload.model_dump(exclude_unset=True)

    if "role_level" in data and data["role_level"] != user.role_level:
        if user.user_id == current.user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="본인의 권한 등급은 변경할 수 없습니다.",
            )
        if user.role_level == "ADMIN" and _admin_count(db, exclude=user.user_id) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="마지막 관리자 계정의 권한은 변경할 수 없습니다.",
            )
        user.role_level = data["role_level"]

    if "dept_id" in data:
        _require_department(db, data["dept_id"])
        user.dept_id = data["dept_id"]

    if "job_title" in data:
        user.job_title = (data["job_title"] or "").strip()

    if data.get("user_name"):
        user.user_name = data["user_name"]

    if data.get("password"):
        user.password_hash = hash_password(data["password"])
        mark_password_state(user, data["password"])

    db.commit()
    db.refresh(user)
    return _user_out(db, user, current, _task_counts(db))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: str,
    current: CurrentUser,
    db: DbSession,
    reassign_to: str | None = Query(
        default=None, description="담당 업무를 넘겨받을 사용자 ID (미지정 시 업무가 있으면 삭제 불가)"
    ),
) -> None:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.user_id == current.user_id:
        raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다.")
    if user.role_level == "ADMIN" and _admin_count(db, exclude=user.user_id) == 0:
        raise HTTPException(status_code=400, detail="마지막 관리자 계정은 삭제할 수 없습니다.")

    tasks = list(db.scalars(select(Task).where(Task.assigned_to == user.user_id)).unique().all())
    if tasks:
        if not reassign_to:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"담당 업무 {len(tasks)}건이 있습니다. 인수인계할 담당자를 지정하세요.",
            )
        successor = db.get(User, reassign_to)
        if successor is None or successor.user_id == user.user_id:
            raise HTTPException(status_code=400, detail="인수인계 대상 사용자가 올바르지 않습니다.")
        for task in tasks:
            task.assigned_to = successor.user_id

    db.delete(user)
    db.commit()


# --------------------------------------------------------------------------- #
# 조직(부서) 관리
# --------------------------------------------------------------------------- #
def _depth(dept: Department, by_id: dict[int, Department]) -> int:
    depth, cursor, guard = 0, dept, 0
    while cursor.parent_dept_id is not None and guard < 20:
        parent = by_id.get(cursor.parent_dept_id)
        if parent is None:
            break
        depth += 1
        cursor = parent
        guard += 1
    return depth


def _flatten_tree(items: list[AdminDepartmentOut]) -> list[AdminDepartmentOut]:
    """부모 바로 아래에 자식을 붙이는 전위순회(DFS) 순서."""
    children: dict[int | None, list[AdminDepartmentOut]] = {}
    for item in items:
        children.setdefault(item.parent_dept_id, []).append(item)
    for siblings in children.values():
        siblings.sort(key=lambda item: item.dept_id)

    ordered: list[AdminDepartmentOut] = []
    seen: set[int] = set()

    def walk(parent_id: int | None) -> None:
        for child in children.get(parent_id, []):
            if child.dept_id in seen:
                continue
            seen.add(child.dept_id)
            ordered.append(child)
            walk(child.dept_id)

    walk(None)
    # 상위가 없는 고아 노드도 목록에서 빠지지 않게 뒤에 붙인다.
    ordered.extend(item for item in items if item.dept_id not in seen)
    return ordered


@router.get("/departments", response_model=list[AdminDepartmentOut])
def list_departments(db: DbSession) -> list[AdminDepartmentOut]:
    departments = list(db.scalars(select(Department).order_by(Department.dept_id)).all())
    by_id = {d.dept_id: d for d in departments}
    user_counts = _dept_user_counts(db)
    task_counts = _dept_task_counts(db)

    result = [
        AdminDepartmentOut(
            dept_id=d.dept_id,
            dept_name=d.dept_name,
            parent_dept_id=d.parent_dept_id,
            parent_dept_name=(
                by_id[d.parent_dept_id].dept_name if d.parent_dept_id in by_id else None
            ),
            user_count=user_counts.get(d.dept_id, 0),
            task_count=task_counts.get(d.dept_id, 0),
            child_count=sum(1 for x in departments if x.parent_dept_id == d.dept_id),
            depth=_depth(d, by_id),
        )
        for d in departments
    ]
    # 부모 바로 아래에 자식이 오도록 트리 순서로 정렬한다.
    return _flatten_tree(result)


@router.post(
    "/departments", response_model=AdminDepartmentOut, status_code=status.HTTP_201_CREATED
)
def create_department(payload: AdminDepartmentCreate, db: DbSession) -> AdminDepartmentOut:
    name = payload.dept_name.strip()
    if db.scalar(select(Department).where(Department.dept_name == name)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"이미 존재하는 부서명입니다: {name}"
        )
    if payload.parent_dept_id is not None and db.get(Department, payload.parent_dept_id) is None:
        raise HTTPException(status_code=404, detail="상위 부서를 찾을 수 없습니다.")

    dept = Department(dept_name=name, parent_dept_id=payload.parent_dept_id)
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return _single_department(db, dept.dept_id)


@router.patch("/departments/{dept_id}", response_model=AdminDepartmentOut)
def update_department(
    dept_id: int, payload: AdminDepartmentUpdate, db: DbSession
) -> AdminDepartmentOut:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")

    data = payload.model_dump(exclude_unset=True)

    if data.get("dept_name"):
        name = data["dept_name"].strip()
        duplicate = db.scalar(
            select(Department).where(
                Department.dept_name == name, Department.dept_id != dept_id
            )
        )
        if duplicate:
            raise HTTPException(status_code=409, detail=f"이미 존재하는 부서명입니다: {name}")
        dept.dept_name = name

    if "parent_dept_id" in data:
        parent_id = data["parent_dept_id"]
        if parent_id is not None:
            if parent_id == dept_id:
                raise HTTPException(status_code=400, detail="자기 자신을 상위 부서로 지정할 수 없습니다.")
            if db.get(Department, parent_id) is None:
                raise HTTPException(status_code=404, detail="상위 부서를 찾을 수 없습니다.")
            if parent_id in get_descendant_dept_ids(db, dept_id):
                raise HTTPException(
                    status_code=400, detail="하위 부서를 상위 부서로 지정할 수 없습니다."
                )
        dept.parent_dept_id = parent_id

    db.commit()
    return _single_department(db, dept_id)


@router.delete("/departments/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(dept_id: int, db: DbSession) -> None:
    dept = db.get(Department, dept_id)
    if dept is None:
        raise HTTPException(status_code=404, detail="부서를 찾을 수 없습니다.")

    blockers = []
    if db.scalar(select(func.count()).select_from(Department).where(Department.parent_dept_id == dept_id)):
        blockers.append("하위 부서")
    if db.scalar(select(func.count()).select_from(User).where(User.dept_id == dept_id)):
        blockers.append("소속 구성원")
    if db.scalar(select(func.count()).select_from(Task).where(Task.dept_id == dept_id)):
        blockers.append("등록된 업무")

    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"삭제할 수 없습니다. 먼저 정리해야 할 항목: {' · '.join(blockers)}",
        )

    db.delete(dept)
    db.commit()


def _single_department(db: Session, dept_id: int) -> AdminDepartmentOut:
    return next(item for item in list_departments(db) if item.dept_id == dept_id)


# --------------------------------------------------------------------------- #
# API 연동 (OpenAI · Anthropic · Google)
# --------------------------------------------------------------------------- #
def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return f"{key[:2]}{'•' * 6}"
    return f"{key[:6]}{'•' * 8}{key[-4:]}"


def _ensure_rows(db: Session) -> dict[str, ApiSetting]:
    rows = {row.provider: row for row in db.scalars(select(ApiSetting)).all()}
    dirty = False
    for provider in AI_PROVIDERS:
        if provider not in rows:
            row = ApiSetting(
                provider=provider,
                api_key="",
                text_model=AI_PROVIDERS[provider]["default_model"],
                is_active=False,
            )
            db.add(row)
            rows[provider] = row
            dirty = True
            continue
        # 모델이 단종되어 선택지에서 빠지면 호출이 404 로 실패하므로 기본 모델로 되돌린다.
        row = rows[provider]
        if row.text_model not in AI_PROVIDERS[provider]["models"]:
            row.text_model = AI_PROVIDERS[provider]["default_model"]
            dirty = True
    if dirty:
        db.commit()
    return rows


def _integration_out(row: ApiSetting) -> IntegrationOut:
    meta = AI_PROVIDERS[row.provider]
    return IntegrationOut(
        provider=row.provider,
        label=meta["label"],
        description=meta["description"],
        models=list(meta["models"]),
        default_model=meta["default_model"],
        supports_stt=bool(meta["supports_stt"]),
        key_hint=meta["key_hint"],
        console_url=meta["console_url"],
        text_model=row.text_model or meta["default_model"],
        has_key=bool(reveal(row.api_key)),
        masked_key=_mask(reveal(row.api_key)),
        is_active=bool(row.is_active),
        last_test_ok=row.last_test_ok,
        last_test_message=row.last_test_message or "",
        last_tested_at=row.last_tested_at,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


def _integration_response(db: Session) -> IntegrationListResponse:
    rows = _ensure_rows(db)
    ordered = [rows[p] for p in AI_PROVIDERS]
    status_info = ai_engine.ai_status(db)
    return IntegrationListResponse(
        providers=[_integration_out(row) for row in ordered],
        active_provider=status_info["provider"],
        active_model=status_info["text_model"],
        llm_ready=status_info["llm_ready"],
        stt_ready=status_info["stt_ready"],
        mock_mode=status_info["mock_mode"],
    )


@router.get("/integrations", response_model=IntegrationListResponse)
def list_integrations(db: DbSession) -> IntegrationListResponse:
    return _integration_response(db)


@router.patch("/integrations/{provider}", response_model=IntegrationListResponse)
def update_integration(
    provider: str, payload: IntegrationUpdate, current: CurrentUser, db: DbSession
) -> IntegrationListResponse:
    if provider not in AI_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"지원하지 않는 프로바이더입니다: {provider}")

    rows = _ensure_rows(db)
    row = rows[provider]
    data = payload.model_dump(exclude_unset=True)

    if "api_key" in data:
        key = (data["api_key"] or "").strip()
        row.api_key = seal(key) if key else ""
        if not key:
            row.last_test_ok = None
            row.last_test_message = ""
            row.last_tested_at = None
            # 키를 지운 프로바이더는 활성 상태를 유지할 수 없으므로 다른 곳으로 넘긴다.
            if row.is_active:
                row.is_active = False
                fallback = next(
                    (r for r in rows.values() if r.provider != provider and reveal(r.api_key)), None
                )
                if fallback is not None:
                    fallback.is_active = True

    if data.get("text_model"):
        model = data["text_model"]
        if model not in AI_PROVIDERS[provider]["models"]:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 모델입니다: {model}")
        row.text_model = model

    if data.get("activate"):
        if not reveal(row.api_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API 키를 먼저 저장해야 활성화할 수 있습니다.",
            )
        for other in rows.values():
            other.is_active = other.provider == provider

    row.updated_by = current.user_id
    db.commit()
    return _integration_response(db)


@router.post("/integrations/{provider}/test", response_model=ConnectionTestResult)
def test_integration(
    provider: str,
    current: CurrentUser,
    db: DbSession,
    model: str | None = None,
) -> ConnectionTestResult:
    if provider not in AI_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"지원하지 않는 프로바이더입니다: {provider}")

    rows = _ensure_rows(db)
    row = rows[provider]
    if not reveal(row.api_key):
        raise HTTPException(status_code=400, detail="저장된 API 키가 없습니다.")

    meta = AI_PROVIDERS[provider]
    # 저장 전에도 화면에서 고른 모델 그대로 확인할 수 있어야 한다.
    if model and model not in meta["models"]:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 모델입니다: {model}")
    cfg = ai_engine.ProviderConfig(
        provider=provider,
        label=meta["label"],
        api_key=reveal(row.api_key),
        model=model or row.text_model or meta["default_model"],
        supports_stt=bool(meta["supports_stt"]),
    )
    result = ai_engine.test_connection(cfg, db=db, user_id=current.user_id)

    row.last_test_ok = bool(result["ok"])
    row.last_test_message = result["message"]
    row.last_tested_at = datetime.now()
    db.commit()

    return ConnectionTestResult(provider=provider, **result)


# --------------------------------------------------------------------------- #
# 사용량 모니터링
# --------------------------------------------------------------------------- #
def _totals(entries: list[ApiUsage]) -> UsageTotals:
    if not entries:
        return UsageTotals()
    latencies = [e.latency_ms for e in entries if e.latency_ms]
    return UsageTotals(
        calls=len(entries),
        success=sum(1 for e in entries if e.status == "success"),
        error=sum(1 for e in entries if e.status == "error"),
        mock=sum(1 for e in entries if e.status == "mock"),
        prompt_tokens=sum(e.prompt_tokens for e in entries),
        completion_tokens=sum(e.completion_tokens for e in entries),
        total_tokens=sum(e.total_tokens for e in entries),
        cost_usd=round(sum(e.cost_usd for e in entries), 4),
        avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
    )


@router.get("/usage", response_model=UsageResponse)
def usage_summary(
    db: DbSession,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=1, le=100),
) -> UsageResponse:
    """실시간 사용량 모니터용 집계. 프런트에서 주기적으로 폴링한다."""
    now = datetime.now()
    since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    entries = list(
        db.scalars(
            select(ApiUsage).where(ApiUsage.created_at >= since).order_by(ApiUsage.created_at)
        ).all()
    )
    rows = _ensure_rows(db)

    by_provider: list[UsageByProvider] = []
    for provider, meta in AI_PROVIDERS.items():
        items = [e for e in entries if e.provider == provider]
        latencies = [e.latency_ms for e in items if e.latency_ms]
        by_provider.append(
            UsageByProvider(
                provider=provider,
                label=meta["label"],
                calls=len(items),
                total_tokens=sum(e.total_tokens for e in items),
                cost_usd=round(sum(e.cost_usd for e in items), 4),
                avg_latency_ms=int(sum(latencies) / len(latencies)) if latencies else 0,
                error_calls=sum(1 for e in items if e.status == "error"),
                is_active=bool(rows[provider].is_active),
            )
        )

    mock_items = [e for e in entries if e.provider == "mock"]
    if mock_items:
        by_provider.append(
            UsageByProvider(
                provider="mock",
                label="데모 모드",
                calls=len(mock_items),
                total_tokens=0,
                cost_usd=0.0,
                avg_latency_ms=0,
                error_calls=0,
                is_active=False,
            )
        )

    features: dict[str, list[ApiUsage]] = {}
    for entry in entries:
        features.setdefault(entry.feature or "기타", []).append(entry)
    by_feature = sorted(
        (
            UsageByFeature(
                feature=name,
                calls=len(items),
                total_tokens=sum(e.total_tokens for e in items),
                cost_usd=round(sum(e.cost_usd for e in items), 4),
            )
            for name, items in features.items()
        ),
        key=lambda f: f.calls,
        reverse=True,
    )

    daily: list[UsageDailyPoint] = []
    for offset in range(days):
        day = (since + timedelta(days=offset)).date()
        items = [e for e in entries if e.created_at.date() == day]
        daily.append(
            UsageDailyPoint(
                date=day.isoformat(),
                calls=len(items),
                total_tokens=sum(e.total_tokens for e in items),
                cost_usd=round(sum(e.cost_usd for e in items), 4),
            )
        )

    recent = list(
        db.scalars(select(ApiUsage).order_by(ApiUsage.usage_id.desc()).limit(limit)).all()
    )

    return UsageResponse(
        generated_at=now,
        range_days=days,
        totals=_totals(entries),
        today=_totals([e for e in entries if e.created_at >= today_start]),
        by_provider=by_provider,
        by_feature=by_feature,
        daily=daily,
        recent=[UsageLogOut.model_validate(e, from_attributes=True) for e in recent],
    )


@router.delete("/usage", status_code=status.HTTP_204_NO_CONTENT)
def clear_usage(db: DbSession) -> None:
    """사용량 로그 초기화."""
    db.query(ApiUsage).delete()
    db.commit()
