"""Directed-graph features for one evaluated transfer."""

from __future__ import annotations

from typing import Any

from veritas.graph.window import Transfer, slice_since

FEATURE_SCHEMA = "features-v1"
MAX_HOPS = 4


def feature_snapshot(
    transfers: list[Transfer],
    *,
    transaction_id: str,
    source: str,
    destination: str,
    as_of: str,
    truncated: bool,
) -> dict[str, Any]:
    window_15 = slice_since(transfers, as_of, minutes=15)
    onward = _onward_ratio(window_15, source, as_of)
    features: dict[str, Any] = {
        "src_in_count_15m": _count(window_15, source, incoming=True),
        "src_out_count_15m": _count(window_15, source, incoming=False),
        "src_in_count_1h": _count(transfers, source, incoming=True),
        "src_out_count_1h": _count(transfers, source, incoming=False),
        "dst_in_count_15m": _count(window_15, destination, incoming=True),
        "dst_out_count_15m": _count(window_15, destination, incoming=False),
        "dst_in_count_1h": _count(transfers, destination, incoming=True),
        "dst_out_count_1h": _count(transfers, destination, incoming=False),
        "src_amount_out_15m": _amount(window_15, source, incoming=False),
        "src_amount_out_1h": _amount(transfers, source, incoming=False),
        "dst_amount_in_15m": _amount(window_15, destination, incoming=True),
        "dst_amount_in_1h": _amount(transfers, destination, incoming=True),
        "src_fan_out_15m": _distinct(window_15, source, incoming=False),
        "dst_fan_in_15m": _distinct(window_15, destination, incoming=True),
        "src_onward_ratio_15m": onward,
        "src_upstream_hops": _upstream_hops(transfers, source),
        "window_edge_count": len(transfers),
        "window_truncated": truncated,
    }
    return {
        "schema_version": FEATURE_SCHEMA,
        "transaction_id": transaction_id,
        "as_of": as_of,
        "features": features,
    }


def _count(transfers: list[Transfer], account: str, *, incoming: bool) -> int:
    if incoming:
        return sum(1 for item in transfers if item.to_account_id == account)
    return sum(1 for item in transfers if item.from_account_id == account)


def _amount(transfers: list[Transfer], account: str, *, incoming: bool) -> int:
    if incoming:
        return sum(item.amount_minor for item in transfers if item.to_account_id == account)
    return sum(item.amount_minor for item in transfers if item.from_account_id == account)


def _distinct(transfers: list[Transfer], account: str, *, incoming: bool) -> int:
    if incoming:
        return len({item.from_account_id for item in transfers if item.to_account_id == account})
    return len({item.to_account_id for item in transfers if item.from_account_id == account})


def _onward_ratio(transfers: list[Transfer], source: str, as_of: str) -> float | None:
    inbound = sum(
        item.amount_minor
        for item in transfers
        if item.to_account_id == source and item.event_time < as_of
    )
    if inbound == 0:
        return None
    outbound = sum(
        item.amount_minor
        for item in transfers
        if item.from_account_id == source and item.event_time <= as_of
    )
    return round(outbound / inbound, 4)


def _upstream_hops(transfers: list[Transfer], source: str) -> int:
    import networkx as nx

    graph = nx.DiGraph()
    for item in transfers:
        graph.add_edge(item.to_account_id, item.from_account_id)
    if source not in graph:
        return 0
    lengths = nx.single_source_shortest_path_length(graph, source, cutoff=MAX_HOPS)
    return max(lengths.values(), default=0)


def bounded_subgraph(
    transfers: list[Transfer],
    *,
    source: str,
    destination: str,
    max_nodes: int,
    max_edges: int,
) -> dict[str, Any]:
    nodes = [source]
    if destination not in nodes:
        nodes.append(destination)
    hit_cap = False
    for item in reversed(transfers):
        for account in (item.from_account_id, item.to_account_id):
            if account in nodes:
                continue
            if len(nodes) >= max_nodes:
                hit_cap = True
                break
            nodes.append(account)
        if hit_cap:
            break
    allowed = set(nodes[:max_nodes])
    edges = []
    for item in transfers:
        if item.from_account_id in allowed and item.to_account_id in allowed:
            edges.append(
                {
                    "transaction_id": item.transaction_id,
                    "from_account_id": item.from_account_id,
                    "to_account_id": item.to_account_id,
                    "amount_minor": item.amount_minor,
                    "event_time": item.event_time,
                }
            )
            if len(edges) >= max_edges:
                break
    return {
        "nodes": [account for account in nodes if account in allowed],
        "edges": edges,
        "truncated": hit_cap or len(edges) >= max_edges,
    }
