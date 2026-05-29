"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { toast } from "sonner";
import { authService } from "@/services/auth.service";
import { useAuthStore } from "@/stores/auth-store";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const schema = z.object({
  full_name: z.string().optional(),
  email: z.string().email(),
  password: z.string().min(8),
});

type AuthFormValues = z.infer<typeof schema>;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const setUser = useAuthStore((state) => state.setUser);
  const form = useForm<AuthFormValues>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "", full_name: "" } });
  const mutation = useMutation({
    mutationFn: (values: AuthFormValues) =>
      mode === "login"
        ? authService.login({ email: values.email, password: values.password })
        : authService.register({ email: values.email, password: values.password, full_name: values.full_name ?? "" }),
    onSuccess: (data) => {
      setUser(data.user);
      router.replace("/dashboard");
    },
    onError: (error) => toast.error(error.message),
  });

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>{mode === "login" ? "Sign in" : "Create account"}</CardTitle>
        <p className="text-sm text-muted-foreground">Access your opportunity intelligence workspace.</p>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
          {mode === "register" ? <Input placeholder="Full name" autoComplete="name" {...form.register("full_name")} /> : null}
          <Input placeholder="Email" type="email" autoComplete="email" {...form.register("email")} />
          <Input placeholder="Password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} {...form.register("password")} />
          <Button className="w-full" disabled={mutation.isPending}>
            {mutation.isPending ? "Working..." : mode === "login" ? "Sign in" : "Register"}
          </Button>
        </form>
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <Link href="/forgot-password" className="hover:text-foreground">Forgot password?</Link>
          <Link href={mode === "login" ? "/register" : "/login"} className="hover:text-foreground">
            {mode === "login" ? "Create account" : "Sign in"}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
