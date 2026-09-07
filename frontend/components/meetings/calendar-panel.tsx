"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  CalendarCheck2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  FileText,
  KanbanSquare,
  Link2Off,
  Loader2,
  LogIn,
  MapPin,
  RefreshCw,
  Settings2,
  Sparkles,
  Users,
  Video,
} from "lucide-react";
import { toast } from "sonner";

import { ArchivedAudio } from "@/components/meetings/archived-audio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth-context";
import { apiErrorMessage, calendarApi, meetingApi } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import type { CalendarConnection, CalendarEvent, Meeting } from "@/types";

interface CalendarPanelProps {
  selected: CalendarEvent | null;
  onSelect: (event: CalendarEvent | null) => void;
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function startOfDay(value: Date) {
  const next = new Date(value);
  next.setHours(0, 0, 0, 0);
  return next;
}

function toKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

function eventDayKey(event: CalendarEvent) {
  return event.start.slice(0, 10);
}

function daysFromToday(date: Date) {
  const today = startOfDay(new Date());
  return Math.round((startOfDay(date).getTime() - today.getTime()) / 86_400_000);
}

function rangeForMonth(cursor: Date) {
  const monthStart = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const monthEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
  return {
    days_back: Math.min(180, Math.max(0, -daysFromToday(monthStart))),
    days_ahead: Math.min(90, Math.max(1, daysFromToday(monthEnd) + 1)),
  };
}

function dayLabel(iso: string) {
  const date = iso.length <= 10 ? new Date(`${iso}T12:00:00`) : new Date(iso);
  const diff = daysFromToday(date);
  const base = `${date.getMonth() + 1}월 ${date.getDate()}일 (${WEEKDAYS[date.getDay()]})`;
  if (diff === 0) return `오늘 · ${base}`;
  if (diff === 1) return `내일 · ${base}`;
  if (diff === -1) return `어제 · ${base}`;
  return base;
}

function timeLabel(event: CalendarEvent) {
  if (event.all_day) return "종일";
  const start = new Date(event.start);
  const text = `${String(start.getHours()).padStart(2, "0")}:${String(start.getMinutes()).padStart(2, "0")}`;
  if (!event.end) return text;
  const end = new Date(event.end);
  return `${text}–${String(end.getHours()).padStart(2, "0")}:${String(end.getMinutes()).padStart(2, "0")}`;
}

export function CalendarPanel({ selected, onSelect }: CalendarPanelProps) {
  const { user } = useAuth();
  const today = startOfDay(new Date());
  const [connection, setConnection] = useState<CalendarConnection | null>(null);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [sample, setSample] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [cursor, setCursor] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));
  const [selectedDay, setSelectedDay] = useState(toKey(today));
  const [preview, setPreview] = useState<Meeting | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  const load = useCallback(
    async (options: { sample?: boolean; month?: Date } = {}) => {
      const useSample = options.sample ?? sample;
      const month = options.month ?? cursor;
      const range = rangeForMonth(month);
      try {
        const data = await calendarApi.events({
          days_back: range.days_back,
          days_ahead: range.days_ahead,
          sample: useSample,
        });
        setConnection(data.connection);
        setEvents(data.events);
      } catch (error) {
        try {
          setConnection(await calendarApi.connection());
        } catch {
          /* 무시 */
        }
        setEvents([]);
        toast.error(apiErrorMessage(error, "캘린더를 불러오지 못했습니다."));
      } finally {
        setLoading(false);
      }
    },
    [sample, cursor],
  );

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const result = query.get("calendar");
    if (!result) return;

    const message = query.get("msg") ?? "";
    if (result === "connected") {
      toast.success(`Microsoft 계정을 연결했습니다${message ? ` (${message})` : ""}`);
    } else {
      toast.error(message || "Microsoft 계정 연결에 실패했습니다.");
    }
    window.history.replaceState({}, "", "/meetings");
  }, []);

  async function handleConnect() {
    setBusy(true);
    try {
      const { url } = await calendarApi.loginUrl();
      window.location.href = url;
    } catch (error) {
      toast.error(apiErrorMessage(error, "로그인 주소를 만들지 못했습니다."));
      setBusy(false);
    }
  }

  async function handleDisconnect() {
    setBusy(true);
    try {
      await calendarApi.disconnect();
      onSelect(null);
      setSample(false);
      await load({ sample: false });
      toast.success("Microsoft 계정 연결을 해제했습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "연결 해제에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  }

  async function handleSync() {
    setBusy(true);
    try {
      const status = await calendarApi.sync();
      setConnection(status);
      await load({ sample: false });
      if (status.last_sync_ok) toast.success(status.last_sync_message);
      else toast.error(status.last_sync_message);
    } catch (error) {
      toast.error(apiErrorMessage(error, "동기화에 실패했습니다."));
    } finally {
      setBusy(false);
    }
  }

  async function openMinutes(meetingId: number) {
    setPreviewOpen(true);
    setPreview(null);
    setPreviewLoading(true);
    try {
      setPreview(await meetingApi.get(meetingId));
    } catch (error) {
      setPreviewOpen(false);
      toast.error(apiErrorMessage(error, "회의록을 불러오지 못했습니다."));
    } finally {
      setPreviewLoading(false);
    }
  }

  function shiftMonth(delta: number) {
    const next = new Date(cursor.getFullYear(), cursor.getMonth() + delta, 1);
    setCursor(next);
    setLoading(true);
    void load({ month: next });
  }

  const connected = connection?.connected ?? false;
  const appReady = connection?.app_configured ?? false;
  const needsReauth = connection?.needs_reauth ?? false;
  const missingScopes = connection?.missing_scopes ?? [];
  const needsConsent = connected && !needsReauth && missingScopes.length > 0;

  const { cells, byDay, monthEvents } = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const gridStart = new Date(first);
    gridStart.setDate(1 - first.getDay());
    const cells = Array.from({ length: 42 }, (_, i) => {
      const date = new Date(gridStart);
      date.setDate(gridStart.getDate() + i);
      return date;
    });
    const byDay = new Map<string, CalendarEvent[]>();
    events.forEach((event) => {
      const key = eventDayKey(event);
      byDay.set(key, [...(byDay.get(key) ?? []), event]);
    });
    const monthEvents = events.filter((event) => {
      const date = new Date(event.start);
      return date.getMonth() === cursor.getMonth() && date.getFullYear() === cursor.getFullYear();
    });
    return { cells, byDay, monthEvents };
  }, [cursor, events]);

  const selectedEvents = byDay.get(selectedDay) ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
          <span className="flex items-center gap-2">
            <CalendarCheck2 className="h-4 w-4 text-primary" />내 캘린더 일정
            {sample ? <Badge variant="warning">샘플</Badge> : null}
            {connected && !sample ? (
              <Badge variant={needsReauth ? "warning" : "success"}>
                {connection?.account_email || connection?.account_name}
              </Badge>
            ) : null}
          </span>
          <span className="flex gap-1.5">
            {connected && !needsReauth ? (
              <>
                <Button variant="outline" size="sm" disabled={busy} onClick={handleSync}>
                  <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
                  동기화
                </Button>
                {needsConsent ? (
                  <Button size="sm" disabled={busy} onClick={handleConnect}>
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <LogIn className="h-3.5 w-3.5" />
                    )}
                    권한 추가
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  disabled={busy}
                  onClick={handleDisconnect}
                >
                  <Link2Off className="h-3.5 w-3.5" />
                  연결 해제
                </Button>
              </>
            ) : (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const next = !sample;
                    setSample(next);
                    void load({ sample: next });
                  }}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  {sample ? "샘플 끄기" : "샘플로 미리보기"}
                </Button>
                <Button size="sm" disabled={busy || !appReady} onClick={handleConnect}>
                  {busy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <LogIn className="h-3.5 w-3.5" />
                  )}
                  {needsReauth ? "Microsoft 계정 다시 연결" : "Microsoft 계정 연결"}
                </Button>
              </>
            )}
          </span>
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          {connected && !needsReauth
            ? `날짜를 고르면 그날 일정이 아래에 나옵니다. 최근 동기화 ${formatDateTime(
                connection?.last_synced_at,
              )}`
            : "Microsoft 365 계정을 연결하면 Outlook 캘린더에 잡힌 회의를 골라 바로 회의록을 만들 수 있습니다."}
        </p>
      </CardHeader>

      <CardContent className="space-y-3">
        {!appReady ? (
          <div className="flex flex-wrap items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-900">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <div className="min-w-0 flex-1 space-y-1">
              <p className="font-medium">Microsoft 365 연동이 아직 설정되지 않았습니다.</p>
              <p>
                조직에 Azure(Entra ID) 앱 등록이 한 번 필요합니다. 등록 후 관리자가 클라이언트 ID와
                시크릿을 입력하면 구성원 각자가 자기 계정을 연결할 수 있습니다.
              </p>
            </div>
            {user?.role_level === "ADMIN" ? (
              <Button asChild size="sm" variant="outline">
                <Link href="/settings?tab=calendar">
                  <Settings2 className="h-3.5 w-3.5" />
                  설정하기
                </Link>
              </Button>
            ) : null}
          </div>
        ) : null}

        {needsConsent ? (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
            일정 만들기·메일 발송을 쓰려면 권한이 더 필요합니다 ({missingScopes.join(", ")}).
            「권한 추가」를 눌러 Microsoft 계정에 다시 동의하세요.
          </p>
        ) : needsReauth ? (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Microsoft 인증이 만료되었습니다. 위의 다시 연결 버튼을 눌러 로그인하세요.
          </p>
        ) : connection?.last_sync_ok === false ? (
          <p className="rounded-md bg-rose-50 px-3 py-2 text-xs text-rose-700">
            {connection.last_sync_message}
          </p>
        ) : null}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-1.5">
            <Button variant="outline" size="sm" onClick={() => shiftMonth(-1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="min-w-[110px] text-center text-sm font-semibold">
              {cursor.getFullYear()}년 {cursor.getMonth() + 1}월
            </span>
            <Button variant="outline" size="sm" onClick={() => shiftMonth(1)}>
              <ChevronRight className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                const now = startOfDay(new Date());
                const month = new Date(now.getFullYear(), now.getMonth(), 1);
                setCursor(month);
                setSelectedDay(toKey(now));
                setLoading(true);
                void load({ month });
              }}
            >
              오늘
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">이 달 일정 {monthEvents.length}건</p>
        </div>

        {loading ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <>
            <div className="overflow-hidden rounded-xl border">
              <div className="grid grid-cols-7 bg-muted/50 text-center text-[11px] font-medium text-muted-foreground">
                {WEEKDAYS.map((day) => (
                  <div key={day} className="px-1 py-1.5">
                    {day}
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-7">
                {cells.map((date) => {
                  const key = toKey(date);
                  const inMonth = date.getMonth() === cursor.getMonth();
                  const isToday = key === toKey(today);
                  const isSelected = key === selectedDay;
                  const dayEvents = byDay.get(key) ?? [];
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setSelectedDay(key)}
                      className={cn(
                        "min-h-[72px] border-t px-1 py-1 text-left transition hover:bg-muted/40",
                        !inMonth && "bg-muted/20 text-muted-foreground",
                        isSelected && "bg-primary/10 ring-1 ring-inset ring-primary",
                      )}
                    >
                      <span
                        className={cn(
                          "inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-medium",
                          isToday && "bg-primary text-primary-foreground",
                        )}
                      >
                        {date.getDate()}
                      </span>
                      <div className="mt-0.5 space-y-0.5">
                        {dayEvents.slice(0, 3).map((event) => (
                          <p
                            key={event.event_key}
                            className={cn(
                              "truncate rounded px-0.5 text-[10px] leading-4",
                              event.meeting_id
                                ? "bg-emerald-100 text-emerald-800"
                                : "bg-blue-50 text-blue-800",
                            )}
                          >
                            {event.all_day ? "종일" : timeLabel(event).slice(0, 5)} {event.title}
                          </p>
                        ))}
                        {dayEvents.length > 3 ? (
                          <p className="text-[10px] text-muted-foreground">+{dayEvents.length - 3}</p>
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="space-y-1.5">
              <p className="text-[11px] font-semibold text-muted-foreground">{dayLabel(selectedDay)}</p>
              {selectedEvents.length ? (
                selectedEvents.map((event) => (
                  <EventRow
                    key={event.event_key}
                    event={event}
                    active={selected?.event_key === event.event_key}
                    onSelect={onSelect}
                    onView={openMinutes}
                  />
                ))
              ) : (
                <p className="py-4 text-center text-xs text-muted-foreground">
                  {connected ? "이 날에는 일정이 없습니다. 다른 날짜를 선택해 보세요." : "연결된 캘린더가 없습니다."}
                </p>
              )}
            </div>
          </>
        )}
      </CardContent>

      <MeetingPreviewDialog
        open={previewOpen}
        loading={previewLoading}
        meeting={preview}
        onOpenChange={setPreviewOpen}
      />
    </Card>
  );
}

function EventRow({
  event,
  active,
  onSelect,
  onView,
}: {
  event: CalendarEvent;
  active: boolean;
  onSelect: (event: CalendarEvent | null) => void;
  onView: (meetingId: number) => void;
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 transition",
        active ? "border-primary bg-primary/5" : "hover:bg-muted/50",
        event.is_cancelled && "opacity-60",
      )}
    >
      <span className="w-[86px] shrink-0 font-mono text-[11px] text-muted-foreground">
        {timeLabel(event)}
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">
          {event.is_cancelled ? <span className="line-through">{event.title}</span> : event.title}
        </p>
        <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
          {event.online_url ? (
            <span className="flex items-center gap-0.5 text-blue-600">
              <Video className="h-3 w-3" />
              Teams
            </span>
          ) : null}
          {event.location ? (
            <span className="flex items-center gap-0.5">
              <MapPin className="h-3 w-3" />
              <span className="max-w-[180px] truncate">{event.location}</span>
            </span>
          ) : null}
          {event.attendees.length ? (
            <span className="flex items-center gap-0.5">
              <Users className="h-3 w-3" />
              {event.attendees.length}명
              {event.matched_user_ids.length
                ? ` (사내 ${event.matched_user_ids.length}명 매칭)`
                : ""}
            </span>
          ) : null}
        </div>
      </div>

      {event.meeting_id ? (
        <span className="flex items-center gap-1.5">
          <Badge variant="success">
            <CheckCircle2 className="h-3 w-3" />
            회의록 저장됨
          </Badge>
          <Button variant="ghost" size="sm" onClick={() => onView(event.meeting_id!)}>
            보기
            <FileText className="h-3 w-3" />
          </Button>
        </span>
      ) : (
        <Button
          size="sm"
          variant={active ? "secondary" : "outline"}
          onClick={() => onSelect(active ? null : event)}
        >
          {active ? "선택 해제" : "이 회의 기록"}
        </Button>
      )}
    </div>
  );
}

function MeetingPreviewDialog({
  open,
  loading,
  meeting,
  onOpenChange,
}: {
  open: boolean;
  loading: boolean;
  meeting: Meeting | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{meeting?.title || "회의록"}</DialogTitle>
          <DialogDescription>
            {meeting
              ? `${formatDateTime(meeting.event_start || meeting.created_at)}${
                  meeting.event_location ? ` · ${meeting.event_location}` : ""
                } · ${meeting.author_name ?? ""}`
              : "회의록을 불러오는 중입니다."}
          </DialogDescription>
        </DialogHeader>
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : meeting ? (
          <div className="space-y-4">
            {meeting.has_audio ? (
              <ArchivedAudio
                kind="meeting"
                id={meeting.meeting_id}
                name={meeting.audio_name}
                size={meeting.audio_size}
              />
            ) : null}
            <div className="markdown-body max-h-[50vh] overflow-auto rounded-lg border bg-muted/20 p-3">
              <ReactMarkdown>{meeting.ai_summary || "_요약 없음_"}</ReactMarkdown>
            </div>
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
                <p className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
                  {meeting.raw_transcript}
                </p>
              </details>
            ) : null}
            <Button asChild variant="outline" size="sm">
              <Link href="/meetings?tab=history">
                회의록 목록
                <ExternalLink className="h-3.5 w-3.5" />
              </Link>
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
