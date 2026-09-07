"use client";

import { useEffect, useState } from "react";
import { Loader2, LogIn, Mail } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { analyticsApi, apiErrorMessage, calendarApi } from "@/lib/api";
import type { CalendarConnection, Period, ReportResult } from "@/types";

export function ReportMailDialog({
  open,
  onOpenChange,
  report,
  period,
  deptId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ReportResult;
  period: Period;
  deptId: number | null;
}) {
  const [connection, setConnection] = useState<CalendarConnection | null>(null);
  const [to, setTo] = useState("");
  const [includeSelf, setIncludeSelf] = useState(true);
  const [sending, setSending] = useState(false);
  const [connecting, setConnecting] = useState(false);

  useEffect(() => {
    if (!open) return;
    calendarApi
      .connection()
      .then((data) => {
        setConnection(data);
        if (data.account_email) setIncludeSelf(true);
      })
      .catch(() => setConnection(null));
  }, [open]);

  async function handleConnect() {
    setConnecting(true);
    try {
      const { url } = await calendarApi.loginUrl();
      window.location.href = url;
    } catch (error) {
      toast.error(apiErrorMessage(error, "로그인 주소를 만들지 못했습니다."));
      setConnecting(false);
    }
  }

  async function handleSend() {
    const extras = to
      .split(/[,;\n]/)
      .map((raw) => raw.trim())
      .filter(Boolean);
    const recipients = [
      ...extras,
      ...(includeSelf && connection?.account_email ? [connection.account_email] : []),
    ];
    if (!recipients.length) {
      toast.error("수신자 이메일을 입력하세요.");
      return;
    }
    setSending(true);
    try {
      const result = await analyticsApi.emailReport({
        period,
        dept_id: deptId,
        to: recipients,
        markdown: report.report_markdown,
      });
      toast.success(`메일을 보냈습니다 (${result.sent_to.join(", ")})`);
      onOpenChange(false);
    } catch (error) {
      toast.error(apiErrorMessage(error, "메일 발송에 실패했습니다."));
    } finally {
      setSending(false);
    }
  }

  const canMail = connection?.connected && connection.can_mail && !connection.needs_reauth;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Mail className="h-4 w-4 text-primary" />
            Outlook으로 리포트 보내기
          </DialogTitle>
          <DialogDescription>
            연결된 Microsoft 계정으로 「{report.period_label}」 리포트를 발송합니다.
          </DialogDescription>
        </DialogHeader>

        {!canMail ? (
          <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-3 text-sm text-amber-900">
            <p>
              {connection?.connected
                ? "메일 발송에는 Mail.Send 권한이 필요합니다. Microsoft 계정을 다시 연결해 동의를 추가하세요."
                : "먼저 Microsoft 계정을 연결해야 메일을 보낼 수 있습니다."}
            </p>
            <Button size="sm" disabled={connecting} onClick={handleConnect}>
              {connecting ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <LogIn className="h-3.5 w-3.5" />
              )}
              Microsoft 계정 연결
            </Button>
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="mail_to">수신자 이메일</Label>
              <Textarea
                id="mail_to"
                rows={3}
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="여러 명은 쉼표 또는 줄바꿈으로 구분"
              />
            </div>
            {connection.account_email ? (
              <label className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={includeSelf}
                  onCheckedChange={(value) => setIncludeSelf(value === true)}
                />
                내 Outlook 계정으로도 보내기 ({connection.account_email})
              </label>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            닫기
          </Button>
          {canMail ? (
            <Button onClick={handleSend} disabled={sending}>
              {sending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              보내기
            </Button>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
