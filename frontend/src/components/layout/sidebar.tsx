"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
  { label: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: Gauge }, { href: "/analytics", label: "Activity Feed", icon: Activity }] },
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
  { label: "Integrations", items: [{ href: "/integrations", label: "AI Providers", icon: Bot }, { href: "/integrations?service=gmail", label: "Gmail", icon: Mail }, { href: "/integrations?service=linkedin", label: "LinkedIn", icon: Briefcase }, { href: "/integrations?service=rapidapi", label: "RapidAPI", icon: KeyRound }, { href: "/integrations?service=apify", label: "Apify", icon: Database }, { href: "/integrations?tab=providers", label: "Provider Registry", icon: Network }] },
  { label: "Team", items: [{ href: "/team", label: "Workspaces", icon: Building2 }, { href: "/team?tab=members", label: "Members", icon: Users }, { href: "/team?tab=organizations", label: "Organizations", icon: ShieldCheck }] },
  { label: "System", items: [{ href: "/settings?tab=feedback", label: "Feedback", icon: Inbox }, { href: "/settings?tab=audit", label: "Audit Logs", icon: ShieldCheck }, { href: "/settings?tab=usage", label: "Usage", icon: BarChart3 }, { href: "/settings?tab=health", label: "Health", icon: HeartPulse }, { href: "/settings", label: "Settings", icon: Settings }] },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden h-screen w-72 shrink-0 border-r bg-card/70 p-4 lg:block">
      <Link href="/dashboard" className="mb-6 flex items-center gap-3 px-2">
        <span className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground"><Sparkles className="h-5 w-5" /></span>
        <span className="font-semibold">Opportunity AI</span>
      </Link>
      <nav className="space-y-5 overflow-y-auto pb-8">
        {groups.map((group) => (
          <section key={group.label}>
            <div className="mb-2 flex items-center gap-2 px-2 text-xs font-semibold uppercase text-muted-foreground">
              <ChevronDown className="h-3.5 w-3.5" /> {group.label}
            </div>
            <div className="space-y-1">
              {group.items.map((item) => {
                const active = pathname === item.href.split("?")[0];
                const Icon = item.icon;
                return (
                  <Link key={`${group.label}-${item.label}`} href={item.href} className={cn("flex h-9 items-center gap-3 rounded-md px-2 text-sm text-muted-foreground transition hover:bg-muted hover:text-foreground", active && "bg-muted text-foreground")}>
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </nav>
    </aside>
  );
}
