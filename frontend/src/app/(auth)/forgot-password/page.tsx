import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function ForgotPasswordPage() {
  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Reset password</CardTitle>
        <p className="text-sm text-muted-foreground">Password reset delivery requires a backend email endpoint.</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input type="email" placeholder="Email" />
        <Button className="w-full" disabled>Send reset link</Button>
        <Link href="/login" className="block text-sm text-muted-foreground hover:text-foreground">Back to sign in</Link>
      </CardContent>
    </Card>
  );
}
