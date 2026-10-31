import { EmptyState } from "@/components/ui/primitives";

export function LiveStreamPage() {
  return (
    <div className="p-6">
      <h1 className="mb-4 text-lg font-semibold">Live stream</h1>
      <EmptyState title="Real-time replay is not available yet">
        The replay service (Phase 7) will stream the dataset's real rows in timestamp order. No rows are simulated, so this page stays empty until that service is running.
      </EmptyState>
    </div>
  );
}
