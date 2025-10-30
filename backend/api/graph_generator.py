import os
import networkx as nx
from typing import Dict, Any, List
from networkx.readwrite import json_graph
import json
from collections import defaultdict
import logging


def create_chunk_level_graph(chunks: List[Dict[str, Any]]) -> nx.DiGraph:
    """
    Create dependency graph at chunk/method level for precise code navigation.

    This creates nodes for individual functions, methods, and classes (not just files).
    Node IDs match chunk IDs exactly, enabling method-level highlighting.

    Args:
        chunks: List of chunk dictionaries from database

    Returns:
        NetworkX DiGraph with hierarchical structure:
        - Level 1-2: Directories
        - Level 3: Files
        - Level 4: Functions + Class definitions
        - Level 5: Methods within classes
    """
    G = nx.DiGraph()

    if not chunks:
        logging.warning("No chunks provided to create_chunk_level_graph")
        return G

    logging.info(f"Creating chunk-level graph from {len(chunks)} chunks...")

    # Extract unique directories and files from chunks
    directories = set()
    files = set()
    class_definitions = {}  # {file_path: {class_name: chunk_id}}

    for chunk in chunks:
        file_path = chunk['file_path']
        files.add(file_path)

        # Extract directory hierarchy
        dir_path = os.path.dirname(file_path)
        while dir_path:
            directories.add(dir_path)
            dir_path = os.path.dirname(dir_path)

        # Track class definitions for parent-child edges
        if chunk['type'] == 'class_definition':
            if file_path not in class_definitions:
                class_definitions[file_path] = {}
            class_definitions[file_path][chunk['name']] = chunk['chunk_id']

    # Step 1: Add directory nodes
    for directory in directories:
        G.add_node(
            directory,
            type="directory",
            label=os.path.basename(directory) or directory,
            shape="box",
            level=directory.count('/') + 1
        )

    # Step 2: Add file nodes
    for file_path in files:
        G.add_node(
            file_path,
            type="file",
            label=os.path.basename(file_path),
            shape="ellipse",
            level=file_path.count('/') + 2
        )

    # Step 3: Add chunk nodes (functions, classes, methods)
    for chunk in chunks:
        chunk_id = chunk['chunk_id']
        chunk_type = chunk['type']
        name = chunk['name']
        file_path = chunk['file_path']

        # Determine level based on chunk type
        if chunk_type == 'method':
            level = 5  # Methods are deepest level
        elif chunk_type in ['function', 'class_definition']:
            level = 4  # Top-level functions and class defs
        elif chunk_type == 'module_variable':
            level = 4  # Module variables
        else:
            level = 4  # Default

        # Create node with chunk ID as node ID (enables highlighting!)
        G.add_node(
            chunk_id,
            type=chunk_type,
            label=name,
            shape=_get_shape_for_chunk_type(chunk_type),
            file=file_path,
            lines=f"{chunk.get('start_line', '?')}-{chunk.get('end_line', '?')}",
            parent_class=chunk.get('metadata', {}).get('parent_class'),
            level=level
        )

    # Step 4: Create edges (containment hierarchy)

    # Directory → subdirectory edges
    for directory in directories:
        subdirs = [d for d in directories if os.path.dirname(d) == directory]
        for subdir in subdirs:
            G.add_edge(directory, subdir, relation="contains")

    # Directory → file edges
    for directory in directories:
        for file_path in files:
            if os.path.dirname(file_path) == directory:
                G.add_edge(directory, file_path, relation="contains")

    # File → chunk edges (file contains functions/classes)
    for chunk in chunks:
        chunk_id = chunk['chunk_id']
        file_path = chunk['file_path']
        chunk_type = chunk['type']

        # File contains top-level functions and class definitions
        if chunk_type in ['function', 'class_definition', 'module_variable']:
            if file_path in G and chunk_id in G:
                G.add_edge(file_path, chunk_id, relation="contains")

    # Class → method edges (class contains methods)
    for chunk in chunks:
        if chunk['type'] == 'method':
            chunk_id = chunk['chunk_id']
            parent_class = chunk.get('metadata', {}).get('parent_class')
            file_path = chunk['file_path']

            if parent_class and file_path in class_definitions:
                class_chunk_id = class_definitions[file_path].get(parent_class)
                if class_chunk_id and class_chunk_id in G:
                    G.add_edge(class_chunk_id, chunk_id, relation="contains")

    # Step 5: Add package/import nodes (external dependencies)
    packages = set()
    for chunk in chunks:
        imports = chunk.get('metadata', {}).get('imports', [])
        for imp in imports:
            # Extract package name (first part before '.')
            if '.' in imp:
                package = imp.split('.')[0]
            else:
                package = imp

            # Skip internal imports and common builtins
            if package not in ['', 'self', 'super'] and not package.startswith('_'):
                packages.add(package)

    for package in packages:
        if package not in G:  # Don't duplicate
            G.add_node(
                package,
                type="package",
                label=package,
                shape="star",
                level=0  # Packages at top level
            )

    # Add import edges (file → package)
    for chunk in chunks:
        chunk_id = chunk['chunk_id']
        imports = chunk.get('metadata', {}).get('imports', [])

        for imp in imports:
            package = imp.split('.')[0] if '.' in imp else imp
            if package in G and package in packages:
                # Add edge from chunk to package
                if chunk_id in G:
                    G.add_edge(package, chunk_id, relation="imports")

    # Step 6: Add spatial layout (hierarchical positioning)
    G = add_spatial_information(G)

    logging.info(f"✅ Chunk-level graph created: {len(G.nodes())} nodes, {len(G.edges())} edges")

    return G


def _get_shape_for_chunk_type(chunk_type: str) -> str:
    """Get node shape based on chunk type."""
    shapes = {
        'method': 'ellipse',
        'function': 'ellipse',
        'class_definition': 'box',
        'module_variable': 'diamond',
        'file': 'ellipse'
    }
    return shapes.get(chunk_type, 'ellipse')


def create_dependency_graph(ast_data: Dict[str, Any]) -> nx.DiGraph:
    G = nx.DiGraph()

    directories = set()
    files = set()
    methods = {}
    imported_methods = {}

    # First pass: collect all files and methods
    for file_path, file_info in ast_data.items():
        files.add(file_path)

        # Handle both OLD format (strings) and NEW format (dicts)
        functions = file_info.get("functions", [])
        classes = file_info.get("classes", [])

        for func in functions:
            func_name = func['name'] if isinstance(func, dict) else func
            methods[func_name] = file_path

        for cls in classes:
            cls_name = cls['name'] if isinstance(cls, dict) else cls
            methods[cls_name] = file_path

    # Second pass: create nodes and edges
    for file_path, file_info in ast_data.items():
        dir_path = os.path.dirname(file_path)
        while dir_path:
            directories.add(dir_path)
            dir_path = os.path.dirname(dir_path)

        functions = file_info.get("functions", [])
        classes = file_info.get("classes", [])
        imports = file_info.get("imports", [])

        # Extract names (handle both string and dict formats)
        func_names = [f['name'] if isinstance(f, dict) else f for f in functions]
        class_names = [c['name'] if isinstance(c, dict) else c for c in classes]

        file_label = f"{os.path.basename(file_path)}\nFunctions: {', '.join(func_names)}\nClasses: {', '.join(class_names)}"
        G.add_node(file_path, type="file", label=file_label, shape="ellipse", level=file_path.count('/') + 1)

        file_extension = os.path.splitext(file_path)[1].lower()

        for imp in imports:
            if file_extension in ['.py', '.js', '.ts']:
                handle_python_style_import(G, imp, file_path, files, methods, imported_methods)
            elif file_extension in ['.java', '.kt']:
                handle_java_style_import(G, imp, file_path)
            elif file_extension in ['.go']:
                handle_go_style_import(G, imp, file_path)
            elif file_extension in ['.c', '.cpp', '.h', '.hpp']:
                handle_c_style_import(G, imp, file_path)
            else:
                # Generic handling for unknown file types
                G.add_node(imp, type="package", label=imp, shape="star", level=imp.count('.') + 1)
                G.add_edge(imp, file_path, relation="imports")

    # Add directory nodes and edges
    for directory in directories:
        G.add_node(directory, type="directory", label=os.path.basename(directory), shape="box", level=directory.count('/'))
        for file in files:
            if os.path.dirname(file) == directory:
                G.add_edge(directory, file, relation="contains")
        subdirs = [d for d in directories if os.path.dirname(d) == directory]
        for subdir in subdirs:
            G.add_edge(directory, subdir, relation="contains")

    # Perform edge clustering
    G = cluster_edges(G)

    # Add spatial information
    G = add_spatial_information(G)

    return G

def add_spatial_information(G):
    # Use a layout algorithm to determine node positions
    pos = nx.spring_layout(G, k=0.5, iterations=50)
    
    # Normalize positions to range [0, 1000] for both x and y
    min_x = min(pos.values(), key=lambda p: p[0])[0]
    max_x = max(pos.values(), key=lambda p: p[0])[0]
    min_y = min(pos.values(), key=lambda p: p[1])[1]
    max_y = max(pos.values(), key=lambda p: p[1])[1]
    
    for node, (x, y) in pos.items():
        normalized_x = (x - min_x) / (max_x - min_x) * 1000
        normalized_y = (y - min_y) / (max_y - min_y) * 1000
        G.nodes[node]['x'] = normalized_x
        G.nodes[node]['y'] = normalized_y
    
    return G

def handle_python_style_import(G, imp, file_path, files, methods, imported_methods):
    if '.' in imp:
        module_path, method = imp.rsplit('.', 1)
        source_file = next((file for file in files if file.endswith(module_path.replace('.', '/') + '.py')), None)
        if source_file:
            # This is an import from within the project
            if method not in imported_methods:
                mid_point = f"{source_file}::{method}"
                G.add_node(mid_point, type="import", label=method, shape="box", level=source_file.count('/') + 2)
                G.add_edge(source_file, mid_point, relation="exports")
                imported_methods[method] = mid_point
            G.add_edge(imported_methods[method], file_path, relation="imports")
        else:
            # This is a package import
            G.add_node(module_path, type="package", label=module_path, shape="star", level=module_path.count('.') + 1)
            G.add_edge(module_path, file_path, relation="imports", label=method)
    elif imp in methods:
        # This is a direct import of a method or class from another file
        source_file = methods[imp]
        if source_file != file_path:
            if imp not in imported_methods:
                mid_point = f"{source_file}::{imp}"
                G.add_node(mid_point, type="import", label=imp, shape="box", level=source_file.count('/') + 2)
                G.add_edge(source_file, mid_point, relation="exports")
                imported_methods[imp] = mid_point
            G.add_edge(imported_methods[imp], file_path, relation="imports")
    else:
        # This is likely a built-in or unknown import
        G.add_node(imp, type="package", label=imp, shape="star", level=1)
        G.add_edge(imp, file_path, relation="imports")

def handle_java_style_import(G, imp, file_path):
    package_path = imp.rsplit('.', 1)[0]
    G.add_node(package_path, type="package", label=package_path, shape="star", level=package_path.count('.') + 1)
    G.add_edge(package_path, file_path, relation="imports")

def handle_go_style_import(G, imp, file_path):
    G.add_node(imp, type="package", label=imp, shape="star", level=imp.count('/') + 1)
    G.add_edge(imp, file_path, relation="imports")

def handle_c_style_import(G, imp, file_path):
    G.add_node(imp, type="header", label=imp, shape="diamond", level=imp.count('/') + 1)
    G.add_edge(imp, file_path, relation="includes")

def cluster_edges(G):
    edge_groups = defaultdict(list)
    for edge in G.edges(data=True):
        source, target = edge[0], edge[1]
        edge_groups[(source, target)].append(edge[2])
    
    for (source, target), edges in edge_groups.items():
        if len(edges) > 1:
            G.add_edge(source, target, relation="multiple", count=len(edges))
            for edge in edges:
                G.remove_edge(source, target, key=None)
    
    return G

def save_graph_as_json(graph: nx.DiGraph, file_path: str) -> None:
    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)

def load_graph_from_json(file_path: str) -> nx.DiGraph:
    with open(file_path, 'r') as f:
        data = json.load(f)
    return json_graph.node_link_graph(data)

def get_subgraph_at_level(G: nx.DiGraph, level: int) -> nx.DiGraph:
    nodes = [node for node, data in G.nodes(data=True) if data['level'] <= level]
    return G.subgraph(nodes)