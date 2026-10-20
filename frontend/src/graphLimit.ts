export const GRAPH_NODE_CAP = 100;

export interface GraphEdge {
  transaction_id: string;
  from_account_id: string;
  to_account_id: string;
  amount_minor: number;
  event_time: string;
}

export function capGraph<TNode extends string>(
  nodes: TNode[],
  edges: GraphEdge[],
  cap = GRAPH_NODE_CAP,
): { nodes: TNode[]; edges: GraphEdge[]; truncated: boolean } {
  const limit = Math.min(Math.max(cap, 1), GRAPH_NODE_CAP);
  const kept = nodes.slice(0, limit);
  const allowed = new Set(kept);
  const visible = edges.filter(
    (edge) => allowed.has(edge.from_account_id as TNode) && allowed.has(edge.to_account_id as TNode),
  );
  return {
    nodes: kept,
    edges: visible,
    truncated: nodes.length > limit || edges.length > visible.length,
  };
}
