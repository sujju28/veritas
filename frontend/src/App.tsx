import { useEffect, useState } from "react";
import { ApiFailure, apiRequest } from "./api";
import { GraphPanel } from "./GraphPanel";
import type { GraphEdge } from "./graphLimit";
import { StatusTagView } from "./StatusTag";

type View = "overview" | "transactions" | "graph" | "decision" | "receipt";

interface Scenario {
  scenario_id: string;
  seed?: number;
  scale?: string;
  account_count?: number;
  transaction_count?: number;
  content_sha256?: string;
  ground_truth_rows?: number;
}

interface TransactionItem {
  transaction_id: string;
  from_account_id: string;
  to_account_id: string;
  amount_minor: number;
  event_time: string;
  currency: string;
}

interface Decision {
  decision_id: string;
  transaction_id: string;
  risk_score: number;
  decision: string;
  score_kind: string;
  reason_codes: string[];
  ruleset_version: string;
  model_version: string;
  features: Record<string, string | number | boolean | null>;
  triggered_rules: { code: string; feature: string; value: unknown; threshold: unknown }[];
  anchor_status: string;
  receipt_status: string;
}

interface Receipt {
  payload: {
    decision_id: string;
    transaction_id: string;
    bank_id: string;
    decision: string;
    risk_score: number;
    reason_codes: string[];
    feature_snapshot_sha256: string;
    model_version: string;
    ruleset_version: string;
    decision_timestamp: string;
  };
  digest_hex: string;
  signature_b64: string;
  signing_key_id: string;
  signature_algorithm: string;
}

interface Anchor {
  anchor_status: string;
  outbox_status: string | null;
  error_category: string | null;
  tx_hash: string | null;
  block_number: number | null;
}

interface VerifyResult {
  status: string;
  digest_hex?: string | null;
  stored: boolean;
}

function money(minor: number, currency: string): string {
  if (currency === "USD") return `${(minor / 100).toFixed(2)} USD (${minor} minor)`;
  return `${minor} ${currency} minor`;
}

export function App() {
  const [view, setView] = useState<View>("overview");
  const [error, setError] = useState<string | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [health, setHealth] = useState<string>("");
  const [transactions, setTransactions] = useState<TransactionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("txn-000007");
  const [nodes, setNodes] = useState<string[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [copyScore, setCopyScore] = useState(1);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [storedDigest, setStoredDigest] = useState<string>("");

  async function loadOverview() {
    setError(null);
    try {
      const ready = await apiRequest<{ status: string }>("/api/v1/health");
      const listed = await apiRequest<{ scenarios: Scenario[] }>("/api/v1/scenarios");
      setHealth(ready.status);
      setScenarios(listed.scenarios);
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "The overview could not be loaded.");
    }
  }

  async function loadTransactions(nextOffset: number) {
    setError(null);
    try {
      const page = await apiRequest<{ items: TransactionItem[]; total: number }>(
        `/api/v1/transactions?limit=50&offset=${nextOffset}`,
      );
      setTransactions(page.items);
      setTotal(page.total);
      setOffset(nextOffset);
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "Transactions could not be loaded.");
    }
  }

  async function loadGraph(transactionId: string) {
    setError(null);
    try {
      const graph = await apiRequest<{
        nodes: string[];
        edges: GraphEdge[];
        truncated: boolean;
      }>(`/api/v1/graph/subgraph?transaction_id=${transactionId}&max_nodes=100`);
      setNodes(graph.nodes);
      setEdges(graph.edges);
      setTruncated(graph.truncated);
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "The graph could not be loaded.");
    }
  }

  async function evaluate(transactionId: string) {
    setError(null);
    try {
      const body = await apiRequest<Decision>("/api/v1/decisions/evaluate", {
        method: "POST",
        body: JSON.stringify({
          transaction_id: transactionId,
          idempotency_key: `ui-${transactionId}`,
        }),
      });
      setDecision(body);
      setView("decision");
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "The decision could not be scored.");
    }
  }

  async function loadReceipt(decisionId: string) {
    setError(null);
    try {
      const body = await apiRequest<Receipt>(`/api/v1/decisions/${decisionId}/receipt`);
      const anchorBody = await apiRequest<Anchor>(`/api/v1/decisions/${decisionId}/anchor`);
      setReceipt(body);
      setAnchor(anchorBody);
      setStoredDigest(body.digest_hex);
      setView("receipt");
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "The receipt could not be loaded.");
    }
  }

  async function verifyCopy() {
    if (!receipt) return;
    const copy = structuredClone(receipt);
    copy.payload.risk_score = copyScore;
    setError(null);
    try {
      const result = await apiRequest<VerifyResult>("/api/v1/verify", {
        method: "POST",
        body: JSON.stringify(copy),
      });
      const stored = await apiRequest<Receipt>(`/api/v1/decisions/${receipt.payload.decision_id}/receipt`);
      setVerifyResult(result);
      setStoredDigest(stored.digest_hex);
      setReceipt(stored);
    } catch (exc) {
      setError(exc instanceof ApiFailure ? exc.message : "The copy could not be verified.");
    }
  }

  useEffect(() => {
    void loadOverview();
  }, []);

  return (
    <>
      <header>
        <h1>VERITAS demo</h1>
        <p>
          Synthetic local data. Anvil is a resettable development chain, not a permissioned QBFT
          ledger. Private keys are not shown.
        </p>
        <nav aria-label="Demo sections">
          {(
            [
              ["overview", "Overview"],
              ["transactions", "Transactions"],
              ["graph", "Graph"],
              ["decision", "Decision"],
              ["receipt", "Receipt"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              aria-current={view === id ? "page" : undefined}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
        </nav>
      </header>
      {error ? <p role="alert">{error}</p> : null}
      <main>
        {view === "overview" ? (
          <section aria-labelledby="overview-heading">
            <h2 id="overview-heading">Overview</h2>
            <p>API health: {health || "unknown"}</p>
            <button type="button" onClick={() => void loadOverview()}>
              Refresh
            </button>
            <table>
              <caption>Seeded scenarios from the API</caption>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((item) => (
                  <tr key={item.scenario_id}>
                    <td>{item.scenario_id}</td>
                    <td>
                      {item.account_count !== undefined
                        ? `${item.scale} seed ${item.seed}: ${item.account_count} accounts, ${item.transaction_count} transactions`
                        : `${item.ground_truth_rows ?? 0} planted rows`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}
        {view === "transactions" ? (
          <section aria-labelledby="tx-heading">
            <h2 id="tx-heading">Transactions</h2>
            <p>
              {total} transfers. Showing {transactions.length} from offset {offset}. Page size is 50.
            </p>
            <button type="button" onClick={() => void loadTransactions(offset)}>
              Load page
            </button>
            <button
              type="button"
              disabled={offset === 0}
              onClick={() => void loadTransactions(Math.max(0, offset - 50))}
            >
              Previous
            </button>
            <button
              type="button"
              disabled={offset + 50 >= total}
              onClick={() => void loadTransactions(offset + 50)}
            >
              Next
            </button>
            <table>
              <caption>Synthetic transfers</caption>
              <thead>
                <tr>
                  <th>Id</th>
                  <th>From</th>
                  <th>To</th>
                  <th>Amount</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {transactions.map((item) => (
                  <tr key={item.transaction_id}>
                    <td>
                      <button
                        type="button"
                        onClick={() => {
                          setSelected(item.transaction_id);
                          void evaluate(item.transaction_id);
                        }}
                      >
                        {item.transaction_id}
                      </button>
                    </td>
                    <td>{item.from_account_id}</td>
                    <td>{item.to_account_id}</td>
                    <td>{money(item.amount_minor, item.currency)}</td>
                    <td>{item.event_time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ) : null}
        {view === "graph" ? (
          <>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void loadGraph(selected);
              }}
            >
              <label>
                Transaction
                <input value={selected} onChange={(event) => setSelected(event.target.value)} />
              </label>
              <button type="submit">Load graph</button>
            </form>
            <GraphPanel nodes={nodes} edges={edges} truncated={truncated} />
          </>
        ) : null}
        {view === "decision" ? (
          <section aria-labelledby="decision-heading">
            <h2 id="decision-heading">Decision</h2>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void evaluate(selected);
              }}
            >
              <label>
                Transaction
                <input value={selected} onChange={(event) => setSelected(event.target.value)} />
              </label>
              <button type="submit">Score</button>
            </form>
            {decision ? (
              <>
                <p>
                  {decision.decision_id} score {decision.risk_score} ({decision.decision}).{" "}
                  {decision.score_kind}. Rules {decision.ruleset_version}. Model{" "}
                  {decision.model_version}.
                </p>
                <StatusTagView value={decision.anchor_status} />
                <table>
                  <caption>Triggered reason codes</caption>
                  <thead>
                    <tr>
                      <th>Code</th>
                      <th>Feature</th>
                      <th>Value</th>
                      <th>Threshold</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decision.triggered_rules.map((rule) => (
                      <tr key={`${rule.code}-${rule.feature}`}>
                        <td>{rule.code}</td>
                        <td>{rule.feature}</td>
                        <td>{String(rule.value)}</td>
                        <td>{String(rule.threshold)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <table>
                  <caption>Feature values</caption>
                  <tbody>
                    {Object.entries(decision.features).map(([name, value]) => (
                      <tr key={name}>
                        <th scope="row">{name}</th>
                        <td>{String(value)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button type="button" onClick={() => void loadReceipt(decision.decision_id)}>
                  Open receipt
                </button>
              </>
            ) : (
              <p>Score a transaction to see reason codes and features.</p>
            )}
          </section>
        ) : null}
        {view === "receipt" && receipt ? (
          <section aria-labelledby="receipt-heading">
            <h2 id="receipt-heading">Signed receipt</h2>
            <p>The stored receipt is read-only. The tamper control edits a copy in the browser.</p>
            <StatusTagView value={anchor?.anchor_status ?? "PENDING"} />
            {anchor?.error_category ? <StatusTagView value={anchor.error_category} /> : null}
            <dl>
              <dt>Decision</dt>
              <dd>{receipt.payload.decision_id}</dd>
              <dt>Score</dt>
              <dd>{receipt.payload.risk_score}</dd>
              <dt>Reasons</dt>
              <dd>{receipt.payload.reason_codes.join(", ") || "none"}</dd>
              <dt>Feature digest</dt>
              <dd>{receipt.payload.feature_snapshot_sha256}</dd>
              <dt>Receipt digest</dt>
              <dd>{storedDigest}</dd>
              <dt>Signer</dt>
              <dd>
                {receipt.signing_key_id} {receipt.signature_algorithm}
              </dd>
              <dt>Anchor transaction</dt>
              <dd>{anchor?.tx_hash ?? "none"}</dd>
              <dt>Block</dt>
              <dd>{anchor?.block_number ?? "none"}</dd>
            </dl>
            <label>
              Copy risk score
              <input
                type="number"
                min={0}
                max={100}
                value={copyScore}
                onChange={(event) => setCopyScore(Number(event.target.value))}
              />
            </label>
            <button type="button" onClick={() => void verifyCopy()}>
              Verify copy
            </button>
            {verifyResult ? (
              <p>
                Copy result <StatusTagView value={verifyResult.status} /> stored=
                {String(verifyResult.stored)}. Stored digest remains {storedDigest}.
              </p>
            ) : null}
          </section>
        ) : null}
      </main>
    </>
  );
}
