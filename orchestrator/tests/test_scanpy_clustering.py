"""Real tests for app/tools/scanpy_clustering.py -- no mocking, runs the
real Scanpy QC/normalize/PCA/neighbors/Leiden pipeline."""
import random

from app.tools.scanpy_clustering import cluster_expression_matrix

random.seed(0)
N_CELLS = 30
N_GENES = 20


def _make_matrix():
    return [[float(random.randint(0, 8)) for _ in range(N_GENES)] for _ in range(N_CELLS)]


async def text_of(result):
    return result["content"][0]["text"]


async def test_happy_path_clusters_real_matrix():
    result = await cluster_expression_matrix.handler({"expression_matrix": _make_matrix()})
    text = await text_of(result)
    assert "Scanpy clustering" in text
    assert "[scanpy:leiden]" in text
    assert "cluster" in text


async def test_too_few_cells_reports_error():
    result = await cluster_expression_matrix.handler({"expression_matrix": _make_matrix()[:5]})
    text = await text_of(result)
    assert "at least 10 cell rows" in text


async def test_mismatched_gene_names_reports_error():
    result = await cluster_expression_matrix.handler({"expression_matrix": _make_matrix(), "gene_names": ["a", "b"]})
    text = await text_of(result)
    assert "must match the matrix dimensions" in text


async def test_missing_input_reports_error():
    result = await cluster_expression_matrix.handler({})
    text = await text_of(result)
    assert "expression_matrix must be" in text
