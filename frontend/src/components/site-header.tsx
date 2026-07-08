"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

export function SiteHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();

  if (!user) return null;

  return (
    <header className="border-b">
      <div className="container max-w-2xl mx-auto flex items-center justify-between py-2 px-4">
        <span className="text-sm text-muted-foreground">{user.email}</span>
        <Button
          variant="ghost"
          size="sm"
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
        >
          <LogOut className="h-4 w-4 mr-2" />
          Log out
        </Button>
      </div>
    </header>
  );
}
