"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

function validatePassword(password: string) {
  const classes = [/[a-z]/.test(password), /[A-Z]/.test(password), /\d/.test(password), /[^a-zA-Z0-9]/.test(password)].filter(Boolean).length;
  return password.length >= 12 && classes >= 3;
}

const schema = z.object({
  full_name: z.string().optional(),
  email: z.string().email(),
  password: z.string().refine(validatePassword, "Password must be at least 12 characters with at least three of: lowercase, uppercase, number, symbol"),
});

type AuthFormValues = z.infer<typeof schema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setUser = useAuthStore((state) => state.setUser);
  const form = useForm<AuthFormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "", full_name: "" } });
  const mutation = useMutation({
    mutationFn: (values: AuthFormValues) =>
      mode === "login"
        ? authService.login({ email: values.email, password: values.password })
        : authService.register({ email: values.email, password: values.password, full_name: values.full_name ?? "" }),
    onSuccess: (data) => {
      setUser(data.user);
      const next = searchParams.get("next");
      const safeNext = (() => {
        if (!next) return "/dashboard";
        try {
          const url = new URL(next, window.location.origin);
          return url.origin === window.location.origin ? url.pathname + url.search + url.hash : "/dashboard";
        } catch {
          return next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
        }
      })();
      router.replace(safeNext);
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      className="w-full max-w-md px-4 sm:px-0"
    >
      <Card>
        <CardHeader>
          <CardTitle>{mode === "login" ? "Sign in" : "Create account"}</CardTitle>
          <p className="text-sm text-muted-foreground">Access your opportunity intelligence workspace.</p>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
            {mode === "register" ? (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ type: "spring", stiffness: 260, damping: 24 }}
              >
                <label className="block space-y-1.5">
                  <span className="text-sm font-medium">Full name</span>
                  <Input id="auth-full-name" placeholder="Full name" autoComplete="name" {...form.register("full_name")} />
                </label>
              </motion.div>
            ) : null}
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Email</span>
              <Input id="auth-email" placeholder="you@example.com" type="email" autoComplete="email" {...form.register("email")} />
            </label>
            <label className="block space-y-1.5">
              <span className="text-sm font-medium">Password</span>
              <Input id="auth-password" placeholder="Enter your password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...form.register("password")} />
            </label>
            <Button className="w-full" loading={mutation.isPending}>
              {mode === "login" ? "Sign in" : "Register"}
            </Button>
          </form>
          <div className="mt-5 flex items-center justify-between text-sm text-muted-foreground">
            <Link href="/forgot-password" className="hover:text-foreground">Forgot password?</Link>
            <Link href={mode === "login" ? "/register" : "/login"} className="hover:text-foreground">
              {mode === "login" ? "Create account" : "Sign in"}
            </Link>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
