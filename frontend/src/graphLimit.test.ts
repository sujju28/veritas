import { describe, expect, it } from "vitest";
import { capGraph, GRAPH_NODE_CAP } from "./graphLimit";

describe("graph node cap", () => {
  it("keeps at most 100 nodes and drops edges outside that set", () => {
    const nodes = Array.from({ length: 140 }, (_, index) => `acct-${index}`);
    const edges = [
      {
        transaction_id: "txn-kept",
        from_account_id: "acct-0",
        to_account_id: "acct-1",
        amount_minor: 10,
        event_time: "2026-01-15T09:00:00Z",
      },
      {
        transaction_id: "txn-dropped",
        from_account_id: "acct-0",
        to_account_id: "acct-120",
        amount_minor: 10,
        event_time: "2026-01-15T09:00:01Z",
      },
    ];
    const view = capGraph(nodes, edges, 500);
    expect(view.nodes).toHaveLength(GRAPH_NODE_CAP);
    expect(view.truncated).toBe(true);
    expect(view.edges.map((edge) => edge.transaction_id)).toEqual(["txn-kept"]);
  });
});
