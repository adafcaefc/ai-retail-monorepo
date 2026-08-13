import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * Mirrors the real layout tile for tile, so nothing shifts when the payload
 * lands: filter bar, six KPIs, the main requirement chart, the two-panel row,
 * the dimension row, then the purchase order.
 */
export default function ReplenishmentSkeleton() {
  return (
    <div
      className="po-dashboard-skeleton"
      role="status"
      aria-label="Loading Replenishment dashboard"
    >
      <Skeleton h={68} w="100%" radius={12} />

      <div className="po-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={104} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={340} w="100%" radius={12} />

      <div className="po-skeleton-panels">
        <Skeleton h={320} w="100%" radius={12} />
        <Skeleton h={320} w="100%" radius={12} />
      </div>

      <div className="po-skeleton-dims">
        {Array.from({ length: 3 }, (_, index) => (
          <Skeleton key={index} h={240} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={360} w="100%" radius={12} />
    </div>
  );
}
