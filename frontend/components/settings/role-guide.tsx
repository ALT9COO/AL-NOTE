"use client";

import { useState } from "react";
import { Crown, Loader2, ShieldCheck, UserRound } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { adminApi, apiErrorMessage } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/auth-context";
import { cn, initials } from "@/lib/utils";
import type { AdminUser, RoleLevel } from "@/types";

const ROLE_CARDS: {
  role: RoleLevel;
  icon: typeof Crown;
  accent: string;
  summary: string;
  permissions: string[];
}[] = [
  {
    role: "ADMIN",
    icon: Crown,
    accent: "border-blue-200 bg-blue-50/60",
    summary: "전사 데이터와 조직 설정을 모두 관리합니다.",
    permissions: [
      "전 부서 업무 조회 및 수정",
      "전사 AI 경영 리포트 열람",
      "사용자 등록 · 삭제 · 비밀번호 초기화",
      "조직(부서) 등록 · 수정 · 삭제",
      "구성원 권한 등급 변경",
    ],
  },
  {
    role: "LEADER",
    icon: ShieldCheck,
    accent: "border-amber-200 bg-amber-50/60",
    summary: "소속 조직과 하위 조직의 모든 권한을 갖습니다.",
    permissions: [
      "소속 · 하위 조직 업무 전체 조회 및 수정",
      "조직 범위 AI 리포트 열람",
      "회의 안건을 조직 업무에 일괄 반영",
      "설정(사용자 · 조직 관리) 접근 불가",
    ],
  },
  {
    role: "MEMBER",
    icon: UserRound,
    accent: "border-slate-200 bg-slate-50/60",
    summary: "본인에게 배정된 업무만 볼 수 있습니다.",
    permissions: [
      "본인 담당 업무만 조회 · 수정 · 상태 변경",
      "본인 범위 AI 리포트 열람",
      "다른 구성원 업무는 보이지 않음",
      "설정(사용자 · 조직 관리) 접근 불가",
    ],
  },
];

interface RoleGuideProps {
  users: AdminUser[];
  onChanged: () => Promise<void>;
}

export function RoleGuide({ users, onChanged }: RoleGuideProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  async function changeRole(user: AdminUser, role: RoleLevel) {
    setBusyId(user.user_id);
    try {
      await adminApi.updateUser(user.user_id, { role_level: role });
      toast.success(`${user.user_name} → ${ROLE_LABELS[role]} 권한으로 변경했습니다.`);
      await onChanged();
    } catch (error) {
      toast.error(apiErrorMessage(error, "권한 변경에 실패했습니다."));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {ROLE_CARDS.map((card) => {
        const Icon = card.icon;
        const members = users.filter((user) => user.role_level === card.role);
        return (
          <Card key={card.role} className={cn("border", card.accent)}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-primary" />
                  {ROLE_LABELS[card.role]}
                </span>
                <span className="text-xs font-normal text-muted-foreground">
                  {members.length}명
                </span>
              </CardTitle>
              <p className="text-xs text-muted-foreground">{card.summary}</p>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1.5">
                {card.permissions.map((permission) => (
                  <li key={permission} className="flex gap-2 text-xs text-muted-foreground">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-primary/60" />
                    {permission}
                  </li>
                ))}
              </ul>

              <div className="space-y-1.5 border-t pt-3">
                {members.map((member) => (
                  <div
                    key={member.user_id}
                    className="flex items-center gap-2 rounded-lg bg-background/70 p-1.5"
                  >
                    <Avatar className="h-7 w-7">
                      <AvatarFallback className="text-[9px]">
                        {initials(member.user_name)}
                      </AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-xs font-medium">
                        {member.user_name}
                        {member.is_self ? (
                          <span className="ml-1 text-[10px] text-primary">(나)</span>
                        ) : null}
                      </p>
                      <p className="truncate text-[10px] text-muted-foreground">
                        {[member.job_title, member.dept_name].filter(Boolean).join(" · ") || "부서 미지정"}
                      </p>
                    </div>
                    {busyId === member.user_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                    ) : (
                      <Select
                        value={member.role_level}
                        onValueChange={(value) => changeRole(member, value as RoleLevel)}
                        disabled={member.is_self}
                      >
                        <SelectTrigger className="h-7 w-[104px] text-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLE_CARDS.map((option) => (
                            <SelectItem key={option.role} value={option.role}>
                              {ROLE_LABELS[option.role]}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </div>
                ))}
                {members.length === 0 ? (
                  <p className="py-2 text-center text-[11px] text-muted-foreground">
                    해당 권한의 구성원이 없습니다.
                  </p>
                ) : null}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
