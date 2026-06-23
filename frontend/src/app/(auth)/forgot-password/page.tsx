"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { authService } from "@/services/auth.service";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const normalized = email.trim();
    if (!normalized || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(normalized)) {
      setError("Enter a valid email address.");
      return;
    }
    setLoading(true);
    try {
      const data = await authService.forgotPassword({ email: normalized });
      setMessage(data.message);
    } catch {
      setError("We could not process the request. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Reset password</CardTitle>
        <p className="text-sm text-muted-foreground">Enter your email and we will send reset instructions if an account exists.</p>
      </CardHeader>
      <CardContent>
        <form className="space-y-4" onSubmit={submit}>
          <label><span className="sr-only">Email</span><Input id="reset-email" type="email" placeholder="Email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          {message ? <p className="rounded-md bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">{message}</p> : null}
          {error ? <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-200">{error}</p> : null}
          <Button className="w-full" type="submit" disabled={loading}>{loading ? "Sending..." : "Send reset link"}</Button>
        </form>
        <Link href="/login" className="block text-sm text-muted-foreground hover:text-foreground">Back to sign in</Link>
      </CardContent>
    </Card>
  );
}
