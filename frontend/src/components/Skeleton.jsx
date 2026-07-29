/**
 * Shimmer placeholders used while data is in flight.
 *
 * Every skeleton mirrors the shape of the content it stands in for — same
 * grid, same tile count, same heights — so the layout does not jump when the
 * real payload lands. Spinners are deliberately avoided here: on a dense
 * board they give no sense of what is about to appear.
 */

export function Skeleton({ w, h, radius, className = "", style }) {
  return (
    <span
      className={["skeleton", className].filter(Boolean).join(" ")}
      aria-hidden="true"
      style={{
        width: w,
        height: h,
        borderRadius: radius,
        ...style,
      }}
    />
  );
}

/** A stack of text lines with a ragged last line, like a real paragraph. */
export function SkeletonLines({ lines = 3, className = "" }) {
  return (
    <span
      className={["skeleton-lines", className].filter(Boolean).join(" ")}
      aria-hidden="true"
    >
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          h={9}
          w={index === lines - 1 ? "62%" : "100%"}
        />
      ))}
    </span>
  );
}

/** Sidebar agent rows — matches `.agent-button` (avatar + two text lines). */
export function AgentListSkeleton({ rows = 3, label = "Loading agents" }) {
  return (
    <div className="agent-list agent-list-skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="agent-skeleton">
          <Skeleton className="agent-skeleton-avatar" w={38} h={38} radius={12} />

          <span className="agent-skeleton-copy">
            <Skeleton h={10} w={`${68 - index * 6}%`} />
            <Skeleton h={8} w={`${88 - index * 8}%`} />
          </span>
        </div>
      ))}
    </div>
  );
}

/** Stacked-card placeholder for list panels (alerts, subagents, history). */
export function ListSkeleton({ rows = 3, label = "Loading" }) {
  return (
    <div className="list-skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="list-skeleton-row">
          <span className="list-skeleton-copy">
            <Skeleton h={9} w={`${58 + (index % 3) * 11}%`} />
            <Skeleton h={7} w={`${84 - (index % 3) * 9}%`} />
          </span>

          <Skeleton h={18} w={62} radius={999} />
        </div>
      ))}
    </div>
  );
}

/**
 * Whole-board placeholder: KPI strip, focus + side panels, what-if bar.
 * Rendered in place of the four workboard rows while the dashboard loads.
 */
export function DashboardSkeleton({ label = "Loading dashboard" }) {
  return (
    <div className="workboard-skeleton" role="status" aria-label={label}>
      <div className="kpi-row">
        {Array.from({ length: 5 }).map((_, index) => (
          <div key={index} className="kpi-tile-skeleton">
            <Skeleton h={8} w="52%" />
            <Skeleton h={19} w="70%" />
            <Skeleton h={8} w="40%" />
            <Skeleton h={22} w="100%" radius={6} />
          </div>
        ))}
      </div>

      <div className="workboard-mid">
        <div className="panel-skeleton">
          <PanelHead />
          <ChartSkeleton bars={7} />
        </div>

        <div className="side-col">
          <div className="panel-skeleton">
            <PanelHead compact />
            <ChartSkeleton bars={5} />
          </div>

          <div className="panel-skeleton">
            <PanelHead compact />
            <ChartSkeleton bars={5} />
          </div>
        </div>
      </div>

      <div className="whatif-skeleton">
        <div className="whatif-skeleton-top">
          <Skeleton h={12} w={130} />
          <Skeleton h={26} w={150} radius={8} />
        </div>

        <div className="whatif-skeleton-grid">
          <div className="whatif-skeleton-levers">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="whatif-skeleton-lever">
                <Skeleton h={8} w="58%" />
                <Skeleton h={12} w="100%" radius={6} />
              </div>
            ))}
          </div>

          <WhatIfStatsSkeleton />

          <WhatIfGaugeSkeleton />
        </div>
      </div>
    </div>
  );
}

/** Scenario stat tiles + comparison chart, used while a simulation reruns. */
export function WhatIfStatsSkeleton() {
  return (
    <div className="whatif-stats whatif-stats-skeleton" role="status" aria-label="Recalculating scenario">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="whatif-stat-skeleton">
          <Skeleton h={7} w="72%" />
          <Skeleton h={15} w="54%" />
          <Skeleton h={7} w="46%" />
        </div>
      ))}

      <div className="whatif-mini-chart whatif-mini-chart-skeleton">
        <ChartSkeleton bars={2} />
      </div>
    </div>
  );
}

export function WhatIfGaugeSkeleton() {
  return (
    <div className="whatif-gauge-skeleton" aria-hidden="true">
      <Skeleton className="gauge-skeleton-ring" w={88} h={88} radius="50%" />
      <Skeleton h={8} w={92} />
    </div>
  );
}

/** Chat "thinking" placeholder — replaces the old spinner row. */
export function ThinkingSkeleton({ text = "Working" }) {
  return (
    <li className="thinking-skeleton" role="status" aria-live="polite">
      <span className="thinking-skeleton-avatar" aria-hidden="true">
        AI
      </span>

      <span className="thinking-skeleton-body">
        <span className="thinking-skeleton-label">
          {text}
          <span className="thinking-dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
        </span>

        <SkeletonLines lines={3} />
      </span>
    </li>
  );
}

function PanelHead({ compact = false }) {
  return (
    <div className="panel-skeleton-head">
      <Skeleton h={compact ? 9 : 11} w={compact ? "44%" : "34%"} />

      {compact ? null : <Skeleton h={9} w={64} radius={999} />}
    </div>
  );
}

/** Bar-chart silhouette: a baseline with columns of varied height. */
function ChartSkeleton({ bars = 6 }) {
  const heights = [58, 82, 44, 96, 68, 88, 52, 76];

  return (
    <div className="chart-skeleton" aria-hidden="true">
      <div className="chart-skeleton-bars">
        {Array.from({ length: bars }).map((_, index) => (
          <Skeleton
            key={index}
            className="chart-skeleton-bar"
            h={`${heights[index % heights.length]}%`}
            radius="4px 4px 0 0"
          />
        ))}
      </div>

      <span className="chart-skeleton-axis" />
    </div>
  );
}
