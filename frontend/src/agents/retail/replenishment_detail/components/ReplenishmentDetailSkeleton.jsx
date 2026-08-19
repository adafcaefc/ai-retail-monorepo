import { Skeleton } from "../../../../components/Skeleton.jsx";

/**
 * The board's shape before its rows arrive.
 *
 * Matched to the real layout — filter row, six tiles, grid — so the page does
 * not jump when the payload lands. A generic spinner would reflow everything
 * the moment it is replaced.
 */
export default function ReplenishmentDetailSkeleton() {
  return (
    <div className="rdet-skeleton" aria-label="Loading Replenishment Detail">
      <div className="rdet-skeleton-filters">
        {Array.from({ length: 8 }, (_, index) => (
          <Skeleton key={index} h={38} radius={6} />
        ))}
      </div>

      <div className="rdet-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => (
          <Skeleton key={index} h={92} radius={10} />
        ))}
      </div>

      <Skeleton h={26} w="40%" radius={6} />
      <Skeleton h={420} radius={10} />
    </div>
  );
}
