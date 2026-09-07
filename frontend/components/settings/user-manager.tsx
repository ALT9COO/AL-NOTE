"use client";

import { useEffect, useMemo, useState } from "react";
import { KeyRound, Loader2, Search, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/auth-context";
import { initials } from "@/lib/utils";
import type { AdminDepartment, AdminUser, RoleLevel } from "@/types";

const ROLES: RoleLevel[] = ["ADMIN", "LEADER", "MEMBER"];

const NO_DEPT = "none";

interface UserManagerProps {
  users: AdminUser[];
  departments: AdminDepartment[];
  onChanged: () => Promise<void>;
}

export function UserManager({ users, departments, onChanged }: UserManagerProps) {
  const [keyword, setKeyword] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [passwordTarget, setPasswordTarget] = useState<AdminUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const query = keyword.trim().toLowerCase();
    if (!query) return users;
    return users.filter(
      (user) =>
        user.user_name.toLowerCase().includes(query) ||
        user.user_id.toLowerCase().includes(query) ||
        (user.job_title ?? "").toLowerCase().includes(query) ||
        (user.dept_name ?? "").toLowerCase().includes(query),
    );
  }, [users, keyword]);

  async function patch(user: AdminUser, payload: Parameters<typeof adminApi.updateUser>[1]) {
    setBusyId(user.user_id);
    try {
      await adminApi.updateUser(user.user_id, payload);
      await onChanged();
      toast.success(`${user.user_name} 계정을 수정했습니다.`);
    } catch (error) {
      toast.error(apiErrorMessage(error, "수정에 실패했습니다."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-xs">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="이름 · 아이디 · 직책 · 부서 검색"
            className="pl-8"
          />
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="h-4 w-4" />
          사용자 등록
        </Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-3 font-medium">사용자</th>
                  <th className="px-4 py-3 font-medium">소속 부서</th>
                  <th className="px-4 py-3 font-medium">직책</th>
                  <th className="px-4 py-3 font-medium">권한 등급</th>
                  <th className="px-4 py-3 font-medium">담당 업무</th>
                  <th className="px-4 py-3 text-right font-medium">관리</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((user) => (
                  <tr key={user.user_id} className="border-b last:border-0 hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <Avatar className="h-8 w-8">
                          <AvatarFallback>{initials(user.user_name)}</AvatarFallback>
                        </Avatar>
                        <div>
                          <p className="font-medium leading-tight">
                            {user.user_name}
                            {user.is_self ? (
                              <span className="ml-1.5 text-[10px] text-primary">(나)</span>
                            ) : null}
                          </p>
                          <p className="font-mono text-[11px] text-muted-foreground">
                            {user.user_id}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Select
                        value={user.dept_id ? String(user.dept_id) : NO_DEPT}
                        onValueChange={(value) =>
                          patch(user, { dept_id: value === NO_DEPT ? null : Number(value) })
                        }
                        disabled={busyId === user.user_id}
                      >
                        <SelectTrigger className="h-8 w-[170px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NO_DEPT}>미지정</SelectItem>
                          {departments.map((dept) => (
                            <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                              {"　".repeat(dept.depth)}
                              {dept.dept_name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-4 py-3">
                      <JobTitleCell
                        user={user}
                        disabled={busyId === user.user_id}
                        onSave={(job_title) => patch(user, { job_title })}
                      />
                    </td>
                    <td className="px-4 py-3">
                      <Select
                        value={user.role_level}
                        onValueChange={(value) => patch(user, { role_level: value as RoleLevel })}
                        disabled={user.is_self || busyId === user.user_id}
                      >
                        <SelectTrigger className="h-8 w-[120px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLES.map((role) => (
                            <SelectItem key={role} value={role}>
                              {ROLE_LABELS[role]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{user.task_count}건</td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPasswordTarget(user)}
                          title="비밀번호 초기화"
                        >
                          <KeyRound className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="text-destructive hover:text-destructive"
                          disabled={user.is_self}
                          onClick={() => setDeleteTarget(user)}
                          title="사용자 삭제"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                      조건에 맞는 사용자가 없습니다.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <CreateUserDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        departments={departments}
        onCreated={onChanged}
      />
      <PasswordDialog
        user={passwordTarget}
        onClose={() => setPasswordTarget(null)}
        onDone={onChanged}
      />
      <DeleteUserDialog
        user={deleteTarget}
        users={users}
        onClose={() => setDeleteTarget(null)}
        onDone={onChanged}
      />
    </div>
  );
}

function JobTitleCell({
  user,
  disabled,
  onSave,
}: {
  user: AdminUser;
  disabled: boolean;
  onSave: (jobTitle: string) => void;
}) {
  const [value, setValue] = useState(user.job_title ?? "");

  useEffect(() => {
    setValue(user.job_title ?? "");
  }, [user.job_title]);

  return (
    <Input
      value={value}
      disabled={disabled}
      placeholder="예: 팀장"
      className="h-8 w-[128px]"
      maxLength={50}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        const next = value.trim();
        if (next !== (user.job_title ?? "").trim()) onSave(next);
      }}
    />
  );
}

function CreateUserDialog({
  open,
  onOpenChange,
  departments,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  departments: AdminDepartment[];
  onCreated: () => Promise<void>;
}) {
  const [form, setForm] = useState({
    user_id: "",
    user_name: "",
    password: "",
    job_title: "",
    role_level: "MEMBER" as RoleLevel,
    dept_id: NO_DEPT,
  });
  const [saving, setSaving] = useState(false);

  function reset() {
    setForm({
      user_id: "",
      user_name: "",
      password: "",
      job_title: "",
      role_level: "MEMBER",
      dept_id: NO_DEPT,
    });
  }

  async function handleSave() {
    if (!form.user_id.trim() || !form.user_name.trim() || form.password.length < 4) {
      toast.error("아이디 · 이름 · 비밀번호(4자 이상)를 모두 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      await adminApi.createUser({
        user_id: form.user_id.trim(),
        user_name: form.user_name.trim(),
        password: form.password,
        role_level: form.role_level,
        job_title: form.job_title.trim(),
        dept_id: form.dept_id === NO_DEPT ? null : Number(form.dept_id),
      });
      toast.success(`${form.user_name} 계정을 등록했습니다.`);
      onOpenChange(false);
      reset();
      await onCreated();
    } catch (error) {
      toast.error(apiErrorMessage(error, "등록에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>사용자 등록</DialogTitle>
          <DialogDescription>
            등록 즉시 해당 계정으로 로그인할 수 있습니다. 아이디는 영문 · 숫자 · . _ - 만 사용합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="new_user_id">아이디 *</Label>
              <Input
                id="new_user_id"
                value={form.user_id}
                onChange={(e) => setForm({ ...form, user_id: e.target.value })}
                placeholder="member3"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new_user_name">이름 *</Label>
              <Input
                id="new_user_name"
                value={form.user_name}
                onChange={(e) => setForm({ ...form, user_name: e.target.value })}
                placeholder="홍길동"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="new_password">초기 비밀번호 * (4자 이상)</Label>
            <Input
              id="new_password"
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>소속 부서</Label>
              <Select
                value={form.dept_id}
                onValueChange={(value) => setForm({ ...form, dept_id: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_DEPT}>미지정</SelectItem>
                  {departments.map((dept) => (
                    <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                      {"　".repeat(dept.depth)}
                      {dept.dept_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="new_job_title">직책</Label>
              <Input
                id="new_job_title"
                value={form.job_title}
                onChange={(e) => setForm({ ...form, job_title: e.target.value })}
                placeholder="예: 팀장 · 실장 · 사원"
                maxLength={50}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>권한 등급</Label>
            <Select
              value={form.role_level}
              onValueChange={(value) => setForm({ ...form, role_level: value as RoleLevel })}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((role) => (
                  <SelectItem key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              관리자는 전 기능, 조직장은 소속 조직 전체, 구성원은 본인 업무만 볼 수 있습니다.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            등록
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PasswordDialog({
  user,
  onClose,
  onDone,
}: {
  user: AdminUser | null;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [password, setPassword] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    if (!user || password.length < 4) {
      toast.error("4자 이상의 비밀번호를 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      await adminApi.updateUser(user.user_id, { password });
      toast.success(`${user.user_name} 계정의 비밀번호를 변경했습니다.`);
      setPassword("");
      onClose();
      await onDone();
    } catch (error) {
      toast.error(apiErrorMessage(error, "변경에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={Boolean(user)} onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>비밀번호 초기화</DialogTitle>
          <DialogDescription>
            {user?.user_name} ({user?.user_id}) 계정의 새 비밀번호를 설정합니다.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="reset_password">새 비밀번호 (4자 이상)</Label>
          <Input
            id="reset_password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            변경
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteUserDialog({
  user,
  users,
  onClose,
  onDone,
}: {
  user: AdminUser | null;
  users: AdminUser[];
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [successor, setSuccessor] = useState("");
  const [saving, setSaving] = useState(false);
  const needsReassign = (user?.task_count ?? 0) > 0;
  const candidates = users.filter((u) => u.user_id !== user?.user_id);

  async function handleDelete() {
    if (!user) return;
    if (needsReassign && !successor) {
      toast.error("담당 업무를 인수인계할 사용자를 선택하세요.");
      return;
    }
    setSaving(true);
    try {
      await adminApi.deleteUser(user.user_id, needsReassign ? successor : null);
      toast.success(`${user.user_name} 계정을 삭제했습니다.`);
      setSuccessor("");
      onClose();
      await onDone();
    } catch (error) {
      toast.error(apiErrorMessage(error, "삭제에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={Boolean(user)} onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>사용자 삭제</DialogTitle>
          <DialogDescription>
            {user?.user_name} ({user?.user_id}) 계정을 삭제합니다. 되돌릴 수 없습니다.
          </DialogDescription>
        </DialogHeader>

        {needsReassign ? (
          <div className="space-y-1.5">
            <Label>담당 업무 {user?.task_count}건 인수인계 대상 *</Label>
            <Select value={successor} onValueChange={setSuccessor}>
              <SelectTrigger>
                <SelectValue placeholder="인수인계할 사용자 선택" />
              </SelectTrigger>
              <SelectContent>
                {candidates.map((candidate) => (
                  <SelectItem key={candidate.user_id} value={candidate.user_id}>
                    {candidate.user_name} ({candidate.user_id})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">담당 중인 업무가 없어 바로 삭제됩니다.</p>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            취소
          </Button>
          <Button variant="destructive" onClick={handleDelete} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
            삭제
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
