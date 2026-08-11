import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * Mirrors the real layout tile for tile, so nothing shifts when the payload
 * lands: filter bar, six KPIs, the two-panel chart row, the dimension row,
 * then the register.
 */
export default function InventoryRiskSkeleton() {
  return (
    <div
      className="risk-dashboard-skeleton"
      role="status"
      aria-label="Loading Inventory Risk dashboard"
    >
      <Skeleton h={68} w="100%" radius={12} />

      <div className="risk-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={104} w="100%" radius={12} />
        ))}
      </div>

      <div className="risk-skeleton-panels">
        <Skeleton h={320} w="100%" radius={12} />
        <Skeleton h={320} w="100%" radius={12} />
      </div>

      <div className="risk-skeleton-dims">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} h={240} w="100%" radius={12} />
        ))}
      </div>

      <Skeleton h={360} w="100%" radius={12} />
    </div>
  );
}
