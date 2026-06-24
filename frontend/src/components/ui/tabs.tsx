"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

type TabsContextValue = { value: string; setValue: (value: string) => void; activeIndex: number; setActiveIndex: (index: number) => void };
const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error("Tabs components must be used within <Tabs>");
  return ctx;
}

export function Tabs({
  defaultValue,
  value: controlledValue,
  onValueChange,
  className,
  children,
}: {
  defaultValue?: string;
  value?: string;
  onValueChange?: (value: string) => void;
  className?: string;
  children: ReactNode;
}) {
  const [uncontrolled, setUncontrolled] = useState(defaultValue ?? "");
  const [activeIndex, setActiveIndex] = useState(0);
  const value = controlledValue ?? uncontrolled;
  const setValue = (next: string) => {
    if (controlledValue === undefined) setUncontrolled(next);
    onValueChange?.(next);
  };
  return (
    <TabsContext.Provider value={{ value, setValue, activeIndex, setActiveIndex }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ className, children }: { className?: string; children: ReactNode }) {
  const { value } = useTabs();
  const items = (Array.isArray(children) ? children : [children]) as React.ReactElement[];
  const activeIndex = items.findIndex(
    (child) => child && child.props && (child.props as Record<string, string>).value === value,
  );

  return (
    <div
      role="tablist"
      className={cn("relative flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1", className)}
    >
      {activeIndex >= 0 ? (
        <motion.div
          layoutId="tab-indicator"
          className="absolute inset-y-1 rounded-md bg-background shadow-sm"
          style={{ left: `calc(${activeIndex * 100}% / ${items.length} + 2px)`, width: `calc(${100 / items.length}% - 4px)` }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
        />
      ) : null}
      {children}
    </div>
  );
}

export function TabsTrigger({ value, className, children }: { value: string; className?: string; children: ReactNode }) {
  const { value: active, setValue } = useTabs();
  const selected = active === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={() => setValue(value)}
      className={cn(
        "relative z-10 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        selected ? "text-foreground" : "text-muted-foreground hover:text-foreground",
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, className, children }: { value: string; className?: string; children: ReactNode }) {
  const { value: active } = useTabs();
  if (active !== value) return null;
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={value}
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ type: "spring", stiffness: 260, damping: 24 }}
        role="tabpanel"
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
