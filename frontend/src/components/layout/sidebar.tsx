"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BarChart3,
  Bot,
  Briefcase,
  ChevronDown,
  ClipboardList,
  Gauge,
  Inbox,
  Mail,
  Settings,
  Sparkles,
  Upload,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { springTap } from "@/lib/animation";
import { opportunityService } from "@/services/opportunity.service";

const groups = [
  { label: "Overview", items: [{ href: "/dashboard", label: "Dashboard", icon: Gauge }, { href: "/agent", label: "Assistant", icon: Sparkles }, { href: "/analytics", label: "Insights", icon: BarChart3 }] },
  {
    label: "Jobs",
    items: [
      { href: "/opportunities", label: "All Jobs", icon: Briefcase },
      { href: "/opportunities?source=public", label: "Find Jobs", icon: Sparkles },
      { href: "/opportunities?import=manual", label: "Add Job", icon: Upload },
      { href: "/opportunities?materials=true", label: "Application Materials", icon: ClipboardList },
      { href: "/opportunities?reminders=true", label: "Reminders", icon: Inbox },
    ],
  },
  {
    label: "Profile",
    items: [
      { href: "/settings?tab=profile", label: "Resume Profile", icon: UserRound },
      { href: "/integrations?service=ai_provider", label: "AI Provider", icon: Bot },
      { href: "/integrations?service=gmail", label: "Gmail Import", icon: Mail },
      { href: "/settings", label: "Settings", icon: Settings },
    ],
  },
];

const container = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.04, delayChildren: 0.1 } },
};

const item = {
  hidden: { opacity: 0, x: -16 },
  visible: { opacity: 1, x: 0, transition: { type: "spring" as const, stiffness: 260, damping: 24 } },
};

const groupContainer = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.03 } },
};

export function Sidebar() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentHref = useMemo(() => {
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, searchParams]);
  const { data: jobs } = useQuery({ queryKey: ["opportunities"], queryFn: () => opportunityService.list(), staleTime: 30_000 });
  const unscoredCount = useMemo(() => (jobs ?? []).filter((j) => j.match_score == null && j.score == null).length, [jobs]);
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
    <aside className="glass-strong fixed left-0 top-0 z-30 hidden h-dvh w-64 shrink-0 flex-col overflow-hidden border-r xl:w-72 lg:flex">
      <Link href="/dashboard" className="glass-subtle flex h-16 shrink-0 items-center gap-3 border-b px-6">
        <span className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground"><Sparkles className="h-5 w-5" /></span>
        <span className="font-semibold">Job Assistant</span>
      </Link>
      <motion.nav
        variants={container}
        initial="hidden"
        animate="visible"
        className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-4"
      >
        {groups.map((group) => (
          <motion.section key={group.label} variants={item}>
            <motion.button
              type="button"
              whileTap={{ scale: 0.97 }}
              transition={springTap}
              className="flex h-9 w-full items-center justify-between rounded-md px-2 text-xs font-semibold uppercase text-muted-foreground transition hover:bg-white/30 hover:text-foreground dark:hover:bg-white/10"
              aria-expanded={Boolean(openGroups[group.label])}
              onClick={() => toggleGroup(group.label)}
            >
              <span>{group.label}</span>
              <motion.span
                animate={{ rotate: openGroups[group.label] ? 0 : -90 }}
                transition={{ type: "spring", stiffness: 260, damping: 20 }}
              >
                <ChevronDown className="h-3.5 w-3.5" />
              </motion.span>
            </motion.button>
            {openGroups[group.label] ? (
              <motion.div
                variants={groupContainer}
                initial="hidden"
                animate="visible"
                className="mt-1 space-y-1 pb-2"
              >
                {group.items.map((navItem) => {
                  const active = currentHref === navItem.href || (navItem.href === pathname && !searchParams.toString());
                  const Icon = navItem.icon;
                  return (
                    <motion.div key={`${group.label}-${navItem.label}`} variants={item}>
                      <Link
                        href={navItem.href}
                        className={cn(
                          "flex h-9 items-center gap-3 rounded-md px-2 text-sm text-muted-foreground transition hover:bg-white/30 hover:text-foreground dark:hover:bg-white/10",
                          active && "glass-subtle text-foreground",
                        )}
                      >
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="truncate">{navItem.label}</span>
                        {navItem.label === "All Jobs" && unscoredCount > 0 ? (
                          <motion.span
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            className="ml-auto rounded-full bg-destructive px-1.5 py-0.5 text-[10px] font-semibold leading-none text-destructive-foreground"
                          >
                            {unscoredCount}
                          </motion.span>
                        ) : null}
                      </Link>
                    </motion.div>
                  );
                })}
              </motion.div>
            ) : null}
          </motion.section>
        ))}
      </motion.nav>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentHref = useMemo(() => {
    const query = searchParams.toString();
    return query ? `${pathname}?${query}` : pathname;
  }, [pathname, searchParams]);
  const items = groups.flatMap((group) => group.items).slice(0, 8);

  return (
    <motion.nav
      variants={container}
      initial="hidden"
      animate="visible"
      className="glass-strong sticky top-16 z-10 flex gap-2 overflow-x-auto border-b px-3 py-2 lg:hidden"
    >
      {items.map((navItem) => {
        const active = currentHref === navItem.href || (navItem.href === pathname && !searchParams.toString());
        const Icon = navItem.icon;
        return (
          <motion.div key={navItem.href} variants={item}>
            <Link
              href={navItem.href}
              className={cn(
                "flex h-9 shrink-0 items-center gap-2 rounded-md px-3 text-sm text-muted-foreground transition hover:bg-white/30 hover:text-foreground dark:hover:bg-white/10",
                active && "glass-subtle text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{navItem.label}</span>
            </Link>
          </motion.div>
        );
      })}
    </motion.nav>
  );
}
