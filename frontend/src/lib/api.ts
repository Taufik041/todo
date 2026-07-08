const API_BASE = "/api";

export type Priority = "low" | "medium" | "high";

export interface Todo {
  id: string;
  title: string;
  description: string | null;
  priority: Priority;
  completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface TodoCreate {
  title: string;
  description?: string;
  priority?: Priority;
}

export interface TodoUpdate {
  title?: string;
  description?: string;
  priority?: Priority;
  completed?: boolean;
}

export interface User {
  id: string;
  email: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let detail = text;
    try {
      detail = JSON.parse(text).detail ?? text;
    } catch {
      // not JSON, keep raw text
    }
    throw new ApiError(res.status, detail || `API ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  me: () => request<User>("/auth/me"),
  login: (email: string, password: string) =>
    request<{ message: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  register: (email: string, password: string, confirmPassword: string) =>
    request<{ message: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        confirm_password: confirmPassword,
      }),
    }),
  logout: () => request<{ message: string }>("/auth/logout", { method: "POST" }),

  listTodos: () => request<Todo[]>("/todos"),
  createTodo: (data: TodoCreate) =>
    request<Todo>("/todos", { method: "POST", body: JSON.stringify(data) }),
  updateTodo: (id: string, data: TodoUpdate) =>
    request<Todo>(`/todos/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteTodo: (id: string) =>
    request<void>(`/todos/${id}`, { method: "DELETE" }),
};
