"use client";

import { useMemo, useState } from "react";
import { Lock } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { cn, STATUS_META } from "@/lib/utils";
import type { Task } from "@/types";

interface TaskListViewProps {
  tasks: Task[];
  onEdit: (task: Task) => void;
}

type SortKey =
  | "task_id"
  | "task_name"
  | "status"
  | "assignee_name"
  | "dept_name"
  | "start_date"
  | "due_date"
  | "progress"
  | "issues";

type SortDirection = "asc" | "desc";

function formatDate(value?: string | null) {
  return value || "-";
}

function compareText(a?: string | null, b?: string | null) {
  return (a || "").localeCompare(b || "", "ko");
}

function compareDate(a?: string | null, b?: string | null) {
  const left = a ? new Date(`${a}T00:00:00`).getTime() : Number.MAX_SAFE_INTEGER;
  const right = b ? new Date(`${b}T00:00:00`).getTime() : Number.MAX_SAFE_INTEGER;
  return left - right;
}

export function TaskListView({ tasks, onEdit }: TaskListViewProps) {
  const [sortKey, setSortKey] = useState<SortKey>("due_date");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");

  const sortedTasks = useMemo(() => {
    const parents = tasks.filter((task) => !task.parent_task_id);
    const children = tasks.filter((task) => task.parent_task_id);
    const compare = (left: Task, right: Task) => {
      let result = 0;
      switch (sortKey) {
        case "task_id":
          result = compareText(left.task_id, right.task_id);
          break;
        case "task_name":
          result = compareText(left.task_name, right.task_name);
          break;
        case "status":
          result = compareText(left.status, right.status);
          break;
        case "assignee_name":
          result = compareText(left.assignee_name, right.assignee_name);
          break;
        case "dept_name":
          result = compareText(left.dept_name, right.dept_name);
          break;
        case "start_date":
          result = compareDate(left.start_date, right.start_date);
          break;
        case "due_date":
          result = compareDate(left.due_date, right.due_date);
          break;
        case "progress":
          result = left.progress - right.progress;
          break;
        case "issues":
          result = compareText(left.issues, right.issues);
          break;
      }
      return sortDirection === "asc" ? result : -result;
    };
    parents.sort(compare);
    const rows: Task[] = [];
    for (const parent of parents) {
      rows.push(parent);
      rows.push(
        ...children
          .filter((child) => child.parent_task_id === parent.task_id)
          .sort((left, right) => left.task_id.localeCompare(right.task_id, "ko")),
      );
    }
    const parentIds = new Set(parents.map((task) => task.task_id));
    rows.push(
      ...children
        .filter((child) => child.parent_task_id && !parentIds.has(child.parent_task_id))
        .sort(compare),
    );
    return rows;
  }, [tasks, sortDirection, sortKey]);

  function changeSort(nextKey: SortKey) {
    if (sortKey === nextKey) {
      setSortDirection((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(nextKey);
    setSortDirection(nextKey === "progress" ? "desc" : "asc");
  }

  function sortMark(key: SortKey) {
    if (sortKey !== key) return "↕";
    return sortDirection === "asc" ? "↑" : "↓";
  }

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
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr className="border-b">
              <SortableHeader label="업무번호" sortKey="task_id" activeKey={sortKey} mark={sortMark("task_id")} onClick={changeSort} />
              <SortableHeader label="업무명" sortKey="task_name" activeKey={sortKey} mark={sortMark("task_name")} onClick={changeSort} />
              <SortableHeader label="상태" sortKey="status" activeKey={sortKey} mark={sortMark("status")} onClick={changeSort} />
              <SortableHeader label="담당자" sortKey="assignee_name" activeKey={sortKey} mark={sortMark("assignee_name")} onClick={changeSort} />
              <SortableHeader label="부서" sortKey="dept_name" activeKey={sortKey} mark={sortMark("dept_name")} onClick={changeSort} />
              <SortableHeader label="시작일" sortKey="start_date" activeKey={sortKey} mark={sortMark("start_date")} onClick={changeSort} />
              <SortableHeader label="종료일" sortKey="due_date" activeKey={sortKey} mark={sortMark("due_date")} onClick={changeSort} />
              <SortableHeader label="진행률" sortKey="progress" activeKey={sortKey} mark={sortMark("progress")} onClick={changeSort} />
              <SortableHeader label="이슈" sortKey="issues" activeKey={sortKey} mark={sortMark("issues")} onClick={changeSort} />
            </tr>
          </thead>
          <tbody>
            {sortedTasks.map((task) => {
              const meta = STATUS_META[task.status];
              return (
                <tr
                  key={task.task_id}
                  className="cursor-pointer border-b transition hover:bg-muted/30"
                  onClick={() => onEdit(task)}
                >
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                    {task.task_id}
                  </td>
                  <td className="min-w-[220px] px-4 py-3">
                    <div className={cn("flex items-center gap-2", task.parent_task_id && "pl-6")}>
                      <span className="truncate font-medium">
                        {task.parent_task_id ? `ㄴ ${task.task_name}` : task.task_name}
                      </span>
                      {(task.child_count ?? 0) > 0 ? (
                        <span className="shrink-0 text-[10px] text-muted-foreground">하위 {task.child_count}</span>
                      ) : null}
                      {!task.can_edit ? <Lock className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : null}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className={cn("inline-flex rounded-full px-2 py-1 text-xs ring-1", meta.chip)}>
                      {task.status}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">{task.assignee_name ?? "-"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{task.dept_name ?? "-"}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">
                    {formatDate(task.start_date)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{formatDate(task.due_date)}</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
                        <div className={cn("h-full rounded-full", meta.bar)} style={{ width: `${task.progress}%` }} />
                      </div>
                      <span className="text-xs font-medium">{task.progress}%</span>
                    </div>
                  </td>
                  <td className="max-w-[240px] px-4 py-3 text-muted-foreground">
                    <span className="block truncate">{task.issues?.trim() || "-"}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function SortableHeader({
  label,
  sortKey,
  activeKey,
  mark,
  onClick,
}: {
  label: string;
  sortKey: SortKey;
  activeKey: SortKey;
  mark: string;
  onClick: (key: SortKey) => void;
}) {
  const active = activeKey === sortKey;
  return (
    <th className="whitespace-nowrap px-4 py-3 text-left font-medium">
      <button
        type="button"
        onClick={() => onClick(sortKey)}
        className={cn(
          "inline-flex items-center gap-1 transition hover:text-foreground",
          active && "text-foreground",
        )}
      >
        <span>{label}</span>
        <span className="text-[10px]">{mark}</span>
      </button>
    </th>
  );
}
