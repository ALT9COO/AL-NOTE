"use client";

import { useEffect, useState } from "react";
import { CalendarPlus, Loader2, LogIn } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, calendarApi } from "@/lib/api";
import type { CalendarConnection, CalendarEvent, MeetingParseResult } from "@/types";

function pad(n: number) {
  return String(n).padStart(2, "0");
}

function toLocalInput(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function nextWeekdayTen() {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  while (date.getDay() === 0 || date.getDay() === 6) {
    date.setDate(date.getDate() + 1);
  }
  date.setHours(10, 0, 0, 0);
  return date;
}

function defaultBody(parsed: MeetingParseResult | null) {
  if (!parsed) return "";
  const lines: string[] = [];
  if (parsed.summary_bullets.length) {
    lines.push("## 회의 요약");
    parsed.summary_bullets.forEach((item) => lines.push(`- ${item}`));
  }
  if (parsed.action_items.length) {
    lines.push("", "## 액션 아이템");
    parsed.action_items.forEach((item) => {
      const extra = [item.assignee, item.due_date].filter(Boolean).join(", ");
      lines.push(`- ${item.title}${extra ? ` (${extra})` : ""}`);
    });
  }
  return lines.join("\n").trim();
}

export function OutlookEventDialog({
  open,
  onOpenChange,
  parsed,
  event,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parsed: MeetingParseResult | null;
  event: CalendarEvent | null;
}) {
  const [connection, setConnection] = useState<CalendarConnection | null>(null);
  const [title, setTitle] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [location, setLocation] = useState("");
  const [attendees, setAttendees] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    if (!open) return;
    calendarApi.connection().then(setConnection).catch(() => setConnection(null));
    const startAt = nextWeekdayTen();
    const endAt = new Date(startAt.getTime() + 60 * 60 * 1000);
    setTitle(`${parsed?.meeting_title || event?.title || "회의"} 후속`);
    setStart(toLocalInput(startAt));
    setEnd(toLocalInput(endAt));
    setLocation(event?.location ?? "");
    setAttendees(
      (event?.attendees ?? [])
        .map((person) => person.email)
        .filter(Boolean)
        .join(", "),
    );
    setBody(defaultBody(parsed));
  }, [open, parsed, event]);

  async function handleConnect() {
    setConnecting(true);
    try {
      const { url } = await calendarApi.loginUrl();
      window.location.href = url;
    } catch (error) {
      toast.error(apiErrorMessage(error, "로그인 주소를 만들지 못했습니다."));
      setConnecting(false);
    }
  }

  async function handleSave() {
    if (!title.trim()) {
      toast.error("일정 제목을 입력하세요.");
      return;
    }
    if (!start || !end) {
      toast.error("시작·종료 시각을 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      const people = attendees
        .split(/[,;\n]/)
        .map((raw) => raw.trim())
        .filter(Boolean)
        .map((email) => ({ name: email.split("@")[0], email }));
      const created = await calendarApi.createEvent({
        title: title.trim(),
        start: start.length === 16 ? `${start}:00` : start,
        end: end.length === 16 ? `${end}:00` : end,
        location: location.trim(),
        body,
        attendees: people,
      });
      toast.success(
        created.web_link
          ? "Outlook 일정을 만들었습니다. Outlook에서 확인할 수 있습니다."
          : "Outlook 일정을 만들었습니다.",
      );
      if (created.web_link) window.open(created.web_link, "_blank", "noopener");
      onOpenChange(false);
    } catch (error) {
      toast.error(apiErrorMessage(error, "일정을 만들지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  const canWrite = connection?.connected && connection.can_write && !connection.needs_reauth;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarPlus className="h-4 w-4 text-primary" />
            Outlook에 후속 일정 잡기
          </DialogTitle>
          <DialogDescription>
            회의 요약을 본문에 넣고, 연결된 본인 Outlook 캘린더에 일정을 만듭니다.
          </DialogDescription>
        </DialogHeader>

        {!canWrite ? (
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            <p>
              {connection?.connected
                ? "일정 만들기에는 Calendars.ReadWrite 권한이 필요합니다. Microsoft 계정을 다시 연결해 동의를 추가하세요."
                : "먼저 Microsoft 계정을 연결해야 일정을 만들 수 있습니다."}
            </p>
            <Button size="sm" disabled={connecting} onClick={handleConnect}>
              {connecting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <LogIn className="h-3.5 w-3.5" />
              )}
              Microsoft 계정 연결
            </Button>
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="evt_title">제목</Label>
              <Input id="evt_title" value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="evt_start">시작</Label>
                <Input
                  id="evt_start"
                  type="datetime-local"
                  value={start}
                  onChange={(e) => setStart(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="evt_end">종료</Label>
                <Input
                  id="evt_end"
                  type="datetime-local"
                  value={end}
                  onChange={(e) => setEnd(e.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="evt_loc">장소</Label>
              <Input
                id="evt_loc"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="Teams / 회의실"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="evt_to">참석자 이메일</Label>
              <Input
                id="evt_to"
                value={attendees}
                onChange={(e) => setAttendees(e.target.value)}
                placeholder="여러 명은 쉼표로 구분"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="evt_body">본문</Label>
              <Textarea
                id="evt_body"
                rows={8}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                className="font-mono text-xs"
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            닫기
          </Button>
          {canWrite ? (
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarPlus className="h-4 w-4" />}
              Outlook에 만들기
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
