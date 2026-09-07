"use client";

import { useEffect, useRef, useState } from "react";
import type { DraggableProvided } from "@hello-pangea/dnd";
import {
  AlertTriangle,
  EyeOff,
  GripVertical,
  ListTree,
  Loader2,
  Lock,
  MessageSquare,
  Plus,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Progress } from "@/components/ui/progress";
import { taskApi, apiErrorMessage } from "@/lib/api";
import { cn, dueBadge, formatRelativeTime, initials, STATUS_META } from "@/lib/utils";
import type { Task } from "@/types";

const TONE_CLASS = {
  muted: "bg-slate-100 text-slate-600",
  warn: "bg-amber-100 text-amber-700",
  late: "bg-red-100 text-red-700 font-semibold",
} as const;

interface TaskCardProps {
  task: Task;
  dragging?: boolean;
  dragHandleProps?: DraggableProvided["dragHandleProps"];
  onOpen: (task: Task) => void;
  onSubtaskAdded?: () => void;
}

function BranchRail({ last }: { last: boolean }) {
  return (
    <div className="relative w-4 shrink-0 self-stretch" aria-hidden>
      <span className={cn("absolute left-[7px] top-0 w-px bg-border", last ? "h-1/2" : "bottom-0")} />
      <span className="absolute left-[7px] top-[14px] h-px w-2.5 bg-border" />
    </div>
  );
}

export function TaskCard({ task, dragging, dragHandleProps, onOpen, onSubtaskAdded }: TaskCardProps) {
  const meta = STATUS_META[task.status];
  const due = dueBadge(task.due_date);
  const collabCount = task.collaborators?.length ?? 0;
  const restricted = (task.viewers?.length ?? 0) > 0;
  const children = task.children ?? [];
  const hasChildren = children.length > 0;
  const canAdd = Boolean(task.can_edit && onSubtaskAdded);
  const [adding, setAdding] = useState(false);
  const [subName, setSubName] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding) inputRef.current?.focus();
  }, [adding]);

  async function submitSubtask() {
    const name = subName.trim();
    if (!name) {
      toast.error("하위 업무명을 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      await taskApi.create({
        task_name: name,
        assigned_to: task.assigned_to,
        dept_id: task.dept_id,
        start_date: task.start_date,
        due_date: task.due_date,
        parent_task_id: task.task_id,
      });
      toast.success("하위 업무를 추가했습니다.");
      setSubName("");
      setAdding(false);
      onSubtaskAdded?.();
    } catch (error) {
      toast.error(apiErrorMessage(error, "하위 업무를 추가하지 못했습니다."));
    } finally {
      setSaving(false);
    }
  }

  const branchRows = children.length + (canAdd ? 1 : 0);

  return (
    <div className="space-y-0">
      <div
        className={cn(
          "group rounded-lg border border-l-4 bg-card shadow-sm transition-all",
          meta.accent,
          dragging ? "rotate-1 shadow-lg ring-2 ring-primary/30" : "hover:shadow-md",
        )}
      >
        <div className="flex items-start gap-1 p-3 pb-0">
          {task.can_edit ? (
            <span
              className="mt-0.5 shrink-0 cursor-grab rounded p-0.5 text-muted-foreground hover:bg-muted active:cursor-grabbing"
              aria-label="드래그하여 상태 변경"
              {...dragHandleProps}
            >
              <GripVertical className="h-3.5 w-3.5" />
            </span>
          ) : (
            <span className="mt-0.5 shrink-0 p-0.5 text-muted-foreground">
              <Lock className="h-3.5 w-3.5" />
            </span>
          )}
          <button type="button" onClick={() => onOpen(task)} className="min-w-0 flex-1 text-left">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                {task.task_id}
              </span>
              <span className="flex items-center gap-1">
                {restricted ? (
                  <EyeOff className="h-3 w-3 text-muted-foreground" aria-label="열람 제한" />
                ) : null}
                <span className={cn("rounded-full px-1.5 py-0.5 text-[10px]", TONE_CLASS[due.tone])}>
                  {due.label}
                </span>
              </span>
            </div>
            <p className="mt-1.5 text-sm font-semibold leading-snug text-foreground">{task.task_name}</p>
          </button>
        </div>

        <button type="button" onClick={() => onOpen(task)} className="block w-full p-3 pt-2 text-left">
          {task.description?.trim() ? (
            <p className="line-clamp-2 text-[11px] leading-snug text-muted-foreground">{task.description}</p>
          ) : null}

          <div className="mt-2 flex items-center gap-2">
            <Avatar className="h-6 w-6">
              <AvatarFallback className="text-[9px]">{initials(task.assignee_name)}</AvatarFallback>
            </Avatar>
            <span className="min-w-0 truncate text-[11px] text-muted-foreground">
              {task.assignee_name ?? "미지정"} · {task.dept_name ?? "-"}
            </span>
            <span className="ml-auto inline-flex shrink-0 items-center gap-1.5 text-[10px] text-muted-foreground">
              {hasChildren ? (
                <span className="inline-flex items-center gap-0.5">
                  <ListTree className="h-3 w-3" />
                  {task.child_count ?? children.length}
                </span>
              ) : null}
              {collabCount ? (
                <span className="inline-flex items-center gap-0.5">
                  <Users className="h-3 w-3" />
                  {collabCount}
                </span>
              ) : null}
            </span>
          </div>

          <div className="mt-2.5 space-y-1">
            <Progress value={task.progress} indicatorClassName={meta.bar} />
            <div className="flex justify-between text-[10px] font-medium text-muted-foreground">
              <span>{hasChildren ? "하위 평균" : ""}</span>
              <span>{task.progress}%</span>
            </div>
          </div>

          {task.issues?.trim() ? (
            <div className="mt-1.5 flex items-start gap-1.5 rounded-md bg-amber-50 px-2 py-1.5 text-[11px] leading-snug text-amber-800">
              <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" />
              <span className="min-w-0">
                <span className="line-clamp-2">{task.issues}</span>
                {task.latest_comment_at ? (
                  <span className="mt-0.5 block text-[10px] text-amber-700/80">
                    {formatRelativeTime(task.latest_comment_at)}
                  </span>
                ) : null}
              </span>
              <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 opacity-70" />
            </div>
          ) : null}
        </button>
      </div>

      {branchRows > 0 ? (
        <ul className="pt-0.5">
          {children.map((child, index) => {
            const childMeta = STATUS_META[child.status];
            const last = index === children.length - 1 && !canAdd;
            return (
              <li key={child.task_id} className="flex items-start">
                <BranchRail last={last} />
                <button
                  type="button"
                  onClick={() => onOpen(child)}
                  className={cn(
                    "mb-1 min-w-0 flex-1 rounded-md border border-l-[3px] bg-card px-2 py-1.5 text-left shadow-sm transition-colors hover:bg-muted/40",
                    childMeta.accent,
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-muted-foreground">{child.task_id}</span>
                    <span className={cn("rounded-full px-1 py-px text-[9px] ring-1", childMeta.chip)}>
                      {child.status}
                    </span>
                    <span className="ml-auto shrink-0 text-[10px] tabular-nums text-muted-foreground">
                      {child.progress}%
                    </span>
                  </div>
                  <p className="mt-0.5 truncate text-[12px] font-medium leading-snug">{child.task_name}</p>
                  <p className="truncate text-[10px] text-muted-foreground">
                    {child.assignee_name ?? "미지정"}
                    {child.dept_name ? ` · ${child.dept_name}` : ""}
                  </p>
                </button>
              </li>
            );
          })}

          {canAdd ? (
            <li className="flex items-start">
              <BranchRail last />
              {adding ? (
                <form
                  className="mb-1 flex min-w-0 flex-1 items-center gap-1 rounded-md border bg-card px-1.5 py-1 shadow-sm"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitSubtask();
                  }}
                >
                  <input
                    ref={inputRef}
                    value={subName}
                    onChange={(event) => setSubName(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        setAdding(false);
                        setSubName("");
                      }
                    }}
                    placeholder="하위 업무명"
                    disabled={saving}
                    className="h-7 min-w-0 flex-1 bg-transparent px-1 text-xs outline-none placeholder:text-muted-foreground"
                  />
                  <button
                    type="submit"
                    disabled={saving}
                    className="inline-flex h-6 items-center rounded px-1.5 text-[10px] font-medium text-primary hover:bg-primary/10 disabled:opacity-50"
                  >
                    {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : "추가"}
                  </button>
                </form>
              ) : (
                <button
                  type="button"
                  onClick={() => setAdding(true)}
                  className="mb-1 inline-flex h-7 min-w-0 flex-1 items-center gap-1 rounded-md border border-dashed border-muted-foreground/30 bg-card/60 px-2 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/5 hover:text-foreground"
                  aria-label={`${task.task_id} 하위 업무 추가`}
                >
                  <Plus className="h-3.5 w-3.5" />
                  하위 추가
                </button>
              )}
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
