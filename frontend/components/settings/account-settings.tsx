"use client";

import { useState } from "react";
import { KeyRound } from "lucide-react";

import { PasswordDialog } from "@/components/layout/password-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ROLE_LABELS, useAuth } from "@/lib/auth-context";

export function AccountSettings() {
  const { user } = useAuth();
  const [passwordOpen, setPasswordOpen] = useState(false);

  if (!user) return null;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>계정</CardTitle>
          <CardDescription>로그인한 계정의 비밀번호를 변경할 수 있습니다.</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1">
            <p className="font-medium">{user.user_name}</p>
            <p className="text-sm text-muted-foreground">
              {user.user_id}
              {user.dept_name ? ` · ${user.dept_name}` : ""}
              {user.job_title ? ` · ${user.job_title}` : ""}
            </p>
            <Badge variant="muted">{ROLE_LABELS[user.role_level]}</Badge>
          </div>
          <Button variant="outline" onClick={() => setPasswordOpen(true)}>
            <KeyRound className="h-4 w-4" />
            비밀번호 변경
          </Button>
        </CardContent>
      </Card>
      <PasswordDialog open={passwordOpen} onOpenChange={setPasswordOpen} />
    </>
  );
}
