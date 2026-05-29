"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  Briefcase,
  Building2,
  ChevronDown,
  ClipboardList,
  Database,
  Gauge,
  HeartPulse,
  Inbox,
  KeyRound,
  ListChecks,
  Mail,
  Network,
  Settings,
  ShieldCheck,
  Sparkles,
  Upload,
  Users,
  Workflow,
} from "lucide-react";
import { cn } from "@/lib/utils";

const groups = [
  { label: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: Gauge }, { href: "/activity", label: "Activity Feed", icon: Activity }] },
  {
    label: "Opportunities",
    items: [
      { href: "/opportunities", label: "All Opportunities", icon: Briefcase },
      { href: "/review-queue", label: "Review Queue", icon: ListChecks },
      { href: "/ai", label: "AI Scoring", icon: Sparkles },
      { href: "/opportunities?materials=true", label: "Application Materials", icon: ClipboardList },
      { href: "/opportunities?reminders=true", label: "Reminders", icon: Inbox },
    ],
  },
  {
    label: "Discovery",
    items: [
      { href: "/opportunities?import=manual", label: "Manual Import", icon: Upload },
      { href: "/opportunities?source=public", label: "Public Discovery", icon: Network },
      { href: "/integrations?service=gmail", label: "Gmail Import", icon: Mail },
      { href: "/opportunities?import=csv", label: "CSV Import", icon: Database },
      { href: "/integrations?service=apify", label: "Apify Import", icon: Bot },
    ],
  },
  { label: "Automation", items: [{ href: "/automation", label: "Rules", icon: Workflow }, { href: "/automation?tab=runs", label: "Runs", icon: Activity }, { href: "/automation?tab=errors", label: "Activity", icon: HeartPulse }] },
  { label: "Integrations", items: [{ href: "/integrations?service=ai_provider", label: "AI Providers", icon: Bot }, { href: "/integrations?service=gmail", label: "Gmail", icon: Mail }, { href: "/integrations?service=linkedin", label: "LinkedIn", icon: Briefcase }, { href: "/integrations?service=rapidapi_linkedin", label: "RapidAPI", icon: KeyRound }, { href: "/integrations?service=apify", label: "Apify", icon: Database }, { href: "/integrations?tab=providers", label: "Provider Registry", icon: Network }] },
  { label: "Team", items: [{ href: "/team", label: "Workspaces", icon: Building2 }, { href: "/team?tab=members", label: "Members", icon: Users }, { href: "/team?tab=organizations", label: "Organizations", icon: ShieldCheck }] },
  { label: "System", items: [{ href: "/settings?tab=feedback", label: "Feedback", icon: Inbox }, { href: "/settings?tab=audit", label: "Audit Logs", icon: ShieldCheck }, { href: "/settings?tab=usage", label: "Usage", icon: BarChart3 }, { href: "/settings?tab=health", label: "Health", icon: HeartPulse }, { href: "/settings", label: "Settings", icon: Settings }] },
];

export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentHref = useMemo(() => {
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, searchParams]);
  const initiallyOpen = useMemo(
    () =>
      Object.fromEntries(
        groups.map((group) => [
          group.label,
          group.label === "Overview" || group.items.some((item) => item.href === currentHref || item.href.split("?")[0] === pathname),
        ]),
      ) as Record<string, boolean>,
    [currentHref, pathname],
  );
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(initiallyOpen);

  useEffect(() => {
    const activeGroup = groups.find((group) => group.items.some((item) => item.href === currentHref || item.href.split("?")[0] === pathname));
    if (activeGroup) {
      setOpenGroups((current) => ({ ...current, [activeGroup.label]: true }));
    }
  }, [currentHref, pathname]);

  function toggleGroup(label: string) {
    setOpenGroups((current) => ({ ...current, [label]: !current[label] }));
  }

  return (
    <aside className="sticky top-0 hidden h-dvh w-72 shrink-0 flex-col overflow-hidden border-r bg-card/70 lg:flex">
      <Link href="/dashboard" className="flex h-16 shrink-0 items-center gap-3 border-b px-6">
        <span className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground"><Sparkles className="h-5 w-5" /></span>
        <span className="font-semibold">Opportunity AI</span>
      </Link>
      <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4">
        {groups.map((group) => (
          <section key={group.label}>
            <button
              type="button"
              className="flex h-9 w-full items-center justify-between rounded-md px-2 text-xs font-semibold uppercase text-muted-foreground transition hover:bg-muted hover:text-foreground"
              aria-expanded={Boolean(openGroups[group.label])}
              onClick={() => toggleGroup(group.label)}
            >
              <span>{group.label}</span>
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", !openGroups[group.label] && "-rotate-90")} />
            </button>
            {openGroups[group.label] ? (
              <div className="mt-1 space-y-1 pb-2">
                {group.items.map((item) => {
                  const active = currentHref === item.href || (item.href === pathname && !searchParams.toString());
                  const Icon = item.icon;
                  return (
                    <Link key={`${group.label}-${item.label}`} href={item.href} className={cn("flex h-9 items-center gap-3 rounded-md px-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground", active && "bg-muted text-foreground")}>
                      <Icon className="h-4 w-4 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </Link>
                  );
                })}
              </div>
            ) : null}
          </section>
        ))}
      </nav>
    </aside>
  );
}
