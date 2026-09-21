"use client";

import { useEffect, useState } from "react";
import {
  DragDropContext,
  Draggable,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";
import { ChevronLeft, ChevronRight } from "lucide-react";

import { TaskCard } from "@/components/kanban/task-card";
import { cn, STATUS_META, STATUSES } from "@/lib/utils";
import type { Task, TaskStatus } from "@/types";

const ISSUE_STATUS: TaskStatus = "이슈 발생";
const ISSUE_OPEN_KEY = "alnote_kanban_issue_open";

interface KanbanBoardProps {
  tasks: Task[];
  onMove: (task: Task, status: TaskStatus) => void;
  onNest: (task: Task, parent: Task) => void;
  onEdit: (task: Task) => void;
  onSubtaskAdded?: () => void;
}

export function KanbanBoard({ tasks, onMove, onNest, onEdit, onSubtaskAdded }: KanbanBoardProps) {
  // @hello-pangea/dnd 는 SSR 중 마운트되면 안 되므로 클라이언트에서만 렌더링한다.
  const [mounted, setMounted] = useState(false);
  const [issueOpen, setIssueOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
    setIssueOpen(window.localStorage.getItem(ISSUE_OPEN_KEY) === "1");
  }, []);

  function toggleIssueOpen() {
    setIssueOpen((prev) => {
      const next = !prev;
      window.localStorage.setItem(ISSUE_OPEN_KEY, next ? "1" : "0");
      return next;
    });
  }

  function handleDragEnd(result: DropResult) {
    const { combine, destination, source, draggableId } = result;
    const task = tasks.find((item) => item.task_id === draggableId);
    if (!task) return;

    if (combine) {
      const parent = tasks.find((item) => item.task_id === combine.draggableId);
      if (parent && parent.task_id !== task.task_id) onNest(task, parent);
      return;
    }

    if (!destination) return;
    if (destination.droppableId === source.droppableId) return;

    onMove(task, destination.droppableId as TaskStatus);
  }

  const columns = STATUSES.map((status) => ({
    status,
    items: tasks.filter((task) => task.status === status),
  }));

  if (!mounted) {
    return (
      <div className="flex flex-wrap gap-4">
        {STATUSES.map((status) => {
          const meta = STATUS_META[status];
          const collapsed = status === ISSUE_STATUS;
          return (
            <section
              key={status}
              className={cn(
                "flex rounded-xl border bg-muted/40",
                collapsed
                  ? "h-12 w-full basis-full xl:h-auto xl:min-h-[240px] xl:w-14 xl:basis-auto xl:flex-none xl:flex-col"
                  : "min-h-[240px] min-w-[240px] flex-1 basis-[240px] flex-col",
              )}
            >
              {collapsed ? (
                <div className="flex flex-1 items-center justify-center gap-2 px-3 xl:flex-col xl:gap-3 xl:px-1.5 xl:py-3">
                  <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
                  <span className="text-xs font-semibold xl:[writing-mode:vertical-rl]">
                    {status}
                  </span>
                </div>
              ) : (
                <>
                  <header className="flex items-center justify-between border-b px-3.5 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
                      <h3 className="text-sm font-semibold">{status}</h3>
                    </div>
                    <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      …
                    </span>
                  </header>
                  <div className="space-y-2.5 p-2.5">
                    <div className="h-20 animate-pulse rounded-lg bg-muted" />
                    <div className="h-16 animate-pulse rounded-lg bg-muted" />
                  </div>
                </>
              )}
            </section>
          );
        })}
      </div>
    );
  }

  return (
    <DragDropContext onDragEnd={handleDragEnd}>
      <div className="flex flex-wrap gap-4">
        {columns.map(({ status, items }) => {
          const meta = STATUS_META[status];
          const isIssue = status === ISSUE_STATUS;
          const collapsed = isIssue && !issueOpen;

          return (
            <Droppable droppableId={status} key={status} isCombineEnabled>
              {(provided, snapshot) => (
                <section
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                  className={cn(
                    "flex rounded-xl border bg-muted/40 transition-colors",
                    collapsed
                      ? "h-12 w-full basis-full xl:h-auto xl:min-h-[240px] xl:w-14 xl:basis-auto xl:flex-none xl:flex-col"
                      : "min-h-[240px] min-w-[240px] flex-1 basis-[240px] flex-col",
                    snapshot.isDraggingOver && "border-primary/40 bg-primary/5",
                    collapsed && items.length > 0 && "border-amber-300 bg-amber-50/70",
                  )}
                >
                  {collapsed ? (
                    <button
                      type="button"
                      onClick={toggleIssueOpen}
                      aria-expanded={false}
                      title="이슈 발생 단계 펼치기"
                      className="flex h-full w-full items-center justify-center gap-2 px-3 text-left hover:bg-background/60 xl:flex-col xl:gap-3 xl:px-1.5 xl:py-3"
                    >
                      <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className={cn("h-2 w-2 shrink-0 rounded-full", meta.dot)} />
                      <span className="text-xs font-semibold xl:[writing-mode:vertical-rl]">
                        {status}
                      </span>
                      <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground xl:px-1.5">
                        {items.length}
                      </span>
                    </button>
                  ) : (
                    <>
                      <header className="flex items-center justify-between border-b px-3.5 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
                          <h3 className="text-sm font-semibold">{status}</h3>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            {items.length}
                          </span>
                          {isIssue ? (
                            <button
                              type="button"
                              onClick={toggleIssueOpen}
                              aria-expanded
                              title="이슈 발생 단계 접기"
                              className="rounded-md p-1 text-muted-foreground hover:bg-background hover:text-foreground"
                            >
                              <ChevronLeft className="h-3.5 w-3.5" />
                            </button>
                          ) : null}
                        </div>
                      </header>

                      <div className="scrollbar-thin flex-1 space-y-2.5 overflow-y-auto p-2.5">
                        {items.length === 0 && !snapshot.isDraggingOver ? (
                          <p className="py-8 text-center text-xs text-muted-foreground">
                            업무 없음
                          </p>
                        ) : null}

                        {items.map((task, index) => (
                          <Draggable
                            draggableId={task.task_id}
                            index={index}
                            key={task.task_id}
                            isDragDisabled={!task.can_edit}
                          >
                            {(dragProvided, dragSnapshot) => (
                              <div
                                ref={dragProvided.innerRef}
                                {...dragProvided.draggableProps}
                                className={cn(!task.can_edit && "cursor-default")}
                              >
                                <TaskCard
                                  task={task}
                                  dragging={dragSnapshot.isDragging}
                                  nestingTarget={Boolean(dragSnapshot.combineTargetFor)}
                                  dragHandleProps={dragProvided.dragHandleProps}
                                  onOpen={onEdit}
                                  onSubtaskAdded={onSubtaskAdded}
                                />
                              </div>
                            )}
                          </Draggable>
                        ))}
                        {provided.placeholder}
                      </div>
                    </>
                  )}
                  {collapsed ? provided.placeholder : null}
                </section>
              )}
            </Droppable>
          );
        })}
      </div>
    </DragDropContext>
  );
}
