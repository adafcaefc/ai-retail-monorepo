import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * Mirrors the real layout tile for tile: filter bar, six KPIs, the quadrant,
 * the two-panel chart row, and the action preview table.
 */
export default function AssortmentSkeleton() {
  return (
    <div
      className="assortment-dashboard-skeleton"
      role="status"
      aria-label="Loading Assortment Optimization dashboard"
    >
      <Skeleton h={68} w="100%" radius={12} />

      <div className="assortment-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={104} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={320} w="100%" radius={12} />

      <div className="assortment-skeleton-panels">
        <Skeleton h={260} w="100%" radius={12} />
        <Skeleton h={260} w="100%" radius={12} />
      </div>

      <Skeleton h={360} w="100%" radius={12} />
    </div>
  );
}
