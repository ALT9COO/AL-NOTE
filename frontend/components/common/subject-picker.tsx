"use client";

import { Building2, UserPlus, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { Collaborator, Department, User } from "@/types";

export function toSubjectPayload(items: Collaborator[]) {
  return items.map((item) =>
    item.kind === "user"
      ? { kind: "user" as const, user_id: item.user_id ?? undefined }
      : { kind: "dept" as const, dept_id: item.dept_id ?? undefined },
  );
}

export function SubjectPicker({
  label,
  hint,
  emptyLabel,
  items,
  onChange,
  users,
  departments,
  assignedTo,
  excludeUserIds,
  disabled,
}: {
  label: string;
  hint: string;
  emptyLabel: string;
  items: Collaborator[];
  onChange: (items: Collaborator[]) => void;
  users: User[];
  departments: Department[];
  assignedTo?: string;
  excludeUserIds?: string[];
  disabled?: boolean;
}) {
  const blocked = new Set([assignedTo, ...(excludeUserIds ?? [])].filter(Boolean) as string[]);
  const people = users.filter(
    (user) =>
      !blocked.has(user.user_id) &&
      !items.some((item) => item.kind === "user" && item.user_id === user.user_id),
  );
  const orgs = departments.filter(
    (dept) => !items.some((item) => item.kind === "dept" && item.dept_id === dept.dept_id),
  );

  function addPerson(userId: string) {
    const picked = users.find((user) => user.user_id === userId);
    if (!picked) return;
    onChange([
      ...items,
      {
        kind: "user",
        user_id: picked.user_id,
        user_name: picked.user_name,
        dept_id: picked.dept_id,
        dept_name: picked.dept_name,
      },
    ]);
  }

  function addOrg(deptId: string) {
    const picked = departments.find((dept) => dept.dept_id === Number(deptId));
    if (!picked) return;
    onChange([...items, { kind: "dept", dept_id: picked.dept_id, dept_name: picked.dept_name }]);
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <p className="text-[11px] text-muted-foreground">{hint}</p>
      <div className="flex flex-wrap gap-1.5">
        {items.length === 0 ? (
          <span className="text-xs text-muted-foreground">{emptyLabel}</span>
        ) : (
          items.map((item) => (
            <Badge key={`${item.kind}-${item.user_id ?? item.dept_id}`} variant="secondary">
              {item.kind === "dept" ? <Building2 className="h-3 w-3" /> : <UserPlus className="h-3 w-3" />}
              {item.kind === "dept" ? item.dept_name : item.user_name}
              {!disabled ? (
                <button
                  type="button"
                  className="ml-0.5 rounded-full hover:bg-black/10"
                  onClick={() =>
                    onChange(
                      items.filter(
                        (entry) =>
                          !(
                            entry.kind === item.kind &&
                            entry.user_id === item.user_id &&
                            entry.dept_id === item.dept_id
                          ),
                      ),
                    )
                  }
                >
                  <X className="h-3 w-3" />
                </button>
              ) : null}
            </Badge>
          ))
        )}
      </div>
      {!disabled ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <Select key={`person-${items.length}`} onValueChange={addPerson} disabled={!people.length}>
            <SelectTrigger>
              <SelectValue placeholder="사람 추가" />
            </SelectTrigger>
            <SelectContent>
              {people.map((user) => (
                <SelectItem key={user.user_id} value={user.user_id}>
                  {user.user_name} · {user.dept_name ?? "-"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select key={`org-${items.length}`} onValueChange={addOrg} disabled={!orgs.length}>
            <SelectTrigger>
              <SelectValue placeholder="조직 추가" />
            </SelectTrigger>
            <SelectContent>
              {orgs.map((dept) => (
                <SelectItem key={dept.dept_id} value={String(dept.dept_id)}>
                  {dept.dept_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      ) : null}
    </div>
  );
}
