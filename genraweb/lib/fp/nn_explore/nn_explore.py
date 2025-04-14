"""Methods to provide data for the nearest neighbor exploration graph."""

from genraweb.lib.chem_id import ChemID
from genraweb.lib.fp.fpclass import FPGen
from genraweb.lib.fp.fputils import FP_INFO
from genraweb.resources import DB


def node_details(res, expanded, isTarget):
    """dict of details for a node, non-None elements only."""
    return dict(
        i
        for i in (
            ("dsstox_sid", res.get("dsstox_sid")),
            ("dsstox_cid", res.get("dsstox_cid")),
            ("name", res.get("name")),
            ("mol_weight", res.get("mol_weight")),
            ("expanded", expanded),
            ("isTarget", isTarget),
        )
        if i[1] is not None
    )


def graph_fp(edges, nodes, state, fp_id):

    edges_seen = set()
    # types_in_seen: (chem_id, fp_id) => an fp_id type edge already leads to chem_id
    types_in_seen = set()
    todo = [state.chem_id]
    # something like "chm_mrgn.tox_txrf"
    key = FPGen.fp_info_key(fp_id=fp_id, sel_by=state.sel_by)
    step_i = 0  # levels outward from target chem_id
    while step_i < state.steps:
        step_i += 1
        if not todo:
            break
        query = ChemID.chem_id_search(todo, index=True)
        if not query:
            break
        query[key] = {"$exists": True}
        todo = []
        for res in DB[FP_INFO].find(query, {"_id": False}):
            from_ = res.get("dsstox_cid") or res.get("dsstox_sid")
            # collect node descriptions for *from* nodes
            if from_ not in nodes or isinstance(nodes[from_], str):
                nodes[from_] = node_details(
                    res,
                    expanded=step_i <= state.steps,
                    isTarget=from_ == state.chem_id or None,
                )

            for neighbor_i, neighbor in enumerate(  # up to k0 neighbors
                res[fp_id][state.sel_by]["chem_ids"][
                    : state.k0 + (1 if from_ != state.chem_id else 0)
                ]
            ):
                similarity = res[fp_id][state.sel_by]["similarities"][neighbor_i]
                if similarity < state.s0:  # threshold filtering takes place here
                    continue
                edge_out = (from_, neighbor, fp_id)
                edge_in = (neighbor, from_, fp_id)
                # don't follow same edge twice, in either direction
                if set((edge_out, edge_in)) & edges_seen:
                    continue
                edges_seen.add(edge_out)
                edges_seen.add(edge_in)
                if state.graph_type == "out_only":
                    type_in = (neighbor, fp_id)
                    if type_in in types_in_seen:
                        continue
                    types_in_seen.add(type_in)
                # if neighbor not in nodes or isinstance(nodes[neighbor], str):
                todo.append(neighbor)
                if step_i <= state.steps:
                    if neighbor not in nodes:
                        nodes[neighbor] = neighbor  # make sure we get name etc.
                    edges.append(
                        {
                            "from": from_,
                            "to": neighbor,
                            "step": step_i,
                            "similarity": round(similarity, 3),
                            "type": fp_id,
                        }
                    )


def nn_graph(state):
    edges = []
    nodes = {}  # Get node level details (name, mol. weight etc.)

    for fp_id in state.fp_ids:
        graph_fp(edges, nodes, state, fp_id)

    # get metadata for leaf nodes, if they don't exist
    leaf_nodes = {
        chem_id: node for chem_id, node in nodes.items() if isinstance(node, str)
    }
    if leaf_nodes:
        query = ChemID.chem_id_search(list(leaf_nodes.keys()), index=True)
        for res in DB[FP_INFO].find(query, {"_id": False}):
            leaf = res.get("dsstox_cid") or res.get("dsstox_sid")
            nodes[leaf] = node_details(res, expanded=False, isTarget=None)

    return {"nodes": nodes, "edges": edges}
