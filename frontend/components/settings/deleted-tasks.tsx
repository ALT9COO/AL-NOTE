"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiErrorMessage, taskApi } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import type { Task } from "@/types";

export function DeletedTasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [restoringId, setRestoringId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setTasks(await taskApi.listDeleted());
    } catch (error) {
      toast.error(apiErrorMessage(error, "삭제된 업무를 불러오지 못했습니다."));
    }
  }, []);

  useEffect(() => {
    void load().finally(() => setLoading(false));
  }, [load]);

  async function handleRestore(task: Task) {
    setRestoringId(task.task_id);
    try {
      await taskApi.restore(task.task_id);
      toast.success(
        task.parent_task_id
          ? `${task.task_id} 하위 업무를 복원했습니다.`
          : `${task.task_id} 업무를 칸반 보드로 복원했습니다.`,
      );
      await load();
    } catch (error) {
      toast.error(apiErrorMessage(error, "복원에 실패했습니다."));
    } finally {
      setRestoringId(null);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Trash2 className="h-4 w-4" />
          삭제된 업무
        </CardTitle>
        <CardDescription>
          삭제한 업무 카드는 1년 동안 보관됩니다. 기간이 지나면 완전히 지워지며 복원할 수 없습니다.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tasks.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            복원할 수 있는 삭제된 업무가 없습니다.
          </p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {tasks
              .filter(
                (task) =>
                  !task.parent_task_id ||
                  !tasks.some((item) => item.task_id === task.parent_task_id),
              )
              .map((task) => (
              <li
                key={task.task_id}
                className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{task.task_name}</span>
                    <Badge variant="muted">{task.task_id}</Badge>
                    {task.parent_task_id ? <Badge variant="outline">하위 · {task.parent_task_id}</Badge> : null}
                    {(task.child_count ?? 0) > 0 ? (
                      <Badge variant="outline">하위 {task.child_count}건 포함</Badge>
                    ) : null}
                    <Badge variant="outline">{task.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {task.assignee_name ?? "담당자 없음"}
                    {task.dept_name ? ` · ${task.dept_name}` : ""}
                    {" · "}
                    삭제 {formatDateTime(task.deleted_at)}
                    {task.deleted_by_name ? ` · ${task.deleted_by_name}` : ""}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTime(task.purge_on)}까지 보관
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!task.can_edit || restoringId === task.task_id}
                  title={task.can_edit ? "칸반 보드로 복원" : "복원 권한이 없습니다"}
                  onClick={() => void handleRestore(task)}
                >
                  {restoringId === task.task_id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                  복원
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
