import { Link, useRouterState } from "@tanstack/react-router";
import {
  Activity,
  AudioLines,
  Blocks,
  BookOpen,
  Cpu,
  GalleryHorizontalEnd,
  LayoutPanelTop,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings2,
  SquareUserRound,
  Type,
  type LucideIcon,
} from "lucide-react";
import { LogoMark } from "@/components/brand/Logo";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { useEngineStatus } from "@/lib/engine/useEngineStatus";

type To =
  | "/app"
  | "/app/studio"
  | "/app/avatars"
  | "/app/sessions"
  | "/app/analytics"
  | "/app/models"
  | "/app/integrations"
  | "/app/settings"
  | "/app/help"
  | "/app/text-to-speech"
  | "/app/conversation";

interface Item {
  to: To;
  label: string;
  icon: LucideIcon;
  soon?: boolean;
}

const GROUPS: { label: string; items: Item[] }[] = [
  {
    label: "Workspace",
    items: [
      { to: "/app", label: "Overview", icon: LayoutPanelTop },
      { to: "/app/avatars", label: "My Avatars", icon: SquareUserRound },
      { to: "/app/sessions", label: "Sessions", icon: GalleryHorizontalEnd },
    ],
  },
  {
    label: "Voice sources",
    items: [
      { to: "/app/text-to-speech", label: "Text to speech", icon: Type, soon: true },
      { to: "/app/conversation", label: "AI conversation", icon: MessagesSquare, soon: true },
    ],
  },
  {
    label: "Insights",
    items: [
      { to: "/app/analytics", label: "Analytics", icon: Activity },
      { to: "/app/models", label: "Models & Performance", icon: Cpu },
    ],
  },
  { label: "Ecosystem", items: [{ to: "/app/integrations", label: "Integrations", icon: Blocks }] },
  {
    label: "Preferences",
    items: [
      { to: "/app/settings", label: "Settings", icon: Settings2 },
      { to: "/app/help", label: "About & Help", icon: BookOpen },
    ],
  },
];

export function AppSidebar({
  collapsed,
  onToggle,
  onNavigate,
  mobile = false,
}: {
  collapsed: boolean;
  onToggle?: () => void;
  onNavigate?: () => void;
  mobile?: boolean;
}) {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const { status } = useEngineStatus();
  const studioActive = path.startsWith("/app/studio");

  return (
    <div
      className={cn(
        "flex h-full flex-col bg-sidebar text-sidebar-foreground",
        !mobile && "border-r border-sidebar-border",
      )}
    >
      <div className={cn("flex h-16 items-center gap-2 px-4", collapsed && "justify-center px-0")}>
        <Link
          to="/"
          className="flex items-center gap-2"
          aria-label="EmoStream website"
          onClick={onNavigate}
        >
          <LogoMark className="size-7 text-foreground" />
          {!collapsed && (
            <span className="text-[1.05rem] font-semibold tracking-[-0.03em]">
              Emo<span className="font-display text-[1.25rem] font-normal italic">Stream</span>
            </span>
          )}
        </Link>
      </div>

      {/* Primary destination */}
      <div className={cn("px-3", collapsed && "px-2")}>
        <NavTip label="Studio" show={collapsed}>
          <Link
            to="/app/studio"
            onClick={onNavigate}
            className={cn(
              "group relative flex items-center gap-3 overflow-hidden rounded-lg border transition-colors duration-200",
              collapsed ? "h-11 justify-center" : "px-3 py-3",
              studioActive
                ? "stage-band border-transparent"
                : "border-sidebar-border bg-surface hover:border-foreground/25",
            )}
          >
            <AudioLines
              className={cn(
                "size-[18px] shrink-0",
                studioActive ? "text-ember" : "text-foreground",
              )}
            />
            {!collapsed && (
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">Studio</span>
                <span
                  className={cn(
                    "block truncate text-[11.5px]",
                    studioActive ? "text-stage-muted" : "text-muted-foreground",
                  )}
                >
                  Portrait → voice → emotion
                </span>
              </span>
            )}
          </Link>
        </NavTip>
      </div>

      <nav className="mt-4 flex-1 overflow-y-auto px-3 pb-4" aria-label="Application">
        {GROUPS.map((g) => (
          <div key={g.label} className="mt-4 first:mt-1">
            {collapsed ? (
              <div className="mx-auto my-2 h-px w-6 bg-sidebar-border" />
            ) : (
              <p className="eyebrow mb-1.5 px-2.5 text-[10px] text-muted-foreground/80">
                {g.label}
              </p>
            )}
            <ul className="space-y-px">
              {g.items.map((it) => {
                const active =
                  it.to === "/app" ? path === "/app" || path === "/app/" : path.startsWith(it.to);
                return (
                  <li key={it.to}>
                    <NavTip
                      label={it.soon ? `${it.label} · coming soon` : it.label}
                      show={collapsed}
                    >
                      <Link
                        to={it.to}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "group relative flex h-9 items-center gap-3 rounded-md text-[13.5px] transition-colors duration-150",
                          collapsed ? "justify-center" : "px-2.5",
                          active
                            ? "bg-sidebar-accent font-medium text-foreground"
                            : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
                        )}
                      >
                        <span
                          className={cn(
                            "absolute -left-3 top-1/2 h-4 w-[2px] -translate-y-1/2 rounded-r bg-ember transition-opacity",
                            active ? "opacity-100" : "opacity-0",
                          )}
                          aria-hidden
                        />
                        <it.icon className="size-[17px] shrink-0" strokeWidth={1.75} />
                        {!collapsed && <span className="flex-1 truncate">{it.label}</span>}
                        {!collapsed && it.soon && (
                          <span className="rounded border border-dashed border-soon/60 px-1 font-mono text-[9px] uppercase tracking-wider text-soon">
                            Soon
                          </span>
                        )}
                      </Link>
                    </NavTip>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className={cn("border-t border-sidebar-border p-3", collapsed && "px-2")}>
        <NavTip label={engineLabel(status)} show={collapsed}>
          <Link
            to="/app/settings"
            hash="performance"
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-2.5 rounded-md px-2 py-2 text-xs hover:bg-sidebar-accent/60",
              collapsed && "justify-center px-0",
            )}
          >
            <span
              className={cn(
                "size-2 shrink-0 rounded-full",
                status === "online"
                  ? "bg-success"
                  : status === "offline"
                    ? "bg-live"
                    : status === "checking"
                      ? "bg-warning animate-rec"
                      : "bg-muted-foreground/40",
              )}
            />
            {!collapsed && (
              <span className="min-w-0">
                <span className="block font-medium text-foreground">Engine</span>
                <span className="block truncate text-muted-foreground">{engineLabel(status)}</span>
              </span>
            )}
          </Link>
        </NavTip>
        {onToggle && (
          <button
            onClick={onToggle}
            className={cn(
              "mt-1 flex h-8 w-full items-center gap-2.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground",
              collapsed && "justify-center px-0",
            )}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <PanelLeftOpen className="size-4" />
            ) : (
              <PanelLeftClose className="size-4" />
            )}
            {!collapsed && "Collapse"}
          </button>
        )}
      </div>
    </div>
  );
}

function engineLabel(s: string) {
  return s === "online"
    ? "Connected"
    : s === "offline"
      ? "Unreachable"
      : s === "checking"
        ? "Checking…"
        : "Not connected";
}

function NavTip({
  label,
  show,
  children,
}: {
  label: string;
  show: boolean;
  children: React.ReactNode;
}) {
  if (!show) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="right">{label}</TooltipContent>
    </Tooltip>
  );
}
