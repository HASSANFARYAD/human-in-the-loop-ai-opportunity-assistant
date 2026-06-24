export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,#312E81_0,#111827_42%,#0F172A_100%)] px-4 py-10 text-foreground sm:px-6">
      {children}
    </main>
  );
}
