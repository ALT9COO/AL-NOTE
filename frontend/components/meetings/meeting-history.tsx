"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  Building2,
  CalendarCheck2,
  CalendarDays,
  ChevronDown,
  FileText,
  KanbanSquare,
  Loader2,
  User2,
  UserPlus,
  Volume2,
} from "lucide-react";
import { toast } from "sonner";

import { SubjectPicker, toSubjectPayload } from "@/components/common/subject-picker";
import { ArchivedAudio } from "@/components/meetings/archived-audio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { apiErrorMessage, authApi, meetingApi } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import type { Collaborator, Department, Meeting, User } from "@/types";

function SubjectChips({ items, empty }: { items: Collaborator[]; empty: string }) {
  if (!items.length) {
    return <span className="text-xs text-muted-foreground">{empty}</span>;
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <Badge key={`${item.kind}-${item.user_id ?? item.dept_id}`} variant="secondary">
          {item.kind === "dept" ? <Building2 className="h-3 w-3" /> : <UserPlus className="h-3 w-3" />}
          {item.kind === "dept" ? item.dept_name : item.user_name}
        </Badge>
      ))}
    </div>
  );
}

function MeetingAccess({
  meeting,
  users,
  departments,
  onUpdated,
}: {
  meeting: Meeting;
  users: User[];
  departments: Department[];
  onUpdated?: () => void;
}) {
  const [participants, setParticipants] = useState<Collaborator[]>(meeting.participants ?? []);
  const [viewers, setViewers] = useState<Collaborator[]>(meeting.viewers ?? []);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setParticipants(meeting.participants ?? []);
    setViewers(meeting.viewers ?? []);
  }, [meeting]);

  async function handleSave() {
    setSaving(true);
    try {
      await meetingApi.updateAccess(meeting.meeting_id, {
        participants: toSubjectPayload(participants),
        viewers: toSubjectPayload(viewers),
      });
      toast.success("공유 설정을 저장했습니다.");
      onUpdated?.();
    } catch (error) {
      toast.error(apiErrorMessage(error, "공유 설정을 저장하지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  if (!meeting.can_manage) {
    return (
      <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
        <p className="text-xs font-medium">참여자</p>
        <SubjectChips items={meeting.participants ?? []} empty="작성자 · 관리자만" />
        <p className="text-xs font-medium">열람자</p>
        <SubjectChips items={meeting.viewers ?? []} empty="추가 열람자 없음" />
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <SubjectPicker
        label="참여자"
        hint="회의에 참석한 사람 또는 조직"
        emptyLabel="작성자만 (참여자 없음)"
        items={participants}
        onChange={setParticipants}
        users={users}
        departments={departments}
        excludeUserIds={meeting.created_by ? [meeting.created_by] : []}
      />
      <SubjectPicker
        label="열람자"
        hint="참석하지 않아도 회의록을 볼 대상"
        emptyLabel="추가 열람자 없음"
        items={viewers}
        onChange={setViewers}
        users={users}
        departments={departments}
        excludeUserIds={meeting.created_by ? [meeting.created_by] : []}
      />
      <div className="flex justify-end">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          공유 설정 저장
        </Button>
      </div>
    </div>
  );
}

export function MeetingHistory({
  meetings,
  users,
  onUpdated,
}: {
  meetings: Meeting[];
  users: User[];
  onUpdated?: () => void;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);

  useEffect(() => {
    authApi.departments().then(setDepartments).catch(() => undefined);
  }, []);

  if (meetings.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-sm text-muted-foreground">
          저장된 회의록이 없습니다. 회의를 분석하고 안건을 제출하면 여기에 기록됩니다.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      {meetings.map((meeting) => {
        const open = openId === meeting.meeting_id;
        const shareCount = (meeting.participants?.length ?? 0) + (meeting.viewers?.length ?? 0);
        return (
          <Card key={meeting.meeting_id}>
            <button
              type="button"
              onClick={() => setOpenId(open ? null : meeting.meeting_id)}
              className="flex w-full items-center gap-3 p-4 text-left"
            >
              <span className="rounded-lg bg-primary/10 p-2 text-primary">
                <FileText className="h-4 w-4" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold">{meeting.title}</p>
                <p className="mt-0.5 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <CalendarDays className="h-3 w-3" />
                    {formatDateTime(meeting.created_at)}
                  </span>
                  <span className="flex items-center gap-1">
                    <User2 className="h-3 w-3" />
                    {meeting.author_name ?? "-"} · {meeting.dept_name ?? "-"}
                  </span>
                  <span>
                    {shareCount ? `공유 ${shareCount}명/조직` : "작성자·관리자만"}
                  </span>
                  {meeting.event_start ? (
                    <span className="flex items-center gap-1 text-primary">
                      <CalendarCheck2 className="h-3 w-3" />
                      캘린더 일정 {formatDateTime(meeting.event_start)}
                      {meeting.event_location ? ` · ${meeting.event_location}` : ""}
                    </span>
                  ) : null}
                  {meeting.has_audio ? (
                    <span className="flex items-center gap-1">
                      <Volume2 className="h-3 w-3" />
                      음성
                    </span>
                  ) : null}
                  {meeting.task_ids?.length ? (
                    <span className="flex items-center gap-1">
                      <KanbanSquare className="h-3 w-3" />
                      관련 업무 {meeting.task_ids.length}건
                    </span>
                  ) : null}
                </p>
              </div>
              <ChevronDown
                className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
              />
            </button>

            {open ? (
              <CardContent className="space-y-4 border-t pt-4">
                {meeting.has_audio ? (
                  <ArchivedAudio
                    kind="meeting"
                    id={meeting.meeting_id}
                    name={meeting.audio_name}
                    size={meeting.audio_size}
                  />
                ) : null}
                <div className="markdown-body">
                  <ReactMarkdown>{meeting.ai_summary || "_요약 없음_"}</ReactMarkdown>
                </div>
                <MeetingAccess
                  meeting={meeting}
                  users={users}
                  departments={departments}
                  onUpdated={onUpdated}
                />
                {meeting.task_ids?.length ? (
                  <div className="flex flex-wrap gap-2">
                    {meeting.task_ids.map((taskId) => (
                      <Link
                        key={taskId}
                        href={`/dashboard?task=${encodeURIComponent(taskId)}`}
                        className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs font-medium text-primary hover:bg-primary/5"
                      >
                        <KanbanSquare className="h-3 w-3" />
                        {taskId} 칸반에서 보기
                      </Link>
                    ))}
                  </div>
                ) : null}
                {meeting.raw_transcript ? (
                  <details className="rounded-lg border bg-muted/30 p-3">
                    <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
                      원본 전사 보기
                    </summary>
                    <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                      {meeting.raw_transcript}
                    </p>
                  </details>
                ) : null}
              </CardContent>
            ) : null}
          </Card>
        );
      })}
    </div>
  );
}
