"use client";

import { useEffect, useState } from "react";
import {
  DragDropContext,
  Draggable,
  Droppable,
  type DropResult,
} from "@hello-pangea/dnd";

import { TaskCard } from "@/components/kanban/task-card";
import { cn, STATUS_META, STATUSES } from "@/lib/utils";
import type { Task, TaskStatus } from "@/types";

interface KanbanBoardProps {
  tasks: Task[];
  onMove: (task: Task, status: TaskStatus) => void;
  onEdit: (task: Task) => void;
  onSubtaskAdded?: () => void;
}

export function KanbanBoard({ tasks, onMove, onEdit, onSubtaskAdded }: KanbanBoardProps) {
  // @hello-pangea/dnd 는 SSR 중 마운트되면 안 되므로 클라이언트에서만 렌더링한다.
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  function handleDragEnd(result: DropResult) {
    const { destination, source, draggableId } = result;
    if (!destination) return;
    if (destination.droppableId === source.droppableId) return;

    const task = tasks.find((t) => t.task_id === draggableId);
    if (!task) return;
    onMove(task, destination.droppableId as TaskStatus);
  }

  const columns = STATUSES.map((status) => ({
    status,
    items: tasks.filter((task) => task.status === status),
  }));

  if (!mounted) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {STATUSES.map((status) => {
          const meta = STATUS_META[status];
          return (
            <section
              key={status}
              className="flex min-h-[240px] flex-col rounded-xl border bg-muted/40"
            >
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
            </section>
          );
        })}
      </div>
    );
  }

  return (
    <DragDropContext onDragEnd={handleDragEnd}>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {columns.map(({ status, items }) => {
          const meta = STATUS_META[status];
          return (
            <Droppable droppableId={status} key={status}>
              {(provided, snapshot) => (
                <section
                  ref={provided.innerRef}
                  {...provided.droppableProps}
                  className={cn(
                    "flex min-h-[240px] flex-col rounded-xl border bg-muted/40 transition-colors",
                    snapshot.isDraggingOver && "border-primary/40 bg-primary/5",
                  )}
                >
                  <header className="flex items-center justify-between border-b px-3.5 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className={cn("h-2 w-2 rounded-full", meta.dot)} />
                      <h3 className="text-sm font-semibold">{status}</h3>
                    </div>
                    <span className="rounded-full bg-background px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                      {items.length}
                    </span>
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
                </section>
              )}
            </Droppable>
          );
        })}
      </div>
    </DragDropContext>
  );
}
