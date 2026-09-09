"""全局一对一参考事实匹配，先最大化覆盖，再最小化分级配对代价。"""


def _assignment_path(costs, row, matched, left_prices, right_prices):
    width = len(matched)
    distance = [float("inf")] * width
    previous = [0] * width
    visited = [False] * width
    matched[0] = row
    column = 0
    while True:
        visited[column] = True
        left = matched[column]
        for candidate in range(1, width):
            if visited[candidate]:
                continue
            cost = (
                costs[left - 1][candidate - 1]
                - left_prices[left]
                - right_prices[candidate]
            )
            if cost < distance[candidate]:
                distance[candidate] = cost
                previous[candidate] = column
        next_column = min(
            (candidate for candidate in range(1, width) if not visited[candidate]),
            key=lambda candidate: distance[candidate],
        )
        delta = distance[next_column]
        for candidate in range(width):
            if visited[candidate]:
                left_prices[matched[candidate]] += delta
                right_prices[candidate] -= delta
            else:
                distance[candidate] -= delta
        column = next_column
        if not matched[column]:
            return column, previous


def minimum_rank_matching(row_count: int, column_count: int, edges: list) -> dict:
    if not edges:
        return {}
    # 每个高优先级分量的权重，超过所有低优先级分量在整份样本中的总和。
    limits = [
        max(rank[index] for rank, _, _ in edges) for index in range(len(edges[0][0]))
    ]
    weights = [1] * len(limits)
    for index in range(len(limits) - 2, -1, -1):
        weights[index] = weights[index + 1] * (row_count * limits[index + 1] + 1)
    edge_costs = {
        (row, column): sum(
            value * weight for value, weight in zip(rank, weights, strict=True)
        )
        for rank, row, column in edges
    }
    unmatched = (max(edge_costs.values()) + 1) * (row_count + 1)
    forbidden = unmatched * (row_count + 1)
    costs = [
        [edge_costs.get((row, column), forbidden) for column in range(column_count)]
        + [unmatched] * row_count
        for row in range(row_count)
    ]
    matched = [0] * (column_count + row_count + 1)
    left_prices = [0] * (row_count + 1)
    right_prices = [0] * len(matched)
    for row in range(1, row_count + 1):
        column, previous = _assignment_path(
            costs, row, matched, left_prices, right_prices
        )
        while column:
            predecessor = previous[column]
            matched[column] = matched[predecessor]
            column = predecessor
    return {
        matched[column] - 1: column - 1
        for column in range(1, column_count + 1)
        if matched[column] and (matched[column] - 1, column - 1) in edge_costs
    }
