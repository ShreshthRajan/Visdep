import json
import networkx as nx
from backend.api.graph_generator import create_dependency_graph, save_graph_as_json, load_graph_from_json

def test_create_dependency_graph():
    ast_data = {
        "file1.py": {
            "functions": ["func1", "func2"],
            "classes": ["Class1"],
            "imports": ["import1"]
        },
        "file2.py": {
            "functions": ["func3"],
            "classes": ["Class2"],
            "imports": ["import2"]
        }
    }
    graph = create_dependency_graph(ast_data)
    assert isinstance(graph, nx.DiGraph)
    assert len(graph.nodes) == 9  # 2 files, 3 functions, 2 classes, 2 imports
    assert len(graph.edges) == 7  # Each file contains functions, classes, and imports

def test_save_and_load_graph():
    graph = nx.DiGraph()
    graph.add_node("file1.py", type="file", label="file1.py")
    graph.add_edge("file1.py", "file1.py::func1", relation="contains")

    save_graph_as_json(graph, "test_graph.json")
    loaded_graph = load_graph_from_json("test_graph.json")
    
    assert nx.is_isomorphic(graph, loaded_graph)
