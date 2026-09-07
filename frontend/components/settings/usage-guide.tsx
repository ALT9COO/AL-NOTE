"use client";

import Image from "next/image";
import { ChartNoAxesCombined, FileAudio2, Grip, Mail, Mic, Presentation, Sparkles, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const GUIDE_SECTIONS = [
  {
    title: "칸반보드 사용방법",
    icon: Grip,
    image: "/guides/kanban-board.png",
    imageAlt: "AL-Note 칸반보드 화면",
    summary: "업무 카드를 끌어다 놓는 것만으로 진행 현황을 빠르게 업데이트할 수 있습니다.",
    steps: [
      {
        icon: Presentation,
        title: "상단 요약 카드 확인",
        body: "전체 업무, 완료, 지연, 평균 진행률을 먼저 보고 오늘 우선순위를 정합니다.",
      },
      {
        icon: Grip,
        title: "카드 드래그로 상태 변경",
        body: "업무 카드를 `할당`, `진행중`, `이슈 발생`, `완료` 컬럼으로 옮기면 상태가 바로 반영됩니다.",
      },
      {
        icon: Sparkles,
        title: "이슈와 진행률 함께 점검",
        body: "각 카드의 진행률, 담당자, 마감일, 이슈 문구를 함께 보면서 병목 업무를 빠르게 찾습니다.",
      },
    ],
    tips: [
      "검색창으로 업무명, 업무 ID, 이슈 문구를 바로 찾을 수 있습니다.",
      "담당자 필터를 쓰면 개인별 또는 팀별 업무만 빠르게 모아볼 수 있습니다.",
    ],
  },
  {
    title: "AI회의실 사용방법",
    icon: Mic,
    image: "/guides/ai-meeting-room.png",
    imageAlt: "AL-Note AI 회의실 화면",
    summary: "회의 녹음이나 파일 업로드를 기반으로 AI가 전사와 안건 정리를 도와줍니다.",
    steps: [
      {
        icon: Mic,
        title: "브라우저 녹음 또는 직접 입력",
        body: "짧은 회의는 브라우저에서 바로 녹음하고, 간단한 메모는 텍스트로 바로 붙여넣을 수 있습니다.",
      },
      {
        icon: Upload,
        title: "긴 회의는 파일 업로드",
        body: "1시간 이상 회의나 이미 녹음된 파일은 업로드 영역에 올리면 더 안정적으로 처리할 수 있습니다.",
      },
      {
        icon: FileAudio2,
        title: "전사 확인 후 업무 반영",
        body: "AI가 추출한 전사와 안건을 검토한 뒤 제출하면 업무 현황과 회의록에 한 번에 반영됩니다.",
      },
    ],
    tips: [
      "Outlook 일정을 연결해 두면 해당 날짜 회의를 쉽게 고르고 기록과 함께 관리할 수 있습니다.",
      "녹음 파일은 전사와 함께 서버에 보관됩니다. 회의록에서 다시 듣거나 파일로 저장할 수 있습니다.",
      "전사 중간 결과는 저장되므로 브라우저를 닫아도 나중에 이어서 진행할 수 있습니다.",
    ],
  },
  {
    title: "AI 리포트 사용방법",
    icon: ChartNoAxesCombined,
    image: "/guides/ai-report.png",
    imageAlt: "AL-Note AI 리포트 화면",
    summary: "기간별 업무 통계를 바탕으로 AI가 경영 보고용 요약 리포트를 생성하고 저장합니다.",
    steps: [
      {
        icon: ChartNoAxesCombined,
        title: "기간과 부서 범위 선택",
        body: "주간, 월간, 분기, 연간 중 보고 싶은 기간을 고르고 필요하면 특정 부서만 좁혀서 봅니다.",
      },
      {
        icon: Sparkles,
        title: "AI 리포트 생성",
        body: "생성 버튼을 누르면 성과, 병목, 리스크를 요약한 경영 리포트가 아래 보고서 영역에 만들어집니다. 주간을 고르면 전주 대비와 업무별 진행 비교가 함께 들어갑니다.",
      },
      {
        icon: Presentation,
        title: "저장된 리포트 다시 열람",
        body: "생성한 리포트는 서버에 저장되며, 목록에서 다시 열어보거나 필요할 때 메일 발송까지 이어갈 수 있습니다.",
      },
      {
        icon: Mail,
        title: "Outlook 메일 발송",
        body: "리포트가 만들어진 뒤 `Outlook으로 보내기`를 누르면 경영진이나 관련 부서에 바로 공유할 수 있습니다.",
      },
    ],
    tips: [
      "주간 리포트는 전주 진행상황과 이번주 진행 예정을 업무별로 보여 줍니다.",
      "리포트를 만들기 전 상단 통계 카드와 차트를 함께 보면 보고서 내용을 더 빠르게 검토할 수 있습니다.",
      "같은 기간이라도 부서를 바꿔 생성하면 팀별 리스크와 성과를 비교하기 쉽습니다.",
    ],
  },
];

export function UsageGuide() {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold tracking-tight">사용 가이드</h2>
        <p className="text-sm text-muted-foreground">
          AL-Note를 처음 쓰는 구성원이 바로 따라할 수 있도록 핵심 화면과 사용 흐름을 정리했습니다.
        </p>
      </div>

      <div className="grid gap-6">
        {GUIDE_SECTIONS.map((section) => {
          const Icon = section.icon;
          return (
            <Card key={section.title} className="overflow-hidden">
              <CardHeader className="pb-3">
                <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                  <Icon className="h-4 w-4 text-primary" />
                  {section.title}
                  <Badge variant="secondary">실제 화면</Badge>
                </CardTitle>
                <p className="text-sm text-muted-foreground">{section.summary}</p>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="overflow-hidden rounded-xl border bg-muted/20">
                  <Image
                    src={section.image}
                    alt={section.imageAlt}
                    width={1600}
                    height={900}
                    className="h-auto w-full object-cover"
                  />
                </div>

                <div
                  className={`grid gap-4 ${
                    section.steps.length >= 4 ? "md:grid-cols-2 xl:grid-cols-4" : "lg:grid-cols-3"
                  }`}
                >
                  {section.steps.map((step, index) => {
                    const StepIcon = step.icon;
                    return (
                      <div key={step.title} className="rounded-xl border bg-muted/20 p-4">
                        <div className="mb-2 flex items-center gap-2 text-sm font-medium">
                          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary/10 text-xs text-primary">
                            {index + 1}
                          </span>
                          <StepIcon className="h-4 w-4 text-primary" />
                          {step.title}
                        </div>
                        <p className="text-sm leading-6 text-muted-foreground">{step.body}</p>
                      </div>
                    );
                  })}
                </div>

                <div className="rounded-xl border border-dashed bg-background p-4">
                  <p className="text-sm font-medium">사용 팁</p>
                  <ul className="mt-2 space-y-2 text-sm text-muted-foreground">
                    {section.tips.map((tip) => (
                      <li key={tip} className="flex gap-2">
                        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/60" />
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </section>
  );
}
