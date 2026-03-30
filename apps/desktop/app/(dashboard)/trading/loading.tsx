import { Skeleton } from "@/components/ui/skeleton"

export default function Loading() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Skeleton className="h-32 rounded-xl border border-border bg-card" />
        <Skeleton className="h-32 rounded-xl border border-border bg-card" />
        <Skeleton className="h-32 rounded-xl border border-border bg-card" />
      </div>
      <Skeleton className="h-[400px] w-full rounded-xl border border-border bg-card" />
    </div>
  )
}
