"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Archive,
  ArrowRight,
  CalendarCheck2,
  CalendarPlus,
  CheckCircle2,
  ChevronDown,
  FileText,
  History,
  Loader2,
  Mic,
  Play,
  Sparkles,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { AgendaReview } from "@/components/meetings/agenda-review";
import { ArchivedAudio } from "@/components/meetings/archived-audio";
import { AudioRecorder } from "@/components/meetings/audio-recorder";
import { CalendarPanel } from "@/components/meetings/calendar-panel";
import { MeetingHistory } from "@/components/meetings/meeting-history";
import { OutlookEventDialog } from "@/components/meetings/outlook-event-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, authApi, meetingApi } from "@/lib/api";
import { clearLocalDraft, readLocalDraft, writeLocalDraft } from "@/lib/meeting-draft";
import { useRecording } from "@/lib/recording-context";
import { cn, formatDateTime } from "@/lib/utils";
import type {
  AgendaSubmitResult,
  CalendarEvent,
  Meeting,
  MeetingDraft,
  MeetingParseResult,
  User,
} from "@/types";

const STEPS = [
  { id: 1, label: "음성 입력" },
  { id: 2, label: "전사 확인" },
  { id: 3, label: "안건 검토 · 제출" },
];

export default function MeetingsPage() {
  const [step, setStep] = useState(1);
  const [transcript, setTranscript] = useState("");
  const [parsed, setParsed] = useState<MeetingParseResult | null>(null);
  const [result, setResult] = useState<AgendaSubmitResult | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [drafts, setDrafts] = useState<MeetingDraft[]>([]);
  const [draftId, setDraftId] = useState<number | null>(null);
  const [parsing, setParsing] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [event, setEvent] = useState<CalendarEvent | null>(null);
  const [calendarOpen, setCalendarOpen] = useState(true);
  const [eventDialogOpen, setEventDialogOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [tab, setTab] = useState("workflow");
  const recording = useRecording();

  const loadMeetings = useCallback(async () => {
    try {
      setMeetings(await meetingApi.list());
    } catch (error) {
      toast.error(apiErrorMessage(error, "회의록을 불러오지 못했습니다."));
    }
  }, []);

  const loadDrafts = useCallback(async () => {
    try {
      setDrafts(await meetingApi.listDrafts());
    } catch {
      /* 초안 API 실패는 화면을 막지 않음 */
    }
  }, []);

  useEffect(() => {
    if (!drafts.some((item) => item.stt_status === "transcribing")) return;
    const timer = window.setInterval(() => {
      void loadDrafts();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [drafts, loadDrafts]);

  const persistDraft = useCallback(
    async (next: {
      transcript: string;
      parsed: MeetingParseResult | null;
      event: CalendarEvent | null;
      step: number;
      draftId: number | null;
    }) => {
      const text = next.transcript.trim();
      if (!text) return next.draftId;
      setSavingDraft(true);
      try {
        const payload = {
          transcript: text,
          parsed: next.parsed,
          event: next.event,
          step: next.step,
          title: next.event?.title,
        };
        const saved = next.draftId
          ? await meetingApi.updateDraft(next.draftId, payload)
          : await meetingApi.createDraft(payload);
        setDraftId(saved.draft_id);
        await loadDrafts();
        return saved.draft_id;
      } catch {
        return next.draftId;
      } finally {
        setSavingDraft(false);
      }
    },
    [loadDrafts],
  );

  function applyDraft(draft: MeetingDraft) {
    if (draft.stt_status === "transcribing") {
      toast.info("전사가 끝난 뒤 이어서 진행할 수 있습니다.");
      return;
    }
    const transcript = draft.transcript ?? "";
    setDraftId(draft.draft_id);
    setTranscript(transcript);
    setParsed(draft.parsed);
    setEvent(draft.event);
    setResult(null);
    const nextStep =
      draft.parsed && draft.step >= 3 ? 3 : transcript.trim() || draft.has_audio ? 2 : 1;
    setStep(nextStep);
    if (draft.event) setCalendarOpen(true);
    writeLocalDraft({
      draftId: draft.draft_id,
      step: nextStep,
      transcript,
      parsed: draft.parsed,
      event: draft.event,
    });
    toast.success("저장된 전사를 이어서 진행합니다.");
  }

  async function archiveAsMeeting(source?: MeetingDraft | null) {
    const item = source ?? drafts.find((draft) => draft.draft_id === draftId) ?? null;
    const linkedId = item?.draft_id ?? draftId ?? undefined;
    const title = (item?.title || event?.title || "음성 기록").trim();
    const text = (item?.transcript || transcript).trim();
    if (!item?.has_audio && !text && !linkedId) {
      toast.error("보관할 음성이나 전사가 없습니다.");
      return;
    }
    try {
      await meetingApi.submit({
        title,
        transcript: text,
        summary_bullets: text
          ? []
          : ["음성 파일만 보관했습니다. 전사는 아직 없습니다."],
        agenda_items: [],
        action_items: [],
        risks: [],
        task_updates: [],
        event_key: item?.event?.event_key ?? event?.event_key ?? null,
        event_start: item?.event?.start ?? event?.start ?? null,
        event_location: item?.event?.location ?? event?.location ?? null,
        draft_id: linkedId,
      });
      toast.success("회의록에 음성을 보관했습니다.");
      reset();
      setTab("history");
      await loadMeetings();
      await loadDrafts();
    } catch (error) {
      toast.error(apiErrorMessage(error, "회의록 보관에 실패했습니다."));
    }
  }

  useEffect(() => {
    authApi.users().then(setUsers).catch(() => undefined);
    void loadMeetings();
    void loadDrafts();
  }, [loadMeetings, loadDrafts]);

  useEffect(() => {
    const local = readLocalDraft();
    const recordingBusy =
      recording.status === "recording" ||
      recording.status === "uploading" ||
      recording.status === "ready";
    if (local && !recordingBusy && local.transcript.trim()) {
      setStep(local.step || 2);
      setTranscript(local.transcript);
      setParsed(local.parsed);
      setEvent(local.event);
      setDraftId(local.draftId);
      if (local.event) setCalendarOpen(true);
    }
    setHydrated(true);
    void loadDrafts();
    const query = new URLSearchParams(window.location.search);
    if (query.get("tab") === "history") setTab("history");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hydrated || result) return;
    writeLocalDraft({ draftId, step, transcript, parsed, event });
  }, [hydrated, draftId, step, transcript, parsed, event, result]);

  useEffect(() => {
    if (!hydrated || result || !transcript.trim() || step < 2) return;
    const timer = window.setTimeout(() => {
      void persistDraft({ transcript, parsed, event, step, draftId });
    }, 800);
    return () => window.clearTimeout(timer);
  }, [hydrated, result, transcript, parsed, event, step, draftId, persistDraft]);

  useEffect(() => {
    if (recording.status === "recording" || recording.status === "uploading") {
      setStep(1);
      setResult(null);
      if (recording.event) setEvent(recording.event);
    }
  }, [recording.status, recording.event]);

  function handleTranscript(text: string, nextDraftId?: number | null) {
    setTranscript(text);
    setParsed(null);
    setResult(null);
    setStep(2);
    if (nextDraftId) setDraftId(nextDraftId);
    void loadDrafts();
  }

  useEffect(() => {
    if (recording.status !== "ready") return;
    if (!recording.transcript && recording.draftId == null) return;
    if (recording.event) setEvent(recording.event);
    handleTranscript(recording.transcript ?? "", recording.draftId);
    recording.acknowledgeTranscript();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording.status, recording.transcript, recording.draftId]);

  async function handleParse() {
    if (!transcript.trim()) {
      toast.error("전사 내용을 입력하세요.");
      return;
    }
    setParsing(true);
    try {
      const data = await meetingApi.parse(transcript.trim(), {
        event_title: event?.title,
        attendees: event?.attendees.map((person) => person.name),
      });
      setParsed(data);
      setStep(3);
      const id = await persistDraft({
        transcript,
        parsed: data,
        event,
        step: 3,
        draftId,
      });
      if (id) setDraftId(id);
    } catch (error) {
      toast.error(apiErrorMessage(error, "AI 분석에 실패했습니다."));
    } finally {
      setParsing(false);
    }
  }

  function handleSubmitted(submitResult: AgendaSubmitResult) {
    setResult(submitResult);
    setDraftId(null);
    clearLocalDraft();
    void loadMeetings();
    void loadDrafts();
  }

  function reset() {
    setStep(1);
    setTranscript("");
    setParsed(null);
    setResult(null);
    setEvent(null);
    setDraftId(null);
    clearLocalDraft();
  }

  async function discardDraft(id: number) {
    try {
      await meetingApi.deleteDraft(id);
      if (draftId === id) reset();
      await loadDrafts();
      toast.success("저장된 전사를 삭제했습니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "초안을 삭제하지 못했습니다."));
    }
  }

  async function retryDraftStt(id: number) {
    try {
      await meetingApi.retryTranscribe(id);
      await loadDrafts();
      toast.info("전사를 다시 시작합니다.");
    } catch (error) {
      toast.error(apiErrorMessage(error, "전사를 다시 시작하지 못했습니다."));
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">AI 회의실</h1>
        <p className="text-sm text-muted-foreground">
          녹음 → 음성 전사 → AI 안건 추출 → 검토 후 업무 현황에 일괄 반영합니다.
        </p>
      </header>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="workflow">
            <Mic className="h-3.5 w-3.5" />
            회의 분석
          </TabsTrigger>
          <TabsTrigger value="history">
            <History className="h-3.5 w-3.5" />
            회의록 ({meetings.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="workflow" className="space-y-5">
          <ol className="flex flex-wrap items-center gap-2">
            {STEPS.map((item, index) => (
              <li key={item.id} className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                    step === item.id
                      ? "border-primary bg-primary text-primary-foreground"
                      : step > item.id
                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                        : "bg-muted text-muted-foreground",
                  )}
                >
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/20 text-[10px]">
                    {item.id}
                  </span>
                  {item.label}
                </span>
                {index < STEPS.length - 1 ? (
                  <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
                ) : null}
              </li>
            ))}
          </ol>

          {result ? (
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-base text-emerald-700">
                  <CheckCircle2 className="h-4 w-4" />
                  업무 현황 반영 완료
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="grid gap-2 sm:grid-cols-3">
                  <div className="rounded-lg bg-white p-3">
                    <p className="text-xs text-muted-foreground">업데이트</p>
                    <p className="text-lg font-semibold">{result.updated.length}건</p>
                  </div>
                  <div className="rounded-lg bg-white p-3">
                    <p className="text-xs text-muted-foreground">신규 생성</p>
                    <p className="text-lg font-semibold">{result.created.length}건</p>
                  </div>
                  <div className="rounded-lg bg-white p-3">
                    <p className="text-xs text-muted-foreground">권한 등으로 제외</p>
                    <p className="text-lg font-semibold">{result.skipped.length}건</p>
                  </div>
                </div>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  {result.tasks.map((task) => (
                    <li key={task.task_id}>
                      ·{" "}
                      <Link
                        href={`/dashboard?task=${task.task_id}`}
                        className="font-medium text-primary hover:underline"
                      >
                        {task.task_id}
                      </Link>{" "}
                      {task.task_name}
                    </li>
                  ))}
                  {result.skipped.map((line) => (
                    <li key={line} className="text-amber-700">
                      · 제외: {line}
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap gap-2">
                  <Button asChild size="sm">
                    <Link href={result.tasks[0] ? `/dashboard?task=${result.tasks[0].task_id}` : "/dashboard"}>
                      칸반 보드에서 확인
                    </Link>
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setEventDialogOpen(true)}>
                    <CalendarPlus className="h-3.5 w-3.5" />
                    Outlook에 후속 일정 잡기
                  </Button>
                  <Button size="sm" variant="outline" onClick={reset}>
                    새 회의 분석
                  </Button>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {step === 1 && !result ? (
            <>
              {drafts.length ? (
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <FileText className="h-4 w-4 text-primary" />
                      이어서 진행할 전사
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-xs text-muted-foreground">
                      전사가 끝나면 서버에 저장됩니다. PC를 껐다 켜도 여기서 다시 분석·업무 반영을 할 수 있습니다.
                    </p>
                    {drafts.map((item) => (
                      <div
                        key={item.draft_id}
                        className="space-y-2 rounded-lg border bg-muted/30 px-3 py-2"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium">{item.title}</p>
                            <p className="text-[11px] text-muted-foreground">
                              {formatDateTime(item.updated_at)} ·{" "}
                              {item.stt_status === "transcribing"
                                ? "음성 전사 중…"
                                : item.stt_status === "error"
                                  ? item.stt_error || "전사 실패"
                                  : item.parsed
                                    ? "안건 검토 대기"
                                    : "전사 확인 대기"}
                              {item.has_audio ? " · 음성 보관" : ""}
                            </p>
                          </div>
                          <Button
                            size="sm"
                            disabled={item.stt_status === "transcribing"}
                            onClick={() => applyDraft(item)}
                          >
                            {item.stt_status === "transcribing" ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Play className="h-3.5 w-3.5" />
                            )}
                            이어서
                          </Button>
                          {item.stt_status === "error" && item.has_audio ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void retryDraftStt(item.draft_id)}
                            >
                              다시 전사
                            </Button>
                          ) : null}
                          {item.has_audio ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void archiveAsMeeting(item)}
                            >
                              <Archive className="h-3.5 w-3.5" />
                              회의록 보관
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void discardDraft(item.draft_id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                        {item.has_audio ? (
                          <ArchivedAudio
                            kind="draft"
                            id={item.draft_id}
                            name={item.audio_name}
                            size={item.audio_size}
                          />
                        ) : null}
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ) : null}
              <p className="rounded-lg border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                Outlook 일정은 선택 사항입니다. 일정 없이 바로 녹음해도 되고, 한 시간이 넘으면 파일로 올려
                주세요 (최대 200MB).
              </p>
              <AudioRecorder event={event} onTranscript={handleTranscript} />
              <div className="rounded-xl border bg-card">
                <button
                  type="button"
                  onClick={() => setCalendarOpen((open) => !open)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left text-sm"
                >
                  <span className="flex items-center gap-2 font-medium">
                    <CalendarCheck2 className="h-4 w-4 text-primary" />
                    Outlook 일정 연결 (선택)
                    {event ? (
                      <span className="text-xs font-normal text-muted-foreground">· {event.title}</span>
                    ) : null}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 text-muted-foreground transition-transform",
                      calendarOpen && "rotate-180",
                    )}
                  />
                </button>
                {calendarOpen ? (
                  <div className="border-t p-4">
                    <CalendarPanel selected={event} onSelect={setEvent} />
                  </div>
                ) : null}
              </div>
            </>
          ) : null}

          {!result && step > 1 && event ? (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-2 text-xs">
              <CalendarCheck2 className="h-3.5 w-3.5 text-primary" />
              <span className="font-medium">{event.title}</span>
              <span className="text-muted-foreground">{formatDateTime(event.start)}</span>
              {event.location ? (
                <span className="text-muted-foreground">· {event.location}</span>
              ) : null}
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setEvent(null)}>
                일정 연결 해제
              </Button>
            </div>
          ) : null}

          {step === 2 && !result ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">전사 결과 확인 및 수정</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-[11px] text-muted-foreground">
                  녹음 파일은 회의록과 함께 보관됩니다. 브라우저를 닫거나 PC를 다시 켜도 회의실에서 다시
                  듣고 이어서 분석할 수 있습니다.
                  {savingDraft ? " · 저장 중…" : ""}
                </p>
                {draftId && drafts.find((item) => item.draft_id === draftId)?.has_audio ? (
                  <ArchivedAudio
                    kind="draft"
                    id={draftId}
                    name={drafts.find((item) => item.draft_id === draftId)?.audio_name}
                    size={drafts.find((item) => item.draft_id === draftId)?.audio_size}
                  />
                ) : null}
                <Textarea
                  rows={12}
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  placeholder="전사가 비어 있으면 직접 수정하거나, 음성만 회의록으로 보관할 수 있습니다."
                  className="font-mono text-xs leading-relaxed"
                />
                <div className="flex flex-wrap justify-between gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      void persistDraft({ transcript, parsed, event, step, draftId });
                      reset();
                    }}
                  >
                    나중에 이어서
                  </Button>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" onClick={() => setStep(1)}>
                      음성 다시 입력
                    </Button>
                    {draftId && drafts.find((item) => item.draft_id === draftId)?.has_audio ? (
                      <Button variant="outline" onClick={() => void archiveAsMeeting()}>
                        <Archive className="h-3.5 w-3.5" />
                        분석 없이 회의록 보관
                      </Button>
                    ) : null}
                    <Button onClick={handleParse} disabled={parsing || !transcript.trim()}>
                      {parsing ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      AI 회의 분석 실행
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : null}

          {step === 3 && parsed && !result ? (
            <AgendaReview
              parsed={parsed}
              transcript={transcript}
              users={users}
              event={event}
              draftId={draftId}
              hasAudio={Boolean(drafts.find((item) => item.draft_id === draftId)?.has_audio)}
              audioName={drafts.find((item) => item.draft_id === draftId)?.audio_name}
              audioSize={drafts.find((item) => item.draft_id === draftId)?.audio_size}
              onSubmitted={handleSubmitted}
              onBack={() => setStep(2)}
            />
          ) : null}
        </TabsContent>

        <TabsContent value="history">
          <MeetingHistory meetings={meetings} users={users} onUpdated={loadMeetings} />
        </TabsContent>
      </Tabs>

      <OutlookEventDialog
        open={eventDialogOpen}
        onOpenChange={setEventDialogOpen}
        parsed={parsed}
        event={event}
      />
    </div>
  );
}
