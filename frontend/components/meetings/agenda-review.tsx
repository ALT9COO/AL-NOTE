"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Loader2,
  Send,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { toast } from "sonner";

import { SubjectPicker, toSubjectPayload } from "@/components/common/subject-picker";
import { ArchivedAudio } from "@/components/meetings/archived-audio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, authApi, meetingApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { cn, STATUS_META, STATUSES } from "@/lib/utils";
import type {
  AgendaSubmitResult,
  CalendarEvent,
  Collaborator,
  Department,
  MeetingParseResult,
  TaskUpdateProposal,
  User,
} from "@/types";

interface AgendaReviewProps {
  parsed: MeetingParseResult;
  transcript: string;
  users: User[];
  event?: CalendarEvent | null;
  draftId?: number | null;
  hasAudio?: boolean;
  audioName?: string | null;
  audioSize?: number | null;
  onSubmitted: (result: AgendaSubmitResult) => void;
  onBack: () => void;
}

interface Row extends TaskUpdateProposal {
  include: boolean;
}

function usersToSubjects(ids: string[], people: User[], excludeId?: string): Collaborator[] {
  const seen = new Set<string>();
  const items: Collaborator[] = [];
  for (const id of ids) {
    if (!id || id === excludeId || seen.has(id)) continue;
    const picked = people.find((person) => person.user_id === id);
    if (!picked) continue;
    seen.add(id);
    items.push({
      kind: "user",
      user_id: picked.user_id,
      user_name: picked.user_name,
      dept_id: picked.dept_id,
      dept_name: picked.dept_name,
    });
  }
  return items;
}

export function AgendaReview({
  parsed,
  transcript,
  users,
  event,
  draftId,
  hasAudio,
  audioName,
  audioSize,
  onSubmitted,
  onBack,
}: AgendaReviewProps) {
  const { user } = useAuth();
  const [title, setTitle] = useState(parsed.meeting_title);
  const [rows, setRows] = useState<Row[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [participants, setParticipants] = useState<Collaborator[]>([]);
  const [viewers, setViewers] = useState<Collaborator[]>([]);

  useEffect(() => {
    authApi.departments().then(setDepartments).catch(() => undefined);
  }, []);

  useEffect(() => {
    // 캘린더에서 고른 일정이 있으면 그 제목을 우선 쓴다 (AI 추정 제목보다 정확하다).
    setTitle(event?.title || parsed.meeting_title);
    setRows(parsed.task_updates.map((item) => ({ ...item, include: true })));
    setParticipants(usersToSubjects(event?.matched_user_ids ?? [], users, user?.user_id));
    setViewers([]);
  }, [parsed, event, users, user?.user_id]);

  function patchRow(index: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  async function handleSubmit() {
    const selected = rows.filter((row) => row.include);
    if (!title.trim()) {
      toast.error("회의 제목을 입력하세요.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await meetingApi.submit({
        title: title.trim(),
        transcript,
        summary_bullets: parsed.summary_bullets,
        agenda_items: parsed.agenda_items,
        action_items: parsed.action_items,
        risks: parsed.risks,
        task_updates: selected.map((row) => ({
          task_id: row.task_id,
          task_name: row.task_name,
          assignee: row.assignee,
          status: row.status,
          progress: row.progress,
          issues: row.issues,
          due_date: row.due_date,
          is_new: row.is_new,
        })),
        event_key: event?.event_key ?? null,
        event_start: event?.start ?? null,
        event_location: event?.location ?? null,
        participants: toSubjectPayload(participants),
        viewers: toSubjectPayload(viewers),
        draft_id: draftId ?? undefined,
      });
      toast.success(
        `업무 ${result.updated.length}건 반영 · 신규 ${result.created.length}건 생성`,
      );
      onSubmitted(result);
    } catch (error) {
      toast.error(apiErrorMessage(error, "안건 제출에 실패했습니다."));
    } finally {
      setSubmitting(false);
    }
  }

  const selectedCount = rows.filter((row) => row.include).length;

  return (
    <div className="space-y-4">
      {parsed.mock ? (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            데모 모드 결과입니다. <code className="font-mono">backend/.env</code> 에
            OPENAI_API_KEY 를 설정하면 GPT-4o 가 실제 회의를 분석합니다.
          </span>
        </div>
      ) : null}

      {hasAudio && draftId ? (
        <ArchivedAudio kind="draft" id={draftId} name={audioName} size={audioSize} />
      ) : null}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-primary" />
              AI 회의 요약
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="meeting_title">회의 제목</Label>
              <Input
                id="meeting_title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                핵심 요약
              </p>
              <ul className="space-y-1.5">
                {parsed.summary_bullets.map((bullet, i) => (
                  <li key={i} className="flex gap-2 text-sm">
                    <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                    <span>{bullet}</span>
                  </li>
                ))}
                {parsed.summary_bullets.length === 0 ? (
                  <li className="text-sm text-muted-foreground">추출된 요약이 없습니다.</li>
                ) : null}
              </ul>
            </div>

            {parsed.agenda_items.length ? (
              <div>
                <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  안건
                </p>
                <div className="space-y-2">
                  {parsed.agenda_items.map((item, i) => (
                    <div key={i} className="rounded-lg border bg-muted/30 p-3">
                      <p className="text-sm font-medium">{item.topic}</p>
                      {item.discussion ? (
                        <p className="mt-1 text-xs text-muted-foreground">논의 · {item.discussion}</p>
                      ) : null}
                      {item.decision ? (
                        <p className="mt-0.5 text-xs text-primary">결정 · {item.decision}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <ClipboardList className="h-4 w-4 text-primary" />
                액션 아이템
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {parsed.action_items.length ? (
                parsed.action_items.map((item, i) => (
                  <div key={i} className="rounded-lg border bg-muted/30 p-2.5 text-xs">
                    <p className="font-medium text-foreground">{item.title}</p>
                    <p className="mt-0.5 text-muted-foreground">
                      담당 {item.assignee || "미지정"} · 기한 {item.due_date || "미정"}
                    </p>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground">추출된 액션 아이템이 없습니다.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-base">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                리스크
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {parsed.risks.length ? (
                parsed.risks.map((risk, i) => (
                  <p key={i} className="rounded-md bg-amber-50 p-2 text-xs text-amber-800">
                    {risk}
                  </p>
                ))
              ) : (
                <p className="text-xs text-muted-foreground">식별된 리스크가 없습니다.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="text-base">
            업무 반영 제안{" "}
            <span className="ml-1 text-xs font-normal text-muted-foreground">
              선택 {selectedCount} / 전체 {rows.length}
            </span>
          </CardTitle>
          <Badge variant="muted">변경된 기존 업무와 신규 후속만 표시합니다</Badge>
        </CardHeader>
        <CardContent className="space-y-3">
          {rows.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              값이 바뀐 기존 업무나, 새로 하기로 한 후속이 없습니다.
              액션 아이템은 위 카드에서 확인하고 필요하면 아래에서 업무로 추가해 주세요.
            </p>
          ) : null}

          {rows.map((row, index) => (
            <div
              key={`${row.task_id}-${index}`}
              className={cn(
                "rounded-xl border p-4 transition-colors",
                row.include ? "bg-card" : "bg-muted/40 opacity-60",
              )}
            >
              <div className="flex items-start gap-3">
                <Checkbox
                  checked={row.include}
                  onCheckedChange={(checked) => patchRow(index, { include: Boolean(checked) })}
                  className="mt-1"
                />
                <div className="flex-1 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={row.is_new ? "warning" : "default"}>
                      {row.is_new ? "신규 업무" : row.task_id}
                    </Badge>
                    {row.change_note ? (
                      <span className="text-xs text-muted-foreground">{row.change_note}</span>
                    ) : null}
                    <Input
                      value={row.task_name}
                      onChange={(e) => patchRow(index, { task_name: e.target.value })}
                      className="h-8 flex-1 min-w-[200px] font-medium"
                    />
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                    <div className="space-y-1">
                      <Label>담당자</Label>
                      <Select
                        value={row.assignee}
                        onValueChange={(value) => patchRow(index, { assignee: value })}
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue placeholder="담당자 선택" />
                        </SelectTrigger>
                        <SelectContent>
                          {users.map((user) => (
                            <SelectItem key={user.user_id} value={user.user_id}>
                              {user.user_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label>상태</Label>
                      <Select
                        value={row.status}
                        onValueChange={(value) =>
                          patchRow(index, { status: value as Row["status"] })
                        }
                      >
                        <SelectTrigger className="h-8">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {STATUSES.map((status) => (
                            <SelectItem key={status} value={status}>
                              {status}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1">
                      <Label>진행률 ({row.progress}%)</Label>
                      <div className="flex h-8 items-center gap-2">
                        <input
                          type="range"
                          min={0}
                          max={100}
                          step={5}
                          value={row.progress}
                          onChange={(e) => patchRow(index, { progress: Number(e.target.value) })}
                          className="w-full accent-primary"
                        />
                      </div>
                    </div>

                    <div className="space-y-1">
                      <Label>마감일</Label>
                      <Input
                        type="date"
                        value={row.due_date}
                        onChange={(e) => patchRow(index, { due_date: e.target.value })}
                        className="h-8"
                      />
                    </div>
                  </div>

                  <div className="space-y-1">
                    <Label>이슈</Label>
                    <Textarea
                      rows={2}
                      value={row.issues}
                      onChange={(e) => patchRow(index, { issues: e.target.value })}
                      placeholder="회의에서 언급된 이슈나 리스크"
                      className="text-sm"
                    />
                  </div>

                  <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                    <span className={cn("h-2 w-2 rounded-full", STATUS_META[row.status].dot)} />
                    제출 시 {row.is_new ? "새 업무로 생성" : `${row.task_id} 업무에 반영`}됩니다.
                  </div>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">참여자 · 공유</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-xs text-muted-foreground">
            기본은 회의를 기록한 사람과 관리자만 볼 수 있습니다. 참여자와 열람자를 지정하면 그
            대상에게도 회의록이 공개됩니다.
          </p>
          <SubjectPicker
            label="참여자"
            hint="회의에 참석한 사람 또는 조직입니다. Outlook 일정과 연결된 경우 매칭된 사내 계정이 미리 채워집니다."
            emptyLabel="작성자만 (참여자 없음)"
            items={participants}
            onChange={setParticipants}
            users={users}
            departments={departments}
            excludeUserIds={user?.user_id ? [user.user_id] : []}
          />
          <SubjectPicker
            label="열람자"
            hint="참석하지 않아도 회의록을 볼 사람 또는 조직입니다."
            emptyLabel="추가 열람자 없음"
            items={viewers}
            onChange={setViewers}
            users={users}
            departments={departments}
            excludeUserIds={user?.user_id ? [user.user_id] : []}
          />
        </CardContent>
      </Card>

      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={onBack}>
          다시 분석
        </Button>
        <Button onClick={handleSubmit} disabled={submitting}>
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          안건 제출 · 업무 현황 반영
        </Button>
      </div>
    </div>
  );
}
