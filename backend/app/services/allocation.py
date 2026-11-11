"""Bounded lower-bound flow: exact type totals and at least one primary question per point."""
from collections import deque

TYPES = ('choice', 'fill', 'answer')


def allocate(context, counts):
    # context[point][kind] = version/max_count/exact_capacity. No math generation or DB writes.
    if sum(counts.values()) < len(context):
        return None
    source, sink, super_source, super_sink = 'source', 'sink', 'super-source', 'super-sink'
    graph, demands, edges = {}, {}, {}
    def edge(a, b, capacity):
        graph.setdefault(a, []); graph.setdefault(b, [])
        forward = [b, capacity, len(graph[b])]
        backward = [a, 0, len(graph[a])]
        graph[a].append(forward); graph[b].append(backward)
        return forward
    def bounded(a, b, lower, upper):
        if upper < lower:
            return None
        demands[a] = demands.get(a, 0) - lower
        demands[b] = demands.get(b, 0) + lower
        return edge(a, b, upper - lower)
    for kind in TYPES:
        bounded(source, kind, counts[kind], counts[kind])
    for point, cells in sorted(context.items()):
        active = {k: c for k, c in cells.items() if counts[k] > 0}
        if not active:
            return None
        # Conservative joint dedupe capacity: each chosen template has at least this many candidates.
        budget = min(c['exact_capacity'] for c in active.values())
        if budget < 1:
            return None
        bounded(point, sink, 1, min(36, budget))
        for kind, cell in active.items():
            limit = min(counts[kind], cell['max_count'])
            edges[point, kind] = (edge(kind, point, limit), limit)
    edge(sink, source, 36)
    needed = 0
    for node, demand in list(demands.items()):
        if demand > 0:
            edge(super_source, node, demand); needed += demand
        elif demand < 0:
            edge(node, super_sink, -demand)
    flow = 0
    while flow < needed:
        parents = {super_source: None}; queue = deque([super_source])
        while queue and super_sink not in parents:
            node = queue.popleft()
            for index, (target, remaining, _) in enumerate(graph.get(node, [])):
                if remaining > 0 and target not in parents:
                    parents[target] = (node, index); queue.append(target)
        if super_sink not in parents:
            return None
        amount, node = needed - flow, super_sink
        while node != super_source:
            parent, index = parents[node]; amount = min(amount, graph[parent][index][1]); node = parent
        node = super_sink
        while node != super_source:
            parent, index = parents[node]; forward = graph[parent][index]
            forward[1] -= amount; graph[node][forward[2]][1] += amount; node = parent
        flow += amount
    result = [{'point_id': point, 'kind': kind, 'count': limit - remaining[1], 'version_id': context[point][kind]['version_id']}
            for kind in TYPES for point in sorted(context)
            if (point, kind) in edges for remaining, limit in [edges[point, kind]] if limit - remaining[1] > 0]

    if result and sum(counts.values()) > min(context[p['point_id']][p['kind']]['exact_capacity'] for p in result):
        return None
    return result
