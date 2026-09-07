"use client";

import { useMemo, useState } from "react";
import { CalendarClock, ChevronLeft, ChevronRight, Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn, STATUS_META } from "@/lib/utils";
import type { Task } from "@/types";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

interface CalendarViewProps {
  tasks: Task[];
  onEdit: (task: Task) => void;
}

function startOfDay(value: Date) {
  const d = new Date(value);
  d.setHours(0, 0, 0, 0);
  return d;
}

function toKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

export function CalendarView({ tasks, onEdit }: CalendarViewProps) {
  const today = startOfDay(new Date());
  const [cursor, setCursor] = useState(() => new Date(today.getFullYear(), today.getMonth(), 1));

  const { cells, dueMap, startMap, undated } = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const gridStart = new Date(first);
    gridStart.setDate(1 - first.getDay());

    const cells = Array.from({ length: 42 }, (_, i) => {
      const date = new Date(gridStart);
      date.setDate(gridStart.getDate() + i);
      return startOfDay(date);
    });

    const dueMap = new Map<string, Task[]>();
    const startMap = new Map<string, Task[]>();
    const undated: Task[] = [];

    tasks.forEach((task) => {
      if (task.due_date) dueMap.set(task.due_date, [...(dueMap.get(task.due_date) ?? []), task]);
      if (task.start_date) startMap.set(task.start_date, [...(startMap.get(task.start_date) ?? []), task]);
      if (!task.due_date && !task.start_date) undated.push(task);
    });

    return { cells, dueMap, startMap, undated };
  }, [cursor, tasks]);

  const monthTaskCount = cells
    .filter((date) => date.getMonth() === cursor.getMonth())
    .reduce((sum, date) => sum + (dueMap.get(toKey(date))?.length ?? 0), 0);

  function shiftMonth(delta: number) {
    setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + delta, 1));
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => shiftMonth(-1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="min-w-[130px] text-center text-sm font-semibold">
            {cursor.getFullYear()}년 {cursor.getMonth() + 1}월
          </span>
          <Button variant="outline" size="sm" onClick={() => shiftMonth(1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setCursor(new Date(today.getFullYear(), today.getMonth(), 1))}
          >
            오늘
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span>이번 달 마감 {monthTaskCount}건</span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm bg-blue-500" />
            마감일
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded-sm border-2 border-dashed border-slate-400" />
            착수일
          </span>
        </div>
      </div>

      <Card className="overflow-hidden">
        <div className="grid grid-cols-7 border-b bg-muted/40">
          {WEEKDAYS.map((day, index) => (
            <div
              key={day}
              className={cn(
                "px-2 py-1.5 text-center text-[11px] font-medium",
                index === 0 && "text-rose-500",
                index === 6 && "text-blue-500",
                index !== 0 && index !== 6 && "text-muted-foreground",
              )}
            >
              {day}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7">
          {cells.map((date) => {
            const key = toKey(date);
            const inMonth = date.getMonth() === cursor.getMonth();
            const isToday = date.getTime() === today.getTime();
            const dueTasks = dueMap.get(key) ?? [];
            const startTasks = (startMap.get(key) ?? []).filter(
              (task) => !dueTasks.some((item) => item.task_id === task.task_id),
            );

            return (
              <div
                key={key}
                className={cn(
                  "min-h-[104px] border-b border-r p-1.5",
                  !inMonth && "bg-muted/30 text-muted-foreground",
                  isToday && "bg-blue-50/70",
                )}
              >
                <div className="mb-1 flex items-center justify-between">
                  <span
                    className={cn(
                      "inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[11px]",
                      isToday && "bg-blue-600 font-semibold text-white",
                      !isToday && date.getDay() === 0 && "text-rose-500",
                      !isToday && date.getDay() === 6 && "text-blue-500",
                    )}
                  >
                    {date.getDate()}
                  </span>
                  {dueTasks.length > 2 ? (
                    <span className="text-[10px] text-muted-foreground">{dueTasks.length}건</span>
                  ) : null}
                </div>

                <div className="space-y-1">
                  {dueTasks.slice(0, 3).map((task) => (
                    <CalendarChip key={task.task_id} task={task} onEdit={onEdit} />
                  ))}
                  {dueTasks.length > 3 ? (
                    <p className="pl-1 text-[10px] text-muted-foreground">+{dueTasks.length - 3}건 더</p>
                  ) : null}
                  {startTasks.slice(0, 2).map((task) => (
                    <CalendarChip key={`start-${task.task_id}`} task={task} onEdit={onEdit} start />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {undated.length ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2 py-3">
            <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <CalendarClock className="h-3.5 w-3.5" />
              일정 미지정 {undated.length}건
            </span>
            {undated.map((task) => (
              <button
                key={task.task_id}
                type="button"
                onClick={() => onEdit(task)}
                className="rounded-md border px-2 py-1 text-[11px] hover:bg-muted"
              >
                {task.task_name}
              </button>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function CalendarChip({
  task,
  onEdit,
  start = false,
}: {
  task: Task;
  onEdit: (task: Task) => void;
  start?: boolean;
}) {
  const meta = STATUS_META[task.status];
  return (
    <button
      type="button"
      onClick={() => onEdit(task)}
      title={`${task.task_id} · ${task.task_name} · ${task.status} ${task.progress}%${
        start ? " (착수일)" : " (마감일)"
      }`}
      className={cn(
        "flex w-full items-center gap-1 rounded-md px-1.5 py-1 text-left text-[10px] font-semibold ring-1 transition hover:brightness-95",
        start ? "border border-dashed bg-transparent ring-transparent" : meta.chip,
        task.is_delayed && !start && "ring-rose-300",
      )}
    >
      <span className={cn("h-2 w-2 shrink-0 rounded-sm", meta.dot)} />
      <span className="truncate">{task.task_name}</span>
      {!task.can_edit ? <Lock className="h-2.5 w-2.5 shrink-0 opacity-60" /> : null}
    </button>
  );
}
