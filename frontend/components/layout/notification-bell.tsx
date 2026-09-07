"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { apiErrorMessage, taskApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TaskAlert } from "@/types";

const DISMISS_KEY = "alnote_dismissed_alerts";

function loadDismissed(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(DISMISS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter((id) => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

function persistDismissed(ids: Set<string>) {
  window.localStorage.setItem(DISMISS_KEY, JSON.stringify([...ids]));
}

export function NotificationBell() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<TaskAlert[]>([]);
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  useEffect(() => {
    setDismissed(loadDismissed());
    taskApi
      .alerts()
      .then(setAlerts)
      .catch((e) => toast.error(apiErrorMessage(e, "알림 목록 오류")));
  }, []);

  const visible = useMemo(
    () => alerts.filter((item) => !dismissed.has(item.task_id)).sort((a, b) => a.days_left - b.days_left),
    [alerts, dismissed],
  );

  function dismiss(taskId: string) {
    setDismissed((prev) => {
      const next = new Set([...prev, taskId]);
      persistDismissed(next);
      return next;
    });
  }

  function openTask(taskId: string) {
    setOpen(false);
    window.dispatchEvent(new CustomEvent("alnote:open-task", { detail: taskId }));
    router.push(`/dashboard?task=${encodeURIComponent(taskId)}`);
  }

  const urgentCount = visible.filter((item) => item.days_left <= 0).length;
  const totalCount = visible.length;

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative h-8 w-8" title="마감 임박 알림">
          <Bell className="h-4 w-4" />
          {totalCount > 0 && (
            <span
              className={cn(
                "absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-bold text-white",
                urgentCount > 0 ? "bg-red-500" : "bg-amber-400",
              )}
            >
              {totalCount > 9 ? "9+" : totalCount}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="text-xs font-semibold">
          마감 임박 업무 ({totalCount}건)
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {visible.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            마감 임박 업무가 없습니다.
          </p>
        ) : (
          <ul className="max-h-72 overflow-y-auto">
            {visible.map((item) => (
              <li
                key={item.task_id}
                className="flex items-start justify-between gap-2 px-3 py-2 hover:bg-muted/50"
              >
                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => openTask(item.task_id)}
                >
                  <p className="truncate text-xs font-medium">{item.task_name}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {item.task_id}
                    {item.assignee_name ? ` · ${item.assignee_name}` : ""}
                  </p>
                </button>
                <div className="flex shrink-0 items-center gap-1.5">
                  <Badge
                    variant={
                      item.days_left < 0 ? "danger" : item.days_left === 0 ? "warning" : "muted"
                    }
                    className="text-[10px]"
                  >
                    {item.days_left < 0
                      ? `${Math.abs(item.days_left)}일 초과`
                      : item.days_left === 0
                        ? "오늘"
                        : `${item.days_left}일 후`}
                  </Badge>
                  <button
                    type="button"
                    className="text-[10px] text-muted-foreground hover:text-foreground"
                    onClick={() => dismiss(item.task_id)}
                    title="알림 숨기기"
                  >
                    ✕
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
