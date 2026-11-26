from math import fsum


def dot(a, b):
    return fsum(x * y for x, y in zip(a, b))


def solve(system, target):
    rows = [list(row) + [value] for row, value in zip(system, target)]
    dimension = len(rows)
    for column in range(dimension):
        pivot = max(range(column, dimension), key=lambda ix: abs(rows[ix][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        scalar = rows[column][column]
        if abs(scalar) < 1e-11:
            raise ValueError("历史读数无法分离出独立的估计系数")
        rows[column] = [v / scalar for v in rows[column]]
        for other in range(dimension):
            if other != column:
                ratio = rows[other][column]
                rows[other] = [v - ratio * w for v, w in zip(rows[other], rows[column])]
    return tuple(row[-1] for row in rows)


def penalized_fit(design, labels, weights, penalty):
    columns = list(zip(*design))
    gram = []
    cross = []
    for i, left in enumerate(columns):
        gram.append(
            [
                fsum(w * x * y for w, x, y in zip(weights, left, right))
                + (penalty if i == j and i else 0.0)
                for j, right in enumerate(columns)
            ]
        )
        cross.append(fsum(w * x * y for w, x, y in zip(weights, left, labels)))
    return solve(gram, cross)
