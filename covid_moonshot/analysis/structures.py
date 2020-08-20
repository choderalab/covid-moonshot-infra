"""
Methods for extracting snapshots and structures from core22 FAH trajectories.

Limitations:
* The reference structure (`natoms_reference`) must share the same atom ordering as the first `natoms_reference` atoms of the trajectory.
  For now, this means that the SpruceTK prepared structure (`Mpro-x10789_0_bound-protein-thiolate.pdb`) is used

Dependencies:
* mdtraj >= 1.9.4 (conda-forge)

"""

from typing import Dict, List, Optional
import mdtraj as md
from covid_moonshot.core import Work


def load_trajectory(
    project_path: str, project_data_path: str, run: int, clone: int, gen: int
) -> md.Trajectory:
    """
    Load the trajectory from the specified PRCG.

    Parameters
    ----------
    project_path : str
       Path to project directory (e.g. '/home/server/server2/projects/13422')
    project_data_path : str
       Path to project data directory (e.g. '/home/server/server2/data/SVR314342810/PROJ13422')
    run : int
       Run (e.g. 0)
    clone : int
       Clone (e.g. 0)
    gen : int
       Gen (e.g. 0)

    Returns
    -------
    trajectory : mdtraj.Trajectory
      The trajectory

    """

    # Load trajectory
    pdbfile_path = f"{project_path}/RUNS/RUN{run}/hybrid_complex.pdb"

    # TODO: Reuse path logic from covid_moonshot.lib
    trajectory_path = (
        f"{project_data_path}/RUN{run}/CLONE{clone}/results{gen}/positions.xtc"
    )
    pdbfile = md.load(pdbfile_path)
    trajectory = md.load(trajectory_path, top=pdbfile.top)

    return trajectory


def load_fragment(fragment_id: str) -> md.Trajectory:
    """
    Load the reference fragment structure

    Parameters
    ----------
    fragment_id : str
      Fragment ID (e.g. 'x10789')

    Returns
    -------
    fragment : mdtraj.Trajectory
      The fragment structure

    """
    import mdtraj as md

    # TODO: Put this in the covid-moonshot path, or generalize to an arbitrary file
    fragment = md.load(f"/home/server/Mpro-{fragment_id}_0_bound-protein-thiolate.pdb")

    return fragment


def mdtraj_to_oemol(snapshot: md.Trajectory):
    """
    Create an OEMol from an MDTraj file by writing and reading

    NOTE: This uses terrible heuristics

    Parameters
    ----------
    snapshot : mdtraj.Trajectory
       MDTraj Trajectory with a single snapshot

    Returns
    -------
    oemol : openeye.oechem.OEMol
       The OEMol

    """
    from openeye import oechem
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        filename = os.path.join(tmpdir, "tmp.pdb")
        # Write the PDB file
        snapshot.save(filename)
        # Read it with OpenEye
        with oechem.oemolistream(filename) as ifs:
            for mol in ifs.GetOEGraphMols():
                return mol


def extract_snapshot(
    project_path: str,
    project_data_path: str,
    run: int,
    clone: int,
    gen: int,
    frame: int,
    fragment_id: str = "x10789",
):
    """
    Extract the specified snapshot, align it to the reference fragment, and write protein and ligands to separate PDB files

    Parameters
    ----------
    project_path : str
       Path to project directory (e.g. '/home/server/server2/projects/13422')
    run : str or int
       Run (e.g. '0')
    clone : str or int
       Clone (e.g. '0')
    gen : str or int
       Gen (e.g. '0')
    fragment_id : str
      Fragment ID (e.g. 'x10789')

    Returns
    -------
    sliced_snapshot : dict of str : mdtraj.Trajectory
      sliced_snapshot[name] is the Trajectory for name in ['protein', 'old_ligand', 'new_ligand', 'old_complex', 'new_complex']
    components : dict of str : oechem.OEMol
      components[name] is the OEMol for name in ['protein', 'old_ligand', 'new_ligand']

    """
    # Load the trajectory
    trajectory = load_trajectory(project_path, project_data_path, run, clone, gen)

    # Load the fragment
    fragment = load_fragment(fragment_id)

    # Align the trajectory to the fragment (in place)
    trajectory.superpose(fragment, atom_indices=fragment.top.select("name CA"))

    # Extract the snapshot
    snapshot = trajectory[frame]

    # Slice out old or new state
    sliced_snapshot = slice_snapshot(snapshot, project_path, run)

    # Convert to OEMol
    # NOTE: This uses heuristics, and should be replaced once we start storing actual chemical information
    components = dict()
    for name in ["protein", "old_ligand", "new_ligand"]:
        components[name] = mdtraj_to_oemol(sliced_snapshot[name])

    return sliced_snapshot, components


def get_stored_atom_indices(path):
    """
    Load hybrid topology file and return relevant atom indices.
    """

    import numpy as np

    htf = np.load(f"{path}/htf.npz", allow_pickle=True)["arr_0"].tolist()
    # Determine mapping between hybrid topology and stored atoms in the positions.xtc
    # <xtcAtoms v="solute"/> eliminates waters
    nonwater_atom_indices = htf.hybrid_topology.select("not water")
    hybrid_to_stored_map = {
        nonwater_atom_indices[index]: index
        for index in range(len(nonwater_atom_indices))
    }

    # Get all atom indices from the hybrid system
    protein_atom_indices = htf.hybrid_topology.select("protein")
    hybrid_ligand_atom_indices = htf.hybrid_topology.select("resn MOL")
    # Identify atom index subsets for the old and new ligands from the hybrid system
    old_ligand_atom_indices = [
        index
        for index in hybrid_ligand_atom_indices
        if index in htf._old_to_hybrid_map.values()
    ]
    new_ligand_atom_indices = [
        index
        for index in hybrid_ligand_atom_indices
        if index in htf._new_to_hybrid_map.values()
    ]

    # Compute sliced atom indices using atom indices within positions.xtc
    stored_atom_indices = dict()
    stored_atom_indices["protein"] = [
        hybrid_to_stored_map[index] for index in protein_atom_indices
    ]
    stored_atom_indices["old_ligand"] = [
        hybrid_to_stored_map[index] for index in old_ligand_atom_indices
    ]
    stored_atom_indices["new_ligand"] = [
        hybrid_to_stored_map[index] for index in new_ligand_atom_indices
    ]
    stored_atom_indices["old_complex"] = [
        hybrid_to_stored_map[index]
        for index in list(protein_atom_indices) + list(old_ligand_atom_indices)
    ]
    stored_atom_indices["new_complex"] = [
        hybrid_to_stored_map[index]
        for index in list(protein_atom_indices) + list(new_ligand_atom_indices)
    ]

    return stored_atom_indices


def slice_snapshot(
    snapshot: md.Trajectory,
    project_path: str,
    run: int,
    cache_dir: Optional[str] = None,
) -> Dict[str, md.Trajectory]:
    """
    Slice snapshot to specified state in-place

    .. TODO ::

       The htf.npz file is very slow to load.
       Replace this with a JSON file containing relevant ligand indices only

    Parameters
    ----------
    snapshot : mdtraj.Trajectory
       Snapshot to slice
    project_path : str
       Path to project directory (e.g. '/home/server/server2/projects/13422')
    run : int
       Run (e.g. '0')
    cache_dir : str, optional
       If specified, cache relevant parts of "htf.npz" file in a local directory of this name

    Returns
    -------
    sliced_snapshot : dict of str : mdtraj.Trajectory
      sliced_snapshot[x] where x is one of ['protein', 'old_ligand', 'new_ligand', 'old_complex', 'new_complex']

    """

    # Prepare sliced snapshots
    import mdtraj as md
    import copy
    import joblib

    path = f"{project_path}/RUNS/RUN{run}"

    _get_stored_atom_indices = (
        get_stored_atom_indices
        if cache_dir is None
        else joblib.Memory(cache_dir=cache_dir).cache(get_stored_atom_indices)
    )

    stored_atom_indices = _get_stored_atom_indices(path)

    sliced_snapshot = dict()
    for key in stored_atom_indices.keys():
        atom_indices = stored_atom_indices[key]
        sliced_snapshot[key] = md.Trajectory(
            snapshot.xyz[:, atom_indices, :], snapshot.topology.subset(atom_indices)
        )

    return sliced_snapshot


def save_snapshots(
    project_path: str,
    project_data_path: str,
    run: int,
    works: List[Work],
    fragment_id: str,
    frame: int,
) -> None:

    """
    Saves structure snapshots for the gen and clone with the least reverse work.
    """

    lrw = min(works, key=lambda w: w.reverse_work)

    sliced_snapshots, components = extract_snapshot(
        project_path=project_path,
        project_data_path=project_data_path,
        run=run,
        clone=lrw.path.clone,
        gen=lrw.path.gen,
        frame=frame,
        fragment_id=fragment_id,
    )

    # Write protein PDB
    sliced_snapshots["protein"].save(f"structures/RUN{run}-protein.pdb")

    # Write old and new complex PDBs
    for name in ["old_complex", "new_complex"]:
        sliced_snapshots[name].save(f"structures/RUN{run}-{name}.pdb")

    # Write ligand SDFs
    from openeye import oechem

    for name in ["old_ligand", "new_ligand"]:
        with oechem.oemolostream(f"structures/RUN{run}-{name}.sdf") as ofs:
            oechem.OEWriteMolecule(ofs, components[name])