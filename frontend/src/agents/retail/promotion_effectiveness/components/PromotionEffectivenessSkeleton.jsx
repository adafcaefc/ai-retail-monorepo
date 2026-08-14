import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * Mirrors the real layout tile for tile, so nothing shifts when the payload
 * lands: filter bar, six KPIs, the main chart, the two-panel chart row, the
 * campaign calendar, and the margin leaders list.
 */
export default function PromotionEffectivenessSkeleton() {
  return (
    <div
      className="promo-dashboard-skeleton"
      role="status"
      aria-label="Loading Promotion Effectiveness dashboard"
    >
      <Skeleton h={68} w="100%" radius={12} />

      <div className="promo-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={104} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={300} w="100%" radius={12} />

      <div className="promo-skeleton-panels">
        <Skeleton h={260} w="100%" radius={12} />
        <Skeleton h={260} w="100%" radius={12} />
      </div>

      <Skeleton h={360} w="100%" radius={12} />
    </div>
  );
}
