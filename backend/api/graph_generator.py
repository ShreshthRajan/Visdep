import os
import networkx as nx
from typing import Dict, Any, List, Optional
from networkx.readwrite import json_graph
import json
from collections import defaultdict
import logging

# Note: Graph positions are now saved FROM THE FRONTEND after vis-network
# completes ForceAtlas2 stabilization. This ensures the exact same beautiful
# layout that users see. No server-side fa2 needed.


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

    # Step 6: Skip ALL backend layout computation
    # Frontend uses ForceAtlas2 (WebGL-accelerated) for ALL repos.
    # This produces beautiful radial clustering layouts and is faster than backend spring_layout.
    logging.info(f"⚡ Layout: {len(G.nodes()):,} nodes will use frontend ForceAtlas2 (WebGL-accelerated)")

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

    # Skip ALL backend layout computation
    # Frontend uses ForceAtlas2 (WebGL-accelerated) for ALL repos.
    # This produces beautiful radial clustering layouts and is faster than backend spring_layout.
    node_count = len(G.nodes())
    logging.info(f"⚡ Layout: {node_count:,} nodes will use frontend ForceAtlas2 (WebGL-accelerated)")

    return G

def add_spatial_information(G):
    """
    Add basic spatial positions for backward compatibility.

    Note: Frontend uses Force-Atlas2 for beautiful layouts (ignores these positions).
    Kept for legacy support only.
    """
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

def save_graph_as_json(graph: nx.DiGraph, file_path: str = "dependency_graph.json", repo_id: int = None) -> None:
    """Save graph to local file and Supabase (Storage for large graphs)."""
    import gzip
    
    # Phase 2: Use repo-specific filename if repo_id provided
    if repo_id:
        file_path = f"dependency_graph_{repo_id}.json"

    data = json_graph.node_link_data(graph)
    with open(file_path, 'w') as f:
        json.dump(data, f)
    
    # MEGA-REPO FIX: Also save to Supabase for Railway access
    if repo_id:
        try:
            from .supabase_client import get_supabase_client
            supabase = get_supabase_client()
            
            # Check file size - use Storage for large graphs (>2MB)
            json_str = json.dumps(data)
            size_mb = len(json_str.encode('utf-8')) / (1024 * 1024)
            
            if size_mb > 2:
                # Large graph: Use Supabase Storage
                logging.info(f"📤 Graph is {size_mb:.1f}MB - using Supabase Storage")
                
                compressed = gzip.compress(json_str.encode('utf-8'))
                storage_path = f"graphs/{repo_id}.json.gz"
                
                try:
                    supabase.storage.from_('repo-data').remove([storage_path])
                except:
                    pass
                
                supabase.storage.from_('repo-data').upload(
                    storage_path,
                    compressed,
                    file_options={"content-type": "application/gzip"}
                )
                
                # Store reference in table
                supabase.table('repo_graphs').upsert({
                    'repo_id': repo_id,
                    'graph_data': {
                        'storage_path': storage_path,
                        'compressed': True,
                        'node_count': len(data.get('nodes', []))
                    }
                }, on_conflict='repo_id').execute()
                
                logging.info(f"✅ Saved large graph to Supabase Storage for repo_id={repo_id}")
            else:
                # Small graph: Use table directly
                supabase.table('repo_graphs').upsert({
                    'repo_id': repo_id,
                    'graph_data': data
                }, on_conflict='repo_id').execute()
                
                logging.info(f"✅ Saved graph to Supabase for repo_id={repo_id}")
        except Exception as e:
            logging.warning(f"⚠️ Failed to save graph to Supabase: {e}")

def load_graph_from_json(file_path: str = "dependency_graph.json", repo_id: int = None) -> nx.DiGraph:
    """Load graph from local file or Supabase (Storage for large graphs)."""
    import gzip
    
    # Phase 2: Use repo-specific filename if repo_id provided
    if repo_id:
        file_path = f"dependency_graph_{repo_id}.json"

    logging.info(f"📊 Attempting to load graph for repo_id={repo_id}")
    
    # First try loading from local file
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        logging.info(f"✅ Loaded graph from local file for repo_id={repo_id}")
        return json_graph.node_link_graph(data)
    except FileNotFoundError:
        # If local file not found, try Supabase
        if repo_id:
            try:
                from .supabase_client import get_supabase_client
                supabase = get_supabase_client()
                
                result = supabase.table('repo_graphs')\
                    .select('graph_data')\
                    .eq('repo_id', repo_id)\
                    .limit(1)\
                    .execute()
                
                if result.data and len(result.data) > 0:
                    data = result.data[0]['graph_data']
                    
                    # Check if graph is stored in Supabase Storage
                    if isinstance(data, dict) and data.get('storage_path'):
                        storage_path = data['storage_path']
                        logging.info(f"📥 Loading large graph from Supabase Storage: {storage_path}")
                        
                        # Download from Storage
                        compressed_data = supabase.storage.from_('repo-data').download(storage_path)
                        
                        # Decompress
                        if data.get('compressed', False):
                            json_bytes = gzip.decompress(compressed_data)
                            data = json.loads(json_bytes.decode('utf-8'))
                        else:
                            data = json.loads(compressed_data.decode('utf-8'))
                        
                        logging.info(f"✅ Loaded large graph from Supabase Storage for repo_id={repo_id}")
                    else:
                        logging.info(f"✅ Loaded graph from Supabase table for repo_id={repo_id}")
                    
                    return json_graph.node_link_graph(data)
                else:
                    logging.error(f"❌ Graph not found locally or in Supabase for repo_id={repo_id}")
                    raise FileNotFoundError(f"Graph not found for repo_id={repo_id}")
            except Exception as e:
                logging.error(f"❌ Graph not found locally or in Supabase for repo_id={repo_id}: {e}")
                raise FileNotFoundError(f"Graph not found for repo_id={repo_id}: {e}")
        else:
            logging.error(f"❌ Graph file not found: {file_path}")
            raise

def get_subgraph_at_level(G: nx.DiGraph, level: int) -> nx.DiGraph:
    nodes = [node for node, data in G.nodes(data=True) if data['level'] <= level]
    return G.subgraph(nodes)


# =============================================================================
# GRAPH POSITIONS (Saved from frontend vis-network ForceAtlas2)
# =============================================================================
# 
# Graph positions are now computed BY VIS-NETWORK in the frontend using its
# native ForceAtlas2 implementation. After stabilization completes, the 
# frontend saves the positions to the backend. This ensures:
#
# 1. Identical beautiful layout (same algorithm that users see)
# 2. No server-side fa2 dependency needed
# 3. Instant load for future users with exact same aesthetic
#
# Flow:
# 1. You upload mega-repo → Frontend runs vis-network ForceAtlas2 (30s+)
# 2. After stabilization → Frontend saves positions to backend
# 3. Future users → Load saved positions instantly (same beautiful layout)
# =============================================================================


def store_graph_positions(repo_id: int, positions: Dict[str, Dict[str, float]]) -> bool:
    """
    Store pre-computed graph positions in Supabase.
    
    Args:
        repo_id: Repository ID
        positions: Dict of {node_id: {"x": float, "y": float}}
        
    Returns:
        True if stored successfully
    """
    try:
        from .supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        record = {
            'repo_id': repo_id,
            'positions': positions,
            'algorithm': 'vis-network-forceAtlas2',  # Positions saved from frontend vis-network
            'iterations': 0  # Not applicable - computed by frontend
        }
        
        supabase.table('graph_positions').upsert(
            record, 
            on_conflict='repo_id'
        ).execute()
        
        logging.info(f"✅ Stored graph positions for repo_id={repo_id} ({len(positions)} nodes)")
        return True
        
    except Exception as e:
        logging.error(f"❌ Failed to store graph positions: {e}")
        return False


def load_graph_positions(repo_id: int) -> Optional[Dict[str, Dict[str, float]]]:
    """
    Load pre-computed graph positions from Supabase.
    
    Args:
        repo_id: Repository ID
        
    Returns:
        Dict of positions or None if not found
    """
    try:
        from .supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        result = supabase.table('graph_positions')\
            .select('positions')\
            .eq('repo_id', repo_id)\
            .limit(1)\
            .execute()
        
        if result.data and len(result.data) > 0:
            positions = result.data[0]['positions']
            logging.info(f"✅ Loaded graph positions for repo_id={repo_id} ({len(positions)} nodes)")
            return positions
        
        return None
        
    except Exception as e:
        logging.warning(f"⚠️ Failed to load graph positions: {e}")
        return None


def precompute_graph_with_positions(
    chunks: List[Dict[str, Any]], 
    repo_id: int
) -> nx.DiGraph:
    """
    Create chunk-level graph.
    
    Note: For mega-repos, positions are saved FROM THE FRONTEND after
    vis-network completes ForceAtlas2 stabilization. This ensures the
    exact same beautiful layout that users see.
    
    Flow for mega-repos:
    1. You upload the repo (this function creates the graph structure)
    2. Frontend loads graph, runs vis-network ForceAtlas2 (30s+)
    3. After stabilization, frontend saves positions to backend
    4. Future users load those exact positions instantly
    
    Args:
        chunks: List of code chunks
        repo_id: Repository ID
        
    Returns:
        NetworkX graph (positions saved separately by frontend)
    """
    # Create graph
    G = create_chunk_level_graph(chunks)
    
    if len(G.nodes()) > 3000:
        logging.info(f"📊 Mega-repo detected ({len(G.nodes())} nodes)")
        logging.info(f"   Positions will be saved by frontend after ForceAtlas2 stabilization")
    
    return G