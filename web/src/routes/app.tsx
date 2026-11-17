import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { AppSidebar } from "@/components/app/AppSidebar";
import { ComingSoonProvider } from "@/components/app/ComingSoon";
import { LogoMark } from "@/components/brand/Logo";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app")({
  component: AppLayout,
});

const KEY = "emostream.sidebar.collapsed";

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const path = useRouterState({ select: (s) => s.location.pathname });

  useEffect(() => {
    setCollapsed(window.localStorage.getItem(KEY) === "1");
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      window.localStorage.setItem(KEY, c ? "0" : "1");
      return !c;
    });
  };

  return (
    <ComingSoonProvider>
      <div className="flex min-h-screen bg-background">
        <aside
          className={cn(
            "sticky top-0 hidden h-screen shrink-0 transition-[width] duration-300 ease-soft md:block",
            collapsed ? "w-[68px]" : "w-[252px]",
          )}
        >
          <AppSidebar collapsed={collapsed} onToggle={toggle} />
        </aside>

        <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
          <SheetContent side="left" className="w-[280px] p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <AppSidebar collapsed={false} mobile onNavigate={() => setMobileOpen(false)} />
          </SheetContent>
        </Sheet>

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/90 px-4 backdrop-blur md:hidden">
            <button
              onClick={() => setMobileOpen(true)}
              className="inline-flex size-9 items-center justify-center rounded-md hover:bg-accent"
              aria-label="Open navigation"
            >
              <Menu className="size-5" />
            </button>
            <Link to="/app" className="flex items-center gap-2">
              <LogoMark className="size-6" />
              <span className="text-sm font-semibold">EmoStream</span>
            </Link>
          </div>
          <main key={path} className="animate-rise flex-1">
            <Outlet />
          </main>
        </div>
      </div>
    </ComingSoonProvider>
  );
}
