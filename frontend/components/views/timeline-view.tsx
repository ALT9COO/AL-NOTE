"use client";

import { useMemo, useState } from "react";
import { Lock } from "lucide-react";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn, initials, STATUS_META } from "@/lib/utils";
import type { Task } from "@/types";

const DAY_MS = 86_400_000;
const DAY_WIDTH = 34;
const LABEL_WIDTH = 240;
const STICKY_LABEL =
  "sticky left-0 z-30 shrink-0 border-r bg-card shadow-[4px_0_8px_-4px_rgba(15,23,42,0.12)]";
const STICKY_GROUP =
  "sticky left-0 z-30 shrink-0 border-r bg-muted shadow-[4px_0_8px_-4px_rgba(15,23,42,0.12)]";

type GroupMode = "assignee" | "status" | "none";

interface TimelineViewProps {
  tasks: Task[];
  onEdit: (task: Task) => void;
}

function startOfDay(value: Date) {
  const d = new Date(value);
  d.setHours(0, 0, 0, 0);
  return d;
}

function parseDate(value?: string | null) {
  return value ? startOfDay(new Date(`${value}T00:00:00`)) : null;
}

function addDays(base: Date, days: number) {
  return new Date(base.getTime() + days * DAY_MS);
}

function diffDays(a: Date, b: Date) {
  return Math.round((a.getTime() - b.getTime()) / DAY_MS);
}

export function TimelineView({ tasks, onEdit }: TimelineViewProps) {
  const [group, setGroup] = useState<GroupMode>("assignee");
  const today = startOfDay(new Date());

  const { rangeStart, days } = useMemo(() => {
    const points: Date[] = [today];
    tasks.forEach((task) => {
      const start = parseDate(task.start_date);
      const due = parseDate(task.due_date);
      if (start) points.push(start);
      if (due) points.push(due);
    });
    const min = new Date(Math.min(...points.map((d) => d.getTime())));
    const max = new Date(Math.max(...points.map((d) => d.getTime())));
    const start = addDays(min, -3);
    const total = Math.max(diffDays(max, start) + 5, 21);
    return { rangeStart: start, days: total };
  }, [tasks, today]);

  const groups = useMemo(() => {
    const scheduled = [...tasks].sort((a, b) => {
      const aStart = parseDate(a.start_date ?? a.due_date)?.getTime() ?? 0;
      const bStart = parseDate(b.start_date ?? b.due_date)?.getTime() ?? 0;
      return aStart - bStart;
    });

    if (group === "none") return [{ key: "전체 업무", tasks: scheduled }];

    const buckets: { key: string; tasks: Task[] }[] = [];
    scheduled.forEach((task) => {
      const key = group === "assignee" ? task.assignee_name ?? "담당자 미지정" : task.status;
      const bucket = buckets.find((item) => item.key === key);
      if (bucket) bucket.tasks.push(task);
      else buckets.push({ key, tasks: [task] });
    });
    return buckets;
  }, [tasks, group]);

  const gridWidth = days * DAY_WIDTH;
  const todayOffset = diffDays(today, rangeStart);

  if (!tasks.length) {
    return (
      <Card>
        <CardContent className="py-16 text-center text-sm text-muted-foreground">
          표시할 업무가 없습니다.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">그룹 기준</span>
          <Select value={group} onValueChange={(value) => setGroup(value as GroupMode)}>
            <SelectTrigger className="h-8 w-[130px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="assignee">담당자별</SelectItem>
              <SelectItem value="status">상태별</SelectItem>
              <SelectItem value="none">전체</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          {Object.entries(STATUS_META).map(([status, meta]) => (
            <span key={status} className="flex items-center gap-1">
              <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
              {status}
            </span>
          ))}
          <span className="flex items-center gap-1">
            <span className="h-3 w-px bg-rose-500" />
            오늘
          </span>
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <div style={{ minWidth: LABEL_WIDTH + gridWidth }}>
            <TimelineHeader rangeStart={rangeStart} days={days} today={today} />

            {groups.map((bucket) => (
              <div key={bucket.key}>
                <div className="flex border-b bg-muted/50">
                  <div
                    className={cn(STICKY_GROUP, "flex items-center gap-2 px-4 py-1.5")}
                    style={{ width: LABEL_WIDTH }}
                  >
                    <span className="truncate text-xs font-semibold">{bucket.key}</span>
                    <span className="shrink-0 text-[10px] text-muted-foreground">
                      {bucket.tasks.length}건
                    </span>
                  </div>
                  <div className="bg-muted/50" style={{ width: gridWidth, minHeight: 28 }} />
                </div>

                {bucket.tasks.map((task) => (
                  <TimelineRow
                    key={task.task_id}
                    task={task}
                    rangeStart={rangeStart}
                    days={days}
                    todayOffset={todayOffset}
                    onEdit={onEdit}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}

function TimelineHeader({
  rangeStart,
  days,
  today,
}: {
  rangeStart: Date;
  days: number;
  today: Date;
}) {
  const cells = Array.from({ length: days }, (_, i) => addDays(rangeStart, i));
  const months: { label: string; span: number }[] = [];
  cells.forEach((date) => {
    const label = `${date.getFullYear()}년 ${date.getMonth() + 1}월`;
    const last = months[months.length - 1];
    if (last && last.label === label) last.span += 1;
    else months.push({ label, span: 1 });
  });

  return (
    <div className="sticky top-0 z-40 border-b bg-card">
      <div className="flex">
        <div
          className={cn(STICKY_LABEL, "z-40 px-4 py-1 text-[11px] font-medium text-muted-foreground")}
          style={{ width: LABEL_WIDTH }}
        >
          업무
        </div>
        <div className="flex">
          {months.map((month) => (
            <div
              key={month.label}
              className="border-r px-2 py-1 text-[11px] font-medium text-muted-foreground"
              style={{ width: month.span * DAY_WIDTH }}
            >
              {month.label}
            </div>
          ))}
        </div>
      </div>
      <div className="flex">
        <div className={cn(STICKY_LABEL, "z-40")} style={{ width: LABEL_WIDTH }} />
        {cells.map((date) => {
          const isToday = date.getTime() === today.getTime();
          const isWeekend = date.getDay() === 0 || date.getDay() === 6;
          return (
            <div
              key={date.toISOString()}
              className={cn(
                "shrink-0 border-r py-1 text-center text-[10px]",
                isWeekend && "bg-muted/40",
                isToday ? "font-semibold text-rose-600" : "text-muted-foreground",
              )}
              style={{ width: DAY_WIDTH }}
            >
              {date.getDate()}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TimelineRow({
  task,
  rangeStart,
  days,
  todayOffset,
  onEdit,
}: {
  task: Task;
  rangeStart: Date;
  days: number;
  todayOffset: number;
  onEdit: (task: Task) => void;
}) {
  const meta = STATUS_META[task.status];
  const start = parseDate(task.start_date);
  const due = parseDate(task.due_date);

  // 한쪽 날짜만 있으면 하루짜리 막대로, 둘 다 없으면 막대를 그리지 않는다.
  const barStart = start ?? due;
  const barEnd = due ?? start;
  const rawOffset = barStart ? diffDays(barStart, rangeStart) : 0;
  const offset = Math.max(rawOffset, 0);
  const totalSpan = barStart && barEnd ? Math.max(diffDays(barEnd, barStart) + 1, 1) : 0;
  const span =
    totalSpan > 0 ? Math.max(rawOffset < 0 ? totalSpan + rawOffset : totalSpan, 1) : 0;
  const barLeft = offset * DAY_WIDTH + 3;
  const barWidth = Math.max(span * DAY_WIDTH - 6, 8);

  return (
    <div className="flex border-b last:border-0">
      <button
        type="button"
        onClick={() => onEdit(task)}
        className={cn(STICKY_LABEL, "flex items-center gap-2 px-4 py-2 text-left hover:bg-muted/30")}
        style={{ width: LABEL_WIDTH }}
      >
        <Avatar className="h-6 w-6">
          <AvatarFallback className="text-[9px]">
            {initials(task.assignee_name ?? "?")}
          </AvatarFallback>
        </Avatar>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-medium">{task.task_name}</span>
          <span className="block font-mono text-[10px] text-muted-foreground">{task.task_id}</span>
        </span>
        {!task.can_edit ? <Lock className="h-3 w-3 shrink-0 text-muted-foreground" /> : null}
      </button>

      <div className="relative isolate overflow-hidden bg-card" style={{ width: days * DAY_WIDTH }}>
        <div className="absolute inset-0 flex">
          {Array.from({ length: days }, (_, i) => {
            const date = addDays(rangeStart, i);
            const isWeekend = date.getDay() === 0 || date.getDay() === 6;
            return (
              <div
                key={i}
                className={cn("shrink-0 border-r border-border/50", isWeekend && "bg-muted/40")}
                style={{ width: DAY_WIDTH }}
              />
            );
          })}
        </div>

        <div
          className="pointer-events-none absolute inset-y-0 z-[2] w-px bg-rose-500/70"
          style={{ left: todayOffset * DAY_WIDTH + DAY_WIDTH / 2 }}
        />

        {span > 0 ? (
          <button
            type="button"
            onClick={() => onEdit(task)}
            title={`${task.task_name} · ${task.status} ${task.progress}%`}
            className={cn(
              "absolute top-1.5 z-[1] h-7 overflow-hidden rounded-md text-left shadow-sm ring-1 ring-black/5 transition hover:brightness-95",
              task.is_delayed ? "ring-2 ring-rose-400" : "",
            )}
            style={{ left: barLeft, width: barWidth, maxWidth: days * DAY_WIDTH - barLeft - 3 }}
          >
            <span className={cn("absolute inset-0 opacity-25", meta.bar)} />
            <span
              className={cn("absolute inset-y-0 left-0", meta.bar)}
              style={{ width: `${task.progress}%` }}
            />
            <span className="relative flex h-full items-center gap-1 px-2 text-[10px] font-medium text-slate-800">
              <span className="truncate">{task.task_name}</span>
              <span className="shrink-0 opacity-70">{task.progress}%</span>
            </span>
          </button>
        ) : (
          <span className="absolute left-2 top-2 z-[1] text-[10px] text-muted-foreground">
            일정 미지정
          </span>
        )}
      </div>
    </div>
  );
}
