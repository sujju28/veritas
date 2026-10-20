import cytoscape from "cytoscape";
import { useEffect, useMemo, useRef } from "react";
import { capGraph, GRAPH_NODE_CAP, type GraphEdge } from "./graphLimit";

export function GraphPanel({
  nodes,
  edges,
  truncated,
}: {
  nodes: string[];
  edges: GraphEdge[];
  truncated: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useMemo(() => capGraph(nodes, edges, GRAPH_NODE_CAP), [nodes, edges]);
  const showWarning = truncated || view.truncated;

  useEffect(() => {
    if (!host.current) return undefined;
    const cy = cytoscape({
      container: host.current,
      elements: [
        ...view.nodes.map((id) => ({ data: { id } })),
        ...view.edges.map((edge) => ({
          data: {
            id: edge.transaction_id,
            source: edge.from_account_id,
            target: edge.to_account_id,
          },
        })),
      ],
      layout: { name: "breadthfirst", directed: true },
      style: [
        {
          selector: "node",
          style: {
            label: "data(id)",
            "font-size": 10,
            "background-color": "#1f4b6e",
            color: "#102033",
            "text-valign": "bottom",
            "text-margin-y": 4,
          },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#6d7d8b",
            "target-arrow-color": "#6d7d8b",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
          },
        },
      ],
      userZoomingEnabled: true,
    });
    return () => cy.destroy();
  }, [view.nodes, view.edges]);

  return (
    <section aria-labelledby="graph-heading">
      <h2 id="graph-heading">Transaction graph</h2>
      <p>
        Showing {view.nodes.length} of {nodes.length} accounts. The hard limit is {GRAPH_NODE_CAP}{" "}
        nodes.
      </p>
      {showWarning ? (
        <p className="warning" role="alert">
          This graph is truncated. Later accounts and transfers are not drawn.
        </p>
      ) : null}
      <div ref={host} className="graph" aria-label="Directed transfer graph" />
    </section>
  );
}
