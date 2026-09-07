"use client";

import { useEffect, useMemo, useState } from "react";
import { Building2, CornerDownRight, Loader2, Pencil, Plus, Trash2, Users } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import type { AdminDepartment } from "@/types";

const ROOT = "root";

function flattenOrgTree(departments: AdminDepartment[]): AdminDepartment[] {
  const children = new Map<number | null, AdminDepartment[]>();
  for (const dept of departments) {
    const siblings = children.get(dept.parent_dept_id) ?? [];
    siblings.push(dept);
    children.set(dept.parent_dept_id, siblings);
  }
  for (const siblings of children.values()) {
    siblings.sort((a, b) => a.dept_id - b.dept_id);
  }

  const ordered: AdminDepartment[] = [];
  const seen = new Set<number>();

  function walk(parentId: number | null) {
    for (const child of children.get(parentId) ?? []) {
      if (seen.has(child.dept_id)) continue;
      seen.add(child.dept_id);
      ordered.push(child);
      walk(child.dept_id);
    }
  }

  walk(null);
  for (const dept of departments) {
    if (!seen.has(dept.dept_id)) ordered.push(dept);
  }
  return ordered;
}

interface DepartmentManagerProps {
  departments: AdminDepartment[];
  onChanged: () => Promise<void>;
}

export function DepartmentManager({ departments, onChanged }: DepartmentManagerProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<AdminDepartment | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const tree = useMemo(() => flattenOrgTree(departments), [departments]);

  function openCreate() {
    setEditing(null);
    setDialogOpen(true);
  }

  function openEdit(dept: AdminDepartment) {
    setEditing(dept);
    setDialogOpen(true);
  }

  async function handleDelete(dept: AdminDepartment) {
    setDeleting(dept.dept_id);
    try {
      await adminApi.deleteDepartment(dept.dept_id);
      toast.success(`${dept.dept_name} 부서를 삭제했습니다.`);
      await onChanged();
    } catch (error) {
      toast.error(apiErrorMessage(error, "삭제에 실패했습니다."));
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          상위 부서를 지정하면 조직장의 권한 범위가 하위 부서까지 자동으로 확장됩니다.
        </p>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" />
          부서 등록
        </Button>
      </div>

      <Card>
        <CardContent className="divide-y p-0">
          {tree.map((dept) => (
            <div
              key={dept.dept_id}
              className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-muted/30"
              style={{ paddingLeft: `${16 + dept.depth * 24}px` }}
            >
              {dept.depth > 0 ? (
                <CornerDownRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              ) : (
                <Building2 className="h-4 w-4 shrink-0 text-primary" />
              )}

              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{dept.dept_name}</p>
                <p className="text-[11px] text-muted-foreground">
                  ID {dept.dept_id}
                  {dept.parent_dept_name ? ` · 상위 ${dept.parent_dept_name}` : " · 최상위 조직"}
                </p>
              </div>

              <div className="flex items-center gap-1.5">
                <Badge variant="muted">
                  <Users className="h-3 w-3" />
                  {dept.user_count}명
                </Badge>
                <Badge variant="secondary">업무 {dept.task_count}건</Badge>
                {dept.child_count ? (
                  <Badge variant="outline">하위 {dept.child_count}</Badge>
                ) : null}
              </div>

              <div className="flex gap-1">
                <Button variant="ghost" size="sm" onClick={() => openEdit(dept)} title="부서 수정">
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-destructive hover:text-destructive"
                  onClick={() => handleDelete(dept)}
                  disabled={deleting === dept.dept_id}
                  title="부서 삭제"
                >
                  {deleting === dept.dept_id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </div>
          ))}
          {tree.length === 0 ? (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              등록된 부서가 없습니다.
            </p>
          ) : null}
        </CardContent>
      </Card>

      <DepartmentDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        department={editing}
        departments={tree}
        onSaved={onChanged}
      />
    </div>
  );
}

function DepartmentDialog({
  open,
  onOpenChange,
  department,
  departments,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  department: AdminDepartment | null;
  departments: AdminDepartment[];
  onSaved: () => Promise<void>;
}) {
  const [name, setName] = useState("");
  const [parent, setParent] = useState(ROOT);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName(department?.dept_name ?? "");
    setParent(department?.parent_dept_id ? String(department.parent_dept_id) : ROOT);
  }, [open, department]);

  // 자기 자신과 하위 부서는 상위 부서로 선택할 수 없다.
  const parentOptions = departments.filter((candidate) => {
    if (!department) return true;
    if (candidate.dept_id === department.dept_id) return false;
    let cursor: AdminDepartment | undefined = candidate;
    let guard = 0;
    while (cursor?.parent_dept_id && guard < 20) {
      if (cursor.parent_dept_id === department.dept_id) return false;
      cursor = departments.find((d) => d.dept_id === cursor?.parent_dept_id);
      guard += 1;
    }
    return true;
  });

  async function handleSave() {
    if (!name.trim()) {
      toast.error("부서명을 입력하세요.");
      return;
    }
    setSaving(true);
    try {
      const parentId = parent === ROOT ? null : Number(parent);
      if (department) {
        await adminApi.updateDepartment(department.dept_id, {
          dept_name: name.trim(),
          parent_dept_id: parentId,
        });
        toast.success("부서 정보를 수정했습니다.");
      } else {
        await adminApi.createDepartment({ dept_name: name.trim(), parent_dept_id: parentId });
        toast.success("부서를 등록했습니다.");
      }
      onOpenChange(false);
      await onSaved();
    } catch (error) {
      toast.error(apiErrorMessage(error, "저장에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{department ? "부서 수정" : "부서 등록"}</DialogTitle>
          <DialogDescription>
            조직도는 상위·하위 구조로 관리되며 권한 범위 계산에 그대로 사용됩니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          <div className="space-y-1.5">
            <Label htmlFor="dept_name">부서명 *</Label>
            <Input
              id="dept_name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 프로덕트디자인팀"
            />
          </div>
          <div className="space-y-1.5">
            <Label>상위 부서</Label>
            <Select value={parent} onValueChange={setParent}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ROOT}>없음 (최상위 조직)</SelectItem>
                {parentOptions.map((dept) => (
                  <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                    {"　".repeat(dept.depth)}
                    {dept.dept_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            저장
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
