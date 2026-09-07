"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, CalendarDays, Mic } from "lucide-react";

import { calendarApi } from "@/lib/api";
import { cn, formatDateTime } from "@/lib/utils";
import type { CalendarEvent, Task } from "@/types";

function isToday(iso: string) {
  const date = new Date(iso);
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  );
}

export function TodayBriefing({ delayed }: { delayed: Task[] }) {
  const [todayEvents, setTodayEvents] = useState<CalendarEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    calendarApi
      .events({ days_back: 0, days_ahead: 1 })
      .then((data) => {
        setConnected(data.connection.connected);
        setTodayEvents(
          data.events.filter((event) => !event.is_cancelled && isToday(event.start)).slice(0, 3),
        );
      })
      .catch(() => {
        setConnected(false);
        setTodayEvents([]);
      });
  }, []);

  if (!delayed.length && !todayEvents.length && !connected) return null;

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border bg-card px-3 py-2 text-xs">
      {delayed.length ? (
        <p className="flex items-center gap-1.5 text-red-600">
          <AlertTriangle className="h-3.5 w-3.5" />
          지연 업무 {delayed.length}건
          <span className="hidden text-muted-foreground sm:inline">
            · {delayed.slice(0, 2).map((task) => task.task_name).join(", ")}
            {delayed.length > 2 ? " 외" : ""}
          </span>
        </p>
      ) : (
        <p className="text-muted-foreground">지연된 업무는 없습니다.</p>
      )}

      {todayEvents.length ? (
        <p className={cn("flex min-w-0 items-center gap-1.5", delayed.length && "border-l pl-4")}>
          <CalendarDays className="h-3.5 w-3.5 shrink-0 text-primary" />
          <span className="truncate">
            오늘 일정 {todayEvents.length}건 · {todayEvents[0].title}
            {todayEvents[0].start ? ` (${formatDateTime(todayEvents[0].start)})` : ""}
          </span>
          <Link href="/meetings" className="shrink-0 font-medium text-primary hover:underline">
            회의실
          </Link>
        </p>
      ) : connected ? (
        <p className={cn("flex items-center gap-1.5 text-muted-foreground", delayed.length && "border-l pl-4")}>
          <CalendarDays className="h-3.5 w-3.5" />
          오늘 연결된 캘린더 일정은 없습니다.
        </p>
      ) : (
        <p className={cn("flex items-center gap-1.5 text-muted-foreground", delayed.length && "border-l pl-4")}>
          <Mic className="h-3.5 w-3.5" />
          <Link href="/meetings" className="hover:text-foreground hover:underline">
            Outlook을 연결하면 오늘 회의가 여기에 표시됩니다
          </Link>
        </p>
      )}
    </div>
  );
}
