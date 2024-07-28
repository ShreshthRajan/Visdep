import networkx as nx
from typing import Dict, Any
from networkx.readwrite import json_graph
import json

def create_dependency_graph(ast_data: Dict[str, Any]) -> nx.DiGraph:
    """
    Create a dependency graph from parsed AST data.
    """
    G = nx.DiGraph()

    for file_path, file_info in ast_data.items():
        G.add_node(file_path, type="file", label=file_path)
        for func in file_info.get("functions", []):
            func_node = f"{file_path}::{func}"
            G.add_node(func_node, type="function", label=func)
            G.add_edge(file_path, func_node, relation="contains")

        for cls in file_info.get("classes", []):
            class_node = f"{file_path}::{cls}"
            G.add_node(class_node, type="class", label=cls)
            G.add_edge(file_path, class_node, relation="contains")

        for imp in file_info.get("imports", []):
            import_node = f"import::{imp}"
            G.add_node(import_node, type="import", label=imp)
            G.add_edge(file_path, import_node, relation="imports")

    return G

def save_graph_as_json(graph: nx.DiGraph, file_path: str) -> None:
    """
    Save the graph as a JSON file for later visualization.
    """
    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def load_graph_from_json(file_path: str) -> nx.DiGraph:
    """
    Load the graph from a JSON file.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data)