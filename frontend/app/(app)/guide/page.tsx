"use client";

import { UsageGuide } from "@/components/settings/usage-guide";

export default function GuidePage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">사용자 가이드</h1>
        <p className="text-sm text-muted-foreground">
          칸반보드와 AI회의실의 핵심 흐름을 실제 화면과 함께 빠르게 익힐 수 있습니다.
        </p>
      </header>

      <UsageGuide />
    </div>
  );
}
