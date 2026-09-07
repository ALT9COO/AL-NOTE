"use client";

import { useEffect, useState, type ReactNode } from "react";
import {
  CalendarRange,
  FileText,
  Gauge,
  ListTree,
  Loader2,
  MessageSquare,
  Plus,
  Send,
  Shield,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import { toast } from "sonner";

import { SubjectPicker, toSubjectPayload } from "@/components/common/subject-picker";

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
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { apiErrorMessage, taskApi } from "@/lib/api";
import { cn, formatDateTime, formatRelativeTime, STATUS_META, STATUSES } from "@/lib/utils";
import type { Collaborator, Department, Task, TaskActivity, TaskStatus, User } from "@/types";

interface TaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  task: Task | null;
  users: User[];
  departments: Department[];
  defaultDeptId?: number | null;
  onSaved: () => void;
}

interface FormState {
  task_name: string;
  description: string;
  status: TaskStatus;
  progress: number;
  assigned_to: string;
  dept_id: string;
  start_date: string;
  due_date: string;
}

const EMPTY: FormState = {
  task_name: "",
  description: "",
  status: "할당",
  progress: 0,
  assigned_to: "",
  dept_id: "",
  start_date: new Date().toISOString().slice(0, 10),
  due_date: "",
};

function activityLabel(item: TaskActivity) {
  if (item.kind === "comment") return "이슈";
  if (item.kind === "progress") return "진척";
  if (item.kind === "status") return "상태";
  if (item.kind === "create") return "등록";
  if (item.kind === "delete") return "삭제";
  if (item.kind === "restore") return "복원";
  return item.kind;
}

function DialogSection({
  icon: Icon,
  title,
  hint,
  children,
}: {
  icon: LucideIcon;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border bg-background shadow-sm">
      <header className="flex items-start gap-2 border-b bg-muted/50 px-3.5 py-2.5">
        <Icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold leading-none">{title}</h3>
          {hint ? <p className="mt-1.5 text-[11px] leading-snug text-muted-foreground">{hint}</p> : null}
        </div>
      </header>
      <div className="space-y-3 p-3.5">{children}</div>
    </section>
  );
}

export function TaskDialog({
  open,
  onOpenChange,
  task,
  users,
  departments,
  defaultDeptId,
  onSaved,
}: TaskDialogProps) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [viewers, setViewers] = useState<Collaborator[]>([]);
  const [activities, setActivities] = useState<TaskActivity[]>([]);
  const [comment, setComment] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [commenting, setCommenting] = useState(false);
  const [detail, setDetail] = useState<Task | null>(task);
  const [subName, setSubName] = useState("");
  const [subAssignee, setSubAssignee] = useState("");
  const [addingSub, setAddingSub] = useState(false);

  function applyDetail(full: Task) {
    setDetail(full);
    setForm({
      task_name: full.task_name,
      description: full.description ?? "",
      status: full.status,
      progress: full.progress,
      assigned_to: full.assigned_to ?? "",
      dept_id: full.dept_id ? String(full.dept_id) : "",
      start_date: full.start_date ?? "",
      due_date: full.due_date ?? "",
    });
    setCollaborators(full.collaborators ?? []);
    setViewers(full.viewers ?? []);
    setActivities(full.activities ?? []);
  }

  useEffect(() => {
    if (!open) return;
    setComment("");
    setSubName("");
    setSubAssignee("");
    setDetail(task);
    setForm(
      task
        ? {
            task_name: task.task_name,
            description: task.description ?? "",
            status: task.status,
            progress: task.progress,
            assigned_to: task.assigned_to ?? "",
            dept_id: task.dept_id ? String(task.dept_id) : "",
            start_date: task.start_date ?? "",
            due_date: task.due_date ?? "",
          }
        : { ...EMPTY, dept_id: defaultDeptId ? String(defaultDeptId) : "" },
    );
    setCollaborators(task?.collaborators ?? []);
    setViewers(task?.viewers ?? []);
    setActivities(task?.activities ?? []);
    if (!task?.task_id) return;
    void taskApi
      .get(task.task_id)
      .then(applyDetail)
      .catch((error) => toast.error(apiErrorMessage(error, "업무 상세를 불러오지 못했습니다.")));
  }, [open, task, defaultDeptId]);

  const current = detail ?? task;
  const readOnly = Boolean(current && !current.can_edit);
  const progressLocked = Boolean(current?.progress_locked || (current?.children?.length ?? 0) > 0);
  const isChild = Boolean(current?.parent_task_id);
  const childItems = current?.children ?? [];

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function applyAssignee(userId: string) {
    const picked = users.find((item) => item.user_id === userId);
    setForm((prev) => ({
      ...prev,
      assigned_to: userId,
      dept_id: picked?.dept_id ? String(picked.dept_id) : prev.dept_id,
    }));
    setCollaborators((prev) => prev.filter((item) => item.user_id !== userId));
    setViewers((prev) => prev.filter((item) => item.user_id !== userId));
  }

  async function handleSave() {
    if (!form.task_name.trim()) {
      toast.error("업무명을 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        task_name: form.task_name.trim(),
        description: form.description,
        status: form.status,
        progress: progressLocked ? current?.progress ?? Number(form.progress) : Number(form.progress),
        assigned_to: form.assigned_to || null,
        dept_id: form.dept_id ? Number(form.dept_id) : null,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        collaborators: toSubjectPayload(collaborators),
        viewers: toSubjectPayload(viewers),
      };
      if (current) {
        const updated = await taskApi.update(current.task_id, payload);
        applyDetail(updated);
        toast.success(`${current.task_id} 업무를 수정했습니다.`);
      } else {
        const created = await taskApi.create(payload);
        toast.success(`${created.task_id} 업무를 등록했습니다.`);
        onOpenChange(false);
      }
      onSaved();
    } catch (error) {
      toast.error(apiErrorMessage(error, "저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete() {
    if (!current) return;
    const childCount = current.child_count ?? current.children?.length ?? 0;
    const message = childCount
      ? `${current.task_id}와 하위 업무 ${childCount}건을 함께 삭제할까요? 설정에서 1년 이내 복원할 수 있습니다.`
      : `${current.task_id} 업무를 삭제할까요? 설정에서 1년 이내 복원할 수 있습니다.`;
    if (!window.confirm(message)) return;
    setDeleting(true);
    try {
      await taskApi.remove(current.task_id);
      toast.success(
        childCount
          ? `${current.task_id}와 하위 업무를 삭제했습니다.`
          : `${current.task_id} 업무를 삭제했습니다. 설정에서 1년 이내 복원할 수 있습니다.`,
      );
      onOpenChange(false);
      onSaved();
    } catch (error) {
      toast.error(apiErrorMessage(error, "삭제에 실패했습니다."));
    } finally {
      setDeleting(false);
    }
  }

  async function handleComment() {
    if (!current || !comment.trim()) return;
    setCommenting(true);
    try {
      const updated = await taskApi.addComment(current.task_id, comment.trim());
      applyDetail(updated);
      setComment("");
      onSaved();
    } catch (error) {
      toast.error(apiErrorMessage(error, "댓글을 등록하지 못했습니다."));
    } finally {
      setCommenting(false);
    }
  }

  async function handleAddSubtask() {
    if (!current || !subName.trim()) {
      toast.error("하위 업무명을 입력하세요.");
      return;
    }
    setAddingSub(true);
    try {
      await taskApi.create({
        task_name: subName.trim(),
        assigned_to: subAssignee || current.assigned_to,
        dept_id: current.dept_id,
        start_date: current.start_date,
        due_date: current.due_date,
        parent_task_id: current.task_id,
      });
      const parent = await taskApi.get(current.task_id);
      applyDetail(parent);
      setSubName("");
      setSubAssignee("");
      toast.success("하위 업무를 추가했습니다.");
      onSaved();
    } catch (error) {
      toast.error(apiErrorMessage(error, "하위 업무를 추가하지 못했습니다."));
    } finally {
      setAddingSub(false);
    }
  }

  async function openLinkedTask(taskId: string) {
    try {
      applyDetail(await taskApi.get(taskId));
    } catch (error) {
      toast.error(apiErrorMessage(error, "업무를 열지 못했습니다."));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto bg-muted/40">
        <DialogHeader>
          <DialogTitle>{current ? `${current.task_id} 업무 상세` : "새 업무 등록"}</DialogTitle>
          <DialogDescription>
            {readOnly
              ? "조회 권한만 있는 업무입니다. 이슈 댓글은 남길 수 있습니다."
              : isChild
                ? `상위 업무 ${current?.parent_task_id}의 하위 업무입니다.`
                : progressLocked
                  ? "하위 업무가 있으면 상위 진행률은 자동 계산되고, 상태 변경 시 하위도 같이 맞춰집니다."
                  : "카드를 클릭하면 세부 내용과 진척 히스토리를 확인할 수 있습니다."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 lg:grid-cols-[1.15fr_0.85fr]">
          <div className="grid gap-3">
            {isChild && current?.parent_task_id ? (
              <button
                type="button"
                className="rounded-xl border bg-background px-3.5 py-2.5 text-left text-xs font-medium shadow-sm hover:bg-muted"
                onClick={() => void openLinkedTask(current.parent_task_id!)}
              >
                상위 업무 {current.parent_task_id} 열기
              </button>
            ) : null}

            <DialogSection icon={FileText} title="업무 내용" hint="업무명과 세부 내용을 입력합니다.">
              <div className="space-y-1.5">
                <Label htmlFor="task_name">업무명 *</Label>
                <Input
                  id="task_name"
                  value={form.task_name}
                  onChange={(e) => set("task_name", e.target.value)}
                  disabled={readOnly}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="description">세부 내용</Label>
                <Textarea
                  id="description"
                  rows={4}
                  value={form.description}
                  onChange={(e) => set("description", e.target.value)}
                  disabled={readOnly}
                  placeholder="업무 배경, 범위, 산출물을 적어 주세요."
                />
              </div>
            </DialogSection>

            <DialogSection icon={CalendarRange} title="담당 · 일정" hint="담당자, 상태, 진행률, 기간을 관리합니다.">
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>담당자</Label>
                  <Select value={form.assigned_to || undefined} onValueChange={applyAssignee} disabled={readOnly}>
                    <SelectTrigger>
                      <SelectValue placeholder="담당자 선택" />
                    </SelectTrigger>
                    <SelectContent>
                      {users.map((user) => (
                        <SelectItem key={user.user_id} value={user.user_id}>
                          {user.user_name} · {user.dept_name ?? "부서 없음"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label>부서</Label>
                  <Select value={form.dept_id || undefined} onValueChange={(value) => set("dept_id", value)} disabled={readOnly}>
                    <SelectTrigger>
                      <SelectValue placeholder="담당자 선택 시 자동 연동" />
                    </SelectTrigger>
                    <SelectContent>
                      {departments.map((dept) => (
                        <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                          {dept.dept_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[11px] text-muted-foreground">담당자를 고르면 소속 부서가 자동으로 채워집니다.</p>
                </div>

                <div className="space-y-1.5">
                  <Label>상태</Label>
                  <Select
                    value={form.status}
                    onValueChange={(value) => set("status", value as TaskStatus)}
                    disabled={readOnly}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {STATUSES.map((status) => (
                        <SelectItem key={status} value={status}>
                          {status}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {progressLocked ? (
                    <p className="text-[11px] text-muted-foreground">
                      상태를 바꾸면 하위 업무도 같은 상태로 맞춰집니다.
                    </p>
                  ) : null}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="progress">
                    진행률 ({form.progress}%){progressLocked ? " · 하위 평균" : ""}
                  </Label>
                  <Progress value={form.progress} indicatorClassName={STATUS_META[form.status].bar} className="h-2" />
                  <input
                    id="progress"
                    type="range"
                    min={0}
                    max={100}
                    step={5}
                    value={form.progress}
                    onChange={(e) => set("progress", Number(e.target.value))}
                    disabled={readOnly || progressLocked}
                    className="h-6 w-full accent-blue-600"
                  />
                  {progressLocked ? (
                    <p className="text-[11px] text-muted-foreground">
                      하위 업무 진행률 평균으로 자동 계산됩니다.
                    </p>
                  ) : null}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="start_date">시작일</Label>
                  <Input
                    id="start_date"
                    type="date"
                    value={form.start_date}
                    onChange={(e) => set("start_date", e.target.value)}
                    disabled={readOnly}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="due_date">마감일</Label>
                  <Input
                    id="due_date"
                    type="date"
                    value={form.due_date}
                    onChange={(e) => set("due_date", e.target.value)}
                    disabled={readOnly}
                  />
                </div>
              </div>
            </DialogSection>

            {current && !isChild ? (
              <DialogSection
                icon={ListTree}
                title="하위 업무"
                hint="하위 진행률 평균이 상위 진행률이 됩니다."
              >
                {childItems.length === 0 ? (
                  <p className="text-[11px] text-muted-foreground">
                    아직 하위 업무가 없습니다. 추가하면 상위 상태·진행률을 따르고, 이후 상위 변경 시 같이 맞춰집니다.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {childItems.map((child) => {
                      const meta = STATUS_META[child.status];
                      return (
                        <li key={child.task_id}>
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 rounded-lg border bg-muted/30 px-2.5 py-2 text-left hover:bg-muted/60"
                            onClick={() => void openLinkedTask(child.task_id)}
                          >
                            <span className="font-mono text-[10px] text-muted-foreground">{child.task_id}</span>
                            <span className="min-w-0 flex-1 truncate text-xs font-medium">{child.task_name}</span>
                            <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] ring-1", meta.chip)}>
                              {child.status}
                            </span>
                            <span className="text-[10px] text-muted-foreground">{child.progress}%</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
                {!readOnly ? (
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <Input
                      value={subName}
                      onChange={(e) => setSubName(e.target.value)}
                      placeholder="하위 업무명"
                      className="h-9 text-xs"
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          void handleAddSubtask();
                        }
                      }}
                    />
                    <Select
                      value={subAssignee || form.assigned_to || undefined}
                      onValueChange={setSubAssignee}
                    >
                      <SelectTrigger className="h-9 sm:w-[160px]">
                        <SelectValue placeholder="담당자" />
                      </SelectTrigger>
                      <SelectContent>
                        {users.map((user) => (
                          <SelectItem key={user.user_id} value={user.user_id}>
                            {user.user_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      type="button"
                      size="sm"
                      className="h-9"
                      onClick={() => void handleAddSubtask()}
                      disabled={addingSub || !subName.trim()}
                    >
                      {addingSub ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                      추가
                    </Button>
                  </div>
                ) : null}
              </DialogSection>
            ) : null}

            <DialogSection icon={Shield} title="권한" hint="함께 일할 사람과 누가 이 업무를 볼 수 있는지 정합니다.">
              <SubjectPicker
                label="공동작업자"
                hint="함께 일할 사람 또는 조직입니다. 기본 열람일 때는 이들에게도 업무가 보입니다."
                emptyLabel="아직 없습니다."
                items={collaborators}
                onChange={setCollaborators}
                users={users}
                departments={departments}
                assignedTo={form.assigned_to}
                disabled={readOnly}
              />
              <div className="border-t pt-3">
                <SubjectPicker
                  label="열람 정책"
                  hint="비워 두면 기본 정책입니다. 사람이나 조직을 지정하면 담당자와 그 대상만 볼 수 있습니다."
                  emptyLabel="기본 정책 사용 중"
                  items={viewers}
                  onChange={setViewers}
                  users={users}
                  departments={departments}
                  assignedTo={form.assigned_to}
                  disabled={readOnly}
                />
              </div>
            </DialogSection>
          </div>

          <div className="flex min-h-[280px] flex-col overflow-hidden rounded-xl border bg-background shadow-sm">
            <div className="flex items-center gap-2 border-b bg-muted/50 px-3.5 py-2.5 text-sm font-semibold">
              <MessageSquare className="h-4 w-4 text-primary" />
              이슈 · 진척 히스토리
            </div>
            <div className="scrollbar-thin flex-1 space-y-3 overflow-y-auto p-3">
              {activities.length === 0 ? (
                <p className="py-8 text-center text-xs text-muted-foreground">
                  {current ? "아직 기록이 없습니다." : "저장한 뒤 댓글과 진척 이력이 쌓입니다."}
                </p>
              ) : (
                activities.map((item) => (
                  <div key={item.activity_id} className="rounded-lg border bg-background p-2.5">
                    <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1.5">
                        {item.kind === "progress" || item.kind === "status" ? (
                          <Gauge className="h-3 w-3" />
                        ) : (
                          <MessageSquare className="h-3 w-3" />
                        )}
                        <span className="font-medium text-foreground">{activityLabel(item)}</span>
                        <span>{item.user_name ?? "시스템"}</span>
                      </span>
                      <span title={formatDateTime(item.created_at)}>{formatRelativeTime(item.created_at)}</span>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed">{item.body}</p>
                    {item.kind === "comment" && item.progress != null ? (
                      <p className="mt-1 text-[10px] text-muted-foreground">
                        당시 진행률 {item.progress}%
                        {item.status ? ` · ${item.status}` : ""}
                      </p>
                    ) : null}
                  </div>
                ))
              )}
            </div>
            {current ? (
              <div className="border-t p-3">
                <div className="flex gap-2">
                  <Textarea
                    rows={2}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="최신 이슈를 댓글로 남기면 카드에도 표시됩니다."
                    className="min-h-[64px] text-xs"
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
                        event.preventDefault();
                        void handleComment();
                      }
                    }}
                  />
                  <Button
                    size="icon"
                    className="h-auto w-10 shrink-0"
                    onClick={() => void handleComment()}
                    disabled={commenting || !comment.trim()}
                  >
                    {commenting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
                <p className="mt-1 text-[10px] text-muted-foreground">Ctrl+Enter로 등록 · 시간이 기록됩니다</p>
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter className="border-t pt-4 sm:justify-between">
          {current && !readOnly ? (
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              삭제
            </Button>
          ) : (
            <span />
          )}
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              닫기
            </Button>
            <Button onClick={handleSave} disabled={saving || readOnly}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              저장
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
