import { Skeleton } from "../../../../components/Skeleton.jsx";

export default function DemandForecastingSkeleton() {
  return (
    <div className="demand-dashboard-skeleton" role="status" aria-label="Loading Demand Forecasting dashboard">
      <Skeleton h={68} w="100%" radius={12} />
      <div className="demand-skeleton-kpis">
        {Array.from({ length: 6 }, (_, index) => <Skeleton key={index} h={112} w="100%" radius={12} />)}
      </div>
      <div className="demand-skeleton-panels">
        <Skeleton h={360} w="100%" radius={12} />
        <Skeleton h={360} w="100%" radius={12} />
      </div>
      <Skeleton h={320} w="100%" radius={12} />
    </div>
  );
}
