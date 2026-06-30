import { SkeletonCard, SkeletonKPIRow, SkeletonChart } from "@/components/ui/skeleton";

export default function Loading() {
  return (
    <div className="flex min-h-screen overflow-x-hidden bg-transparent">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r bg-background xl:w-72 lg:block">
        <div className="flex h-full flex-col gap-2 p-4">
          <div className="mb-4 h-8 w-32 animate-pulse rounded bg-muted" />
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-5 w-full animate-pulse rounded bg-muted/60" />
          ))}
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64 xl:pl-72">
        <header className="flex h-14 items-center gap-4 border-b px-4 md:px-6">
          <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />
          <div className="h-5 w-48 animate-pulse rounded bg-muted" />
          <div className="ml-auto h-8 w-8 animate-pulse rounded-full bg-muted" />
        </header>
        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 space-y-6 p-4 md:p-6">
          <SkeletonKPIRow count={4} />
          <div className="grid gap-6 lg:grid-cols-2">
            <SkeletonChart />
            <SkeletonChart />
          </div>
          <SkeletonCard rows={4} />
        </main>
      </div>
    </div>
  );
}
