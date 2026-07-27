export default function RouteRenderer({ data }) {
  if (!data?.routes?.length) {
    return null;
  }

  return (
    <section className="route-block">
      <h2 className="route-block-title">
        {data.title}
      </h2>

      <div className="route-list">
        {data.routes.map((route, index) => {
          const destination =
            route.destination?.toLowerCase() || "";

          const isAgent =
            destination.includes("agent");

          return (
            <div
              key={index}
              className={
                `route-item ${
                  isAgent
                    ? "route-item--agent"
                    : ""
                }`
              }
            >
              <div className="route-destination">
                {route.destination}
              </div>

              <div className="route-reason">
                {route.reason}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}