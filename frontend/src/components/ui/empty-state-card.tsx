"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface EmptyAction {
  label: string;
  href?: string;
  onClick?: () => void;
  icon?: typeof Search;
  variant?: "default" | "outline";
}

interface EmptyStateCardProps {
  icon?: typeof Search;
  title: string;
  description: string;
  actions?: EmptyAction[];
  children?: ReactNode;
}

export function EmptyStateCard({ icon: Icon = Search, title, description, actions }: EmptyStateCardProps) {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-4 p-8 text-center sm:p-12">
        <motion.span
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 15 }}
          className="grid h-14 w-14 place-items-center rounded-2xl bg-primary/10 text-primary"
        >
          <Icon className="h-7 w-7" />
        </motion.span>
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <h2 className="text-lg font-semibold">{title}</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
        </motion.div>
        {actions && actions.length > 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="flex flex-wrap justify-center gap-2"
          >
            {actions.map((action) => {
              const ActionIcon = action.icon ?? Search;
              const btn = (
                <Button key={action.label} variant={action.variant ?? "default"} onClick={action.onClick}>
                  <ActionIcon className="h-4 w-4" />
                  {action.label}
                </Button>
              );
              return action.href ? <Link key={action.label} href={action.href}>{btn}</Link> : btn;
            })}
          </motion.div>
        ) : null}
      </CardContent>
    </Card>
  );
}
