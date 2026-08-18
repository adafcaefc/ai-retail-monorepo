import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * Mirrors the real layout tile for tile: filter bar, six KPIs, the main
 * chart, the two-panel chart row, and the candidate table.
 */
export default function PricingMarkdownSkeleton() {
  return (
    <div
      className="pricing-dashboard-skeleton"
      role="status"
      aria-label="Loading Pricing & Markdown dashboard"
    >
      <Skeleton h={68} w="100%" radius={12} />

      <div className="pricing-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={104} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={300} w="100%" radius={12} />

      <div className="pricing-skeleton-panels">
        <Skeleton h={260} w="100%" radius={12} />
        <Skeleton h={260} w="100%" radius={12} />
      </div>

      <Skeleton h={360} w="100%" radius={12} />
    </div>
  );
}
