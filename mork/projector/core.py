"""
projector.py — Project event journal JSON to MORK atoms

This module reads an event journal (JSON) and generates MORK add-atom commands
that can be sent to the MORK HTTP server.

The event journal contains operations like:
- upsert_node: Create/update a node (State, Claim, Move, Attempt, etc.)
- add_edge: Create a relationship between nodes

The projector transforms these into MORK atoms in the format:
!(add-atom &mork (NodeType proof_id local_id field1 field2 ...))
!(add-atom &mork (Edge edge_id RELATION src_id dst_id))
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


# Mapping of node labels to their MORK atom types
NODE_TYPE_MAP = {
    "State": "State",
    "Claim": "Claim",
    "Move": "Move",
    "Attempt": "Attempt",
    "Proof": "Proof",
    "Route": "Route",
    "Artifact": "Artifact",
    "Context": "Context",
    "Critique": "Critique",
    "Experiment": "Experiment",
    "Verification": "Verification",
    "Concept": "Concept",
    "Hypothesis": "Hypothesis",
}

# Mapping of edge relations to their MORK relation names
EDGE_REL_MAP = {
    "SUPPORTED_BY": "SUPPORTED_BY",
    "PROPOSES": "PROPOSES",
    "ON_STATE": "ON_STATE",
    "ON_MOVE": "ON_MOVE",
    "USES_CLAIM": "USES_CLAIM",
    "DEPENDS_ON": "DEPENDS_ON",
    "REQUIRES": "REQUIRES",
    "CHILD_OF": "CHILD_OF",
    "HAS_STATE": "HAS_STATE",
    "HAS_CLAIM": "HAS_CLAIM",
    "PRODUCED_CLAIM": "PRODUCED_CLAIM",
    "PRODUCED_ARTIFACT": "PRODUCED_ARTIFACT",
    "VIA_ROUTE": "VIA_ROUTE",
    "USED_CONTEXT": "USED_CONTEXT",
    "HAD_CRITIQUE": "HAD_CRITIQUE",
    "RAN": "RAN",
    "HAD_VERIFICATION": "HAD_VERIFICATION",
    "OF": "OF",
    "TARGETS": "TARGETS",
}

# Node types that need a state_id reference (inferred from edges)
NODES_NEEDING_STATE = {"Move", "Attempt"}

# Field order for each node type (after proof_id and local_id)
# For Move: state_id, status, kind, move_summary
# For Attempt: state_id, status, worker, move_summary
NODE_FIELD_ORDER = {
    "State": ["description", "status", "kind"],
    "Claim": ["statement", "status"],
    "Move": ["status", "kind", "move_summary"],
    "Attempt": ["status", "worker", "move_summary"],
    "Proof": ["theorem_kernel", "theorem_hash", "active_revision"],
    "Route": ["display_path"],
    "Artifact": ["kind", "media_type", "sha256", "filename"],
    "Context": ["packet_hash", "compiler_version", "token_budget", "token_count"],
    "Critique": ["verdict", "reason", "critic_worker"],
    "Experiment": ["question", "status"],
    "Verification": ["kind", "status", "lean_name", "toolchain_hash"],
    "Concept": ["name", "mechanism_tags"],
    "Hypothesis": ["kind", "layer", "falsification_test", "novelty", "abductive_strength", "cost", "risk", "lifecycle_status"],
}


def sanitize_value(value: Any) -> str:
    """Sanitize a value for use in MORK atom syntax."""
    if value is None:
        return '""'
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return str(value)
    # Escape quotes and wrap in quotes
    str_val = str(value).replace('"', '\\"')
    return f'"{str_val}"'


def extract_proof_id(node_id: str) -> str:
    """Extract proof_id from a node id (format: proof_id/local_id)."""
    if "/" in node_id:
        return node_id.split("/")[0]
    return node_id


def extract_local_id(node_id: str) -> str:
    """Extract local id from a node id (format: proof_id/local_id)."""
    if "/" in node_id:
        return node_id.split("/")[1]
    return node_id


class Projector:
    """
    Projects an event journal to MORK add-atom commands.
    
    Uses a two-pass approach:
    1. First pass: collect all nodes and edges
    2. Infer state_id for Move and Attempt nodes from edges
    3. Generate MORK atoms
    """
    
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}  # node_id -> {label, fields}
        self.edges: List[Dict[str, Any]] = []
        self.node_state_map: Dict[str, str] = {}  # node_id -> state_local_id
    
    def process_event_journal(self, journal_data: Dict[str, Any]) -> List[str]:
        """Process the entire journal and return MORK commands."""
        events = journal_data.get("events", [])
        sorted_events = sorted(events, key=lambda e: e.get("revision", 0))
        
        # First pass: collect all nodes and edges
        for event in sorted_events:
            payload = event.get("payload", {})
            ops = payload.get("ops", [])
            for op in ops:
                self._collect_operation(op)
        
        # Second pass: infer state_id for Move and Attempt from edges
        self._infer_state_references()
        
        # Third pass: generate MORK commands
        commands = []
        for node_id, node_data in self.nodes.items():
            cmd = self._node_to_atom(node_id, node_data)
            if cmd:
                commands.append(cmd)
        
        for edge in self.edges:
            cmd = self._edge_to_atom(edge)
            if cmd:
                commands.append(cmd)
        
        return commands
    
    def _collect_operation(self, op: Dict[str, Any]):
        """Collect nodes and edges from an operation."""
        op_type = op.get("op", "")
        
        if op_type == "upsert_node":
            node_id = op.get("id", "")
            label = op.get("label", "Node")
            fields = op.get("fields", {})
            self.nodes[node_id] = {
                "label": label,
                "fields": fields,
            }
        elif op_type == "add_edge":
            self.edges.append({
                "rel": op.get("rel", "RELATED"),
                "src": op.get("src", ""),
                "dst": op.get("dst", ""),
                "edge_id": op.get("edge_id", ""),
            })
    
    def _infer_state_references(self):
        """
        Infer state_id for Move and Attempt nodes from edges.
        
        - Move: state_id comes from PROPOSES edge (src is state, dst is move)
        - Attempt: state_id comes from ON_STATE edge (src is attempt, dst is state)
        """
        for edge in self.edges:
            rel = edge.get("rel", "")
            src = edge.get("src", "")
            dst = edge.get("dst", "")
            
            if rel == "PROPOSES":
                # src is state, dst is move -> move's state_id = dst's local_id's state
                # Actually, src is the state that proposes the move (dst)
                # So the Move (dst) is associated with State (src)
                state_local_id = extract_local_id(src)
                self.node_state_map[dst] = state_local_id
            
            elif rel == "ON_STATE":
                # src is attempt, dst is state -> attempt's state_id = dst's local_id
                state_local_id = extract_local_id(dst)
                self.node_state_map[src] = state_local_id
    
    def _node_to_atom(self, node_id: str, node_data: Dict[str, Any]) -> Optional[str]:
        """Convert a node to a MORK add-atom command."""
        label = node_data.get("label", "Node")
        fields = node_data.get("fields", {})
        
        mork_type = NODE_TYPE_MAP.get(label, label)
        proof_id = extract_proof_id(node_id)
        local_id = extract_local_id(node_id)
        
        # Build the atom parts
        atom_parts = [mork_type, f'"{proof_id}"', f'"{local_id}"']
        
        # For Move and Attempt, inject state_id before other fields
        if label in NODES_NEEDING_STATE:
            state_id = self.node_state_map.get(node_id, "")
            atom_parts.append(f'"{state_id}"')
        
        # Add fields in the expected order
        field_order = NODE_FIELD_ORDER.get(label, [])
        for field_name in field_order:
            if field_name in fields:
                atom_parts.append(sanitize_value(fields[field_name]))
        
        # Add any remaining fields not in the standard order
        for field_name, value in fields.items():
            if field_name not in field_order:
                atom_parts.append(sanitize_value(value))
        
        atom_str = " ".join(atom_parts)
        return f"!(add-atom &mork ({atom_str}))"
    
    def _edge_to_atom(self, edge: Dict[str, Any]) -> str:
        """Convert an edge to a MORK add-atom command."""
        rel = edge.get("rel", "RELATED")
        src = edge.get("src", "")
        dst = edge.get("dst", "")
        edge_id = edge.get("edge_id", "")
        
        mork_rel = EDGE_REL_MAP.get(rel, rel)
        local_edge_id = extract_local_id(edge_id)
        local_src = extract_local_id(src)
        local_dst = extract_local_id(dst)
        
        return f'!(add-atom &mork (Edge "{local_edge_id}" {mork_rel} "{local_src}" "{local_dst}"))'


def project_event_journal(journal_data: Dict[str, Any]) -> List[str]:
    """
    Project an event journal to a list of MORK add-atom commands.
    
    Args:
        journal_data: The parsed event journal JSON data
        
    Returns:
        A list of MORK add-atom command strings
    """
    projector = Projector()
    return projector.process_event_journal(journal_data)


def project_from_file(filepath: str) -> List[str]:
    """
    Load an event journal from a JSON file and project to MORK commands.
    
    Args:
        filepath: Path to the event journal JSON file
        
    Returns:
        A list of MORK add-atom command strings
    """
    with open(filepath, 'r') as f:
        journal_data = json.load(f)
    return project_event_journal(journal_data)


def generate_metta_file(commands: List[str], include_queries: bool = True) -> str:
    """
    Generate a .metta file content from MORK commands.
    
    Args:
        commands: List of MORK add-atom commands
        include_queries: Whether to include standard query templates
        
    Returns:
        A string containing the .metta file content
    """
    lines = [";; Auto-generated MORK atoms from event journal", ""]
    
    # Add mork space initialization
    lines.append(";; Initialize MORK space")
    lines.append("!(mm2-exec &mork 1)")
    lines.append("")
    
    for cmd in commands:
        lines.append(cmd)
    
    lines.append("")
    
    # Add standard query templates
    if include_queries:
        lines.append("")
        lines.append(";; ============================================")
        lines.append(";; QUERY SECTION: Match patterns for querying proof data")
        lines.append(";; ============================================")
        lines.append("")
        lines.extend(generate_query_templates())
    
    return "\n".join(lines)


def generate_query_templates() -> List[str]:
    """
    Generate standard MORK match query templates for proof data.
    
    These queries provide easy access to common proof information:
    - Open states
    - Claims and their status
    - Moves and their kind
    - Attempts and their workers
    - Edge relationships
    - Complete proof graph summary
    
    Returns:
        A list of MORK query command strings
    """
    queries = [
        # Query 1: Find all open states
        ';; Query 1: Find all open states',
        '!(test (collapse (match &mork (State $proof $sid $desc "open" $kind)',
        '                           (open-state $proof $sid $desc $kind)))',
        '       ())',  # Empty result template - will be filled at runtime
        '',
        # Query 2: Find all claims and their status
        ';; Query 2: Find all claims and their status',
        '!(test (collapse (match &mork (Claim $proof $cid $stmt $status)',
        '                          (claim-info $proof $cid $stmt $status)))',
        '       ())',
        '',
        # Query 3: Find all moves and their kind
        ';; Query 3: Find all moves and their kind',
        '!(test (collapse (match &mork (Move $proof $mid $state $status $kind $summary)',
        '                          (move-info $proof $mid $state $status $kind $summary)))',
        '       ())',
        '',
        # Query 4: Find all attempts and their workers
        ';; Query 4: Find all attempts and their workers',
        '!(test (collapse (match &mork (Attempt $proof $aid $state $status $worker $summary)',
        '                          (attempt-info $proof $aid $state $status $worker $summary)))',
        '       ())',
        '',
        # Query 5: Find all edges
        ';; Query 5: Find all edges',
        '!(test (collapse (match &mork (Edge $eid $rel $src $dst)',
        '                          (edge-info $eid $rel $src $dst)))',
        '       ())',
        '',
        # Query 6: Find supported attempts (completed work)
        ';; Query 6: Find supported attempts (completed work)',
        '!(test (collapse (match &mork (Attempt $proof $aid $state "supported" $worker $summary)',
        '                          (supported-attempt $proof $aid $worker $summary)))',
        '       ())',
        '',
        # Query 7: Get complete proof graph info
        ';; Query 7: Get complete proof graph info - all nodes and edges',
        ';; This query gathers the full structure of the proof',
        '!(test (collapse (match &mork',
        '    ;; Match all nodes',
        '    (State $proof $sid $sdesc $sstatus $skind)',
        '    (Claim $proof $cid $cstmt $cstatus)',
        '    (Move $proof $mid $mstate $mstatus $mkind $msummary)',
        '    (Attempt $proof $aid $astate $astatus $aworker $asummary)',
        '    ;; Match all edges',
        '    (Edge $eid $rel $src $dst)',
        '    )',
        '    (proof-graph',
        '        (state $proof $sid $sdesc $sstatus $skind)',
        '        (claim $proof $cid $cstmt $cstatus)',
        '        (move $proof $mid $mstatus $mkind $msummary)',
        '        (attempt $proof $aid $astatus $aworker $asummary)',
        '        (edge $eid $rel $src $dst)))',
        '       ())',
    ]
    return queries
