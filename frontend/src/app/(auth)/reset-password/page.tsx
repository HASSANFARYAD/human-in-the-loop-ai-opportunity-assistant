import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export default function ResetPasswordPage() {
  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Choose new password</CardTitle>
        <p className="text-sm text-muted-foreground">This screen is ready for a reset-token backend contract.</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <Input type="password" placeholder="New password" />
        <Input type="password" placeholder="Confirm password" />
        <Button className="w-full" disabled>Update password</Button>
      </CardContent>
    </Card>
  );
}
