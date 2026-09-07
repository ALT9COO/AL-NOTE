import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

import type { Task } from "@/types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const STATUSES = ["할당", "진행중", "이슈 발생", "완료"] as const;

export const STATUS_META: Record<
  (typeof STATUSES)[number],
  { accent: string; bar: string; chip: string; dot: string }
> = {
  할당: {
    accent: "border-l-slate-400",
    bar: "bg-slate-400",
    chip: "bg-slate-100 text-slate-700 ring-slate-200",
    dot: "bg-slate-400",
  },
  진행중: {
    accent: "border-l-blue-500",
    bar: "bg-blue-500",
    chip: "bg-blue-50 text-blue-700 ring-blue-200",
    dot: "bg-blue-500",
  },
  "이슈 발생": {
    accent: "border-l-amber-500",
    bar: "bg-amber-500",
    chip: "bg-amber-50 text-amber-700 ring-amber-200",
    dot: "bg-amber-500",
  },
  완료: {
    accent: "border-l-emerald-500",
    bar: "bg-emerald-500",
    chip: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    dot: "bg-emerald-500",
  },
};

export const STATUS_CHART_COLORS: Record<string, string> = {
  할당: "#94a3b8",
  진행중: "#3b82f6",
  "이슈 발생": "#f59e0b",
  완료: "#22c55e",
};

/** 마감일까지 남은 일수를 D-day 배지 텍스트로 변환 */
export function dueBadge(due?: string | null): { label: string; tone: "muted" | "warn" | "late" } {
  if (!due) return { label: "기한 없음", tone: "muted" };
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(`${due}T00:00:00`);
  const diff = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  const date = `${target.getMonth() + 1}/${target.getDate()}`;
  if (diff < 0) return { label: `${date} · D+${Math.abs(diff)}`, tone: "late" };
  if (diff <= 3) return { label: `${date} · D-${diff}`, tone: "warn" };
  return { label: `${date} · D-${diff}`, tone: "muted" };
}

export function initials(name?: string | null) {
  if (!name) return "?";
  return name.trim().slice(0, 2);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function formatRelativeTime(value?: string | null) {
  if (!value) return "";
  const diff = Date.now() - new Date(value).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "방금";
  if (minutes < 60) return `${minutes}분 전`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}시간 전`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}일 전`;
  return formatDateTime(value);
}

export type DashboardPeriod = "monthly" | "halfyear" | "yearly";

export const DASHBOARD_PERIODS: { value: DashboardPeriod; label: string }[] = [
  { value: "monthly", label: "월" },
  { value: "halfyear", label: "반기" },
  { value: "yearly", label: "연간" },
];

function startOfDay(date: Date) {
  const copy = new Date(date);
  copy.setHours(0, 0, 0, 0);
  return copy;
}

function parseDateOnly(value: string) {
  return startOfDay(new Date(`${value.slice(0, 10)}T00:00:00`));
}

/** 대시보드 기간 필터 범위 (월 / 반기 / 연간). */
export function dashboardPeriodRange(period: DashboardPeriod, anchor = new Date()) {
  const year = anchor.getFullYear();
  const month = anchor.getMonth();

  if (period === "monthly") {
    const start = new Date(year, month, 1);
    const end = new Date(year, month + 1, 0);
    return { start, end, label: `${year}년 ${month + 1}월` };
  }
  if (period === "halfyear") {
    if (month < 6) {
      return {
        start: new Date(year, 0, 1),
        end: new Date(year, 5, 30),
        label: `${year}년 상반기`,
      };
    }
    return {
      start: new Date(year, 6, 1),
      end: new Date(year, 11, 31),
      label: `${year}년 하반기`,
    };
  }
  return {
    start: new Date(year, 0, 1),
    end: new Date(year, 11, 31),
    label: `${year}년`,
  };
}

export function formatDateOnly(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate(),
  ).padStart(2, "0")}`;
}

/** 갱신일·마감일·진행 구간이 선택 기간과 겹치는 업무인지 판별한다. */
export function taskInDashboardPeriod(task: Task, start: Date, end: Date) {
  const rangeStart = startOfDay(start);
  const rangeEnd = startOfDay(end);

  if (task.updated_at) {
    const updated = startOfDay(new Date(task.updated_at));
    if (updated >= rangeStart && updated <= rangeEnd) return true;
  }
  if (task.due_date) {
    const due = parseDateOnly(task.due_date);
    if (due >= rangeStart && due <= rangeEnd) return true;
  }
  if (task.start_date && task.due_date) {
    const taskStart = parseDateOnly(task.start_date);
    const taskDue = parseDateOnly(task.due_date);
    if (taskStart <= rangeEnd && taskDue >= rangeStart) return true;
  }
  return false;
}

export function isTopLevelTask(task: Task) {
  return !task.parent_task_id;
}

export function childrenOf(tasks: Task[], parentId: string) {
  return tasks
    .filter((task) => task.parent_task_id === parentId)
    .sort((left, right) => left.task_id.localeCompare(right.task_id, "ko"));
}
