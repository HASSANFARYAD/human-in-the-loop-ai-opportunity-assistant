"use client";

import Link from "next/link";
import { FormEvent, Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { authService } from "@/services/auth.service";

function passwordPolicyMessages(password: string) {
  const messages = [];
  if (password.length < 12) messages.push("Use at least 12 characters.");
  const classes = [
    /[a-z]/.test(password),
    /[A-Z]/.test(password),
    /\d/.test(password),
    /[^a-zA-Z0-9]/.test(password),
  ].filter(Boolean).length;
  if (classes < 3) messages.push("Include at least three of lowercase, uppercase, number, and symbol.");
  return messages;
}

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const policyMessages = useMemo(() => passwordPolicyMessages(password), [password]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    if (!token) {
      setError("This reset link is missing a token.");
      return;
    }
    if (policyMessages.length) {
      setError("The new password does not meet the password policy.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Password confirmation does not match.");
      return;
    }
    setLoading(true);
    try {
      const data = await authService.resetPassword({ token, password });
      setMessage(data.message);
      setPassword("");
      setConfirmPassword("");
    } catch {
      setError("This reset link is invalid, expired, or already used.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Choose new password</CardTitle>
        <p className="text-sm text-muted-foreground">Reset links expire and can only be used once.</p>
      </CardHeader>
      <CardContent>
        <form className="space-y-5" onSubmit={submit}>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">New password</span>
            <Input id="new-password" type="password" placeholder="New password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">Confirm password</span>
            <Input id="confirm-password" type="password" placeholder="Confirm password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} />
          </label>
          {password && policyMessages.length ? <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">{policyMessages.map((item) => <p key={item}>{item}</p>)}</div> : null}
          {message ? <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">{message} <Link href="/login" className="font-medium underline">Sign in</Link></p> : null}
          {error ? <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p> : null}
          <Button className="w-full" type="submit" loading={loading} disabled={!token}>Update password</Button>
        </form>
      </CardContent>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
