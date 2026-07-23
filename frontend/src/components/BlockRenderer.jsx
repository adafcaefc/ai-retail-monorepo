import ChartRenderer from "./ChartRenderer.jsx";
import SimulationRenderer from "./SimulationRenderer.jsx";


export default function BlockRenderer({
  block
}) {
  if (!block) {
    return null;
  }

  switch (block.type) {
    case "html":
      return (
        <HtmlBlock
          data={block.data}
        />
      );

    case "chart":
      return (
        <ChartRenderer
          data={block.data || {}}
        />
      );

    case "simulation":
      return (
        <SimulationRenderer
          data={block.data || {}}
        />
      );

    case "next_route":
      return (
        <JsonBlock
          title="Suggested next route"
          data={block.data}
        />
      );

    default:
      return (
        <JsonBlock
          title={
            `Unsupported block: ${
              block.type ||
              "unknown"
            }`
          }
          data={block}
        />
      );
  }
}


function HtmlBlock({
  data
}) {
  const html =
    data?.html || "";

  if (!html) {
    return null;
  }

  return (
    <div
      className="rendered-html"

      dangerouslySetInnerHTML={{
        __html: html
      }}
    />
  );
}


function JsonBlock({
  title,
  data
}) {
  return (
    <section className="json-block">
      <strong>
        {title}
      </strong>

      <pre>
        {JSON.stringify(
          data,
          null,
          2
        )}
      </pre>
    </section>
  );
}