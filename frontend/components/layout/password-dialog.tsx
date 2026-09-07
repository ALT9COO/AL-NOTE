"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

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
import { authApi, apiErrorMessage } from "@/lib/api";

export function PasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);

  function reset() {
    setCurrentPassword("");
    setNextPassword("");
    setConfirm("");
  }

  async function handleSave() {
    if (nextPassword.length < 4) {
      toast.error("새 비밀번호는 4자 이상이어야 합니다.");
      return;
    }
    if (nextPassword !== confirm) {
      toast.error("새 비밀번호가 일치하지 않습니다.");
      return;
    }
    setSaving(true);
    try {
      await authApi.changePassword(currentPassword, nextPassword);
      toast.success("비밀번호를 변경했습니다.");
      reset();
      onOpenChange(false);
    } catch (error) {
      toast.error(apiErrorMessage(error, "비밀번호 변경에 실패했습니다."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>비밀번호 변경</DialogTitle>
          <DialogDescription>현재 비밀번호를 확인한 뒤 새 비밀번호로 바꿉니다.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="cur_pw">현재 비밀번호</Label>
            <Input
              id="cur_pw"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new_pw">새 비밀번호 (4자 이상)</Label>
            <Input
              id="new_pw"
              type="password"
              value={nextPassword}
              onChange={(e) => setNextPassword(e.target.value)}
              autoComplete="new-password"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new_pw2">새 비밀번호 확인</Label>
            <Input
              id="new_pw2"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSave} disabled={saving || !currentPassword || !nextPassword}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            변경
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
