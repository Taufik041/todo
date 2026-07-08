"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Plus, ClipboardList } from "lucide-react";
import { Toaster, toast } from "sonner";
import { api, type Todo, type TodoUpdate } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { TodoItem } from "@/components/todo-item";
import { TodoForm } from "@/components/todo-form";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

type Filter = "all" | "active" | "completed";

export default function Home() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [todos, setTodos] = useState<Todo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Filter>("all");
  const [createOpen, setCreateOpen] = useState(false);

  const fetchTodos = useCallback(async () => {
    try {
      const data = await api.listTodos();
      setTodos(data);
    } catch {
      toast.error("Failed to load todos");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!authLoading && !user) router.replace("/login");
  }, [authLoading, user, router]);

  useEffect(() => {
    if (user) fetchTodos();
  }, [user, fetchTodos]);

  if (authLoading || !user) {
    return (
      <main className="min-h-screen bg-background">
        <div className="text-center py-16 text-muted-foreground text-sm">Loading…</div>
      </main>
    );
  }

  const filtered = todos.filter((t) => {
    if (filter === "active") return !t.completed;
    if (filter === "completed") return t.completed;
    return true;
  });

  const counts = {
    all: todos.length,
    active: todos.filter((t) => !t.completed).length,
    completed: todos.filter((t) => t.completed).length,
  };

  const handleToggle = async (todo: Todo) => {
    try {
      const updated = await api.updateTodo(todo.id, { completed: !todo.completed });
      setTodos((prev) => prev.map((t) => (t.id === todo.id ? updated : t)));
    } catch {
      toast.error("Failed to update todo");
    }
  };

  const handleUpdate = async (todo: Todo, data: TodoUpdate) => {
    try {
      const updated = await api.updateTodo(todo.id, data);
      setTodos((prev) => prev.map((t) => (t.id === todo.id ? updated : t)));
      toast.success("Todo updated");
    } catch {
      toast.error("Failed to update todo");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.deleteTodo(id);
      setTodos((prev) => prev.filter((t) => t.id !== id));
      toast.success("Todo deleted");
    } catch {
      toast.error("Failed to delete todo");
    }
  };

  return (
    <main className="min-h-screen bg-background">
      <div className="container max-w-2xl mx-auto py-12 px-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Todos</h1>
            <p className="text-muted-foreground mt-1 text-sm">
              {counts.active === 0
                ? "All caught up!"
                : `${counts.active} task${counts.active !== 1 ? "s" : ""} remaining`}
            </p>
          </div>
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                New Todo
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Create Todo</DialogTitle>
              </DialogHeader>
              <TodoForm
                onSubmit={async (data) => {
                  try {
                    const created = await api.createTodo(data);
                    setTodos((prev) => [created, ...prev]);
                    setCreateOpen(false);
                    toast.success("Todo created");
                  } catch {
                    toast.error("Failed to create todo");
                  }
                }}
                onCancel={() => setCreateOpen(false)}
              />
            </DialogContent>
          </Dialog>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2 mb-6">
          {(["all", "active", "completed"] as Filter[]).map((f) => (
            <Button
              key={f}
              variant={filter === f ? "default" : "outline"}
              size="sm"
              onClick={() => setFilter(f)}
              className="capitalize"
            >
              {f}
              <span className="ml-1.5 text-xs opacity-70">{counts[f]}</span>
            </Button>
          ))}
        </div>

        <Separator className="mb-6" />

        {/* List */}
        {loading ? (
          <div className="text-center py-16 text-muted-foreground text-sm">Loading…</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
            <ClipboardList className="h-10 w-10 opacity-30" />
            <p className="text-sm">
              {filter === "all" ? "No todos yet — create one!" : `No ${filter} todos.`}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((todo) => (
              <TodoItem
                key={todo.id}
                todo={todo}
                onToggle={() => handleToggle(todo)}
                onUpdate={(data) => handleUpdate(todo, data)}
                onDelete={() => handleDelete(todo.id)}
              />
            ))}
          </div>
        )}
      </div>

      <Toaster richColors position="bottom-right" />
    </main>
  );
}
