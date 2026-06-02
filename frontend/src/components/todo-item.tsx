"use client";

import { useState } from "react";
import { Pencil, Trash2 } from "lucide-react";
import type { Priority, Todo, TodoUpdate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TodoForm } from "@/components/todo-form";

const priorityClass: Record<Priority, string> = {
  low: "border-green-300 bg-green-50 text-green-700",
  medium: "border-amber-300 bg-amber-50 text-amber-700",
  high: "border-red-300 bg-red-50 text-red-700",
};

interface TodoItemProps {
  todo: Todo;
  onToggle: () => Promise<void>;
  onUpdate: (data: TodoUpdate) => Promise<void>;
  onDelete: () => Promise<void>;
}

export function TodoItem({ todo, onToggle, onUpdate, onDelete }: TodoItemProps) {
  const [editOpen, setEditOpen] = useState(false);
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  return (
    <>
      <Card className={todo.completed ? "opacity-60" : ""}>
        <CardContent className="flex items-start gap-3 p-4">
          <Checkbox
            checked={todo.completed}
            disabled={toggling}
            onCheckedChange={async () => {
              setToggling(true);
              await onToggle();
              setToggling(false);
            }}
            className="mt-0.5 shrink-0"
          />

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span
                className={`font-medium text-sm leading-snug ${
                  todo.completed ? "line-through text-muted-foreground" : ""
                }`}
              >
                {todo.title}
              </span>
              <Badge variant="outline" className={`text-xs shrink-0 ${priorityClass[todo.priority]}`}>
                {todo.priority}
              </Badge>
            </div>
            {todo.description && (
              <p className="text-sm text-muted-foreground mt-0.5 line-clamp-2">
                {todo.description}
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              {new Date(todo.created_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </p>
          </div>

          <div className="flex gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setEditOpen(true)}
            >
              <Pencil className="h-3.5 w-3.5" />
              <span className="sr-only">Edit</span>
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={deleting}
              onClick={async () => {
                setDeleting(true);
                await onDelete();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              <span className="sr-only">Delete</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Todo</DialogTitle>
          </DialogHeader>
          <TodoForm
            defaultValues={todo}
            onSubmit={async (data) => {
              await onUpdate(data);
              setEditOpen(false);
            }}
            onCancel={() => setEditOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
