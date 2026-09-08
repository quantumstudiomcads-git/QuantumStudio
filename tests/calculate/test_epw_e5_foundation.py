import hashlib
import tempfile
import unittest
from pathlib import Path
import numpy as np
from backend.engines.epw.models import EPWSettings
from backend.engines.epw.writer import epw_input
from backend.results.epw import (
    EPWParseError, integrate_lambda, parse_a2f, parse_tc_eigenvalues, parse_wannier_hr, evaluate_wannier_hr,
    parse_wannier_band_blocks, parse_qe_band_blocks, match_wannier_bands, fermi_crossings,
)
from backend.engines.epw.collector import EPWArtifactError, collect_epw_phonon_artifacts
from backend.engines.epw.grid import EPWGridError, epw_full_grid, qe_full_grid_card, validate_epw_grid, require_finer_mesh
from backend.engines.epw.reciprocal import (
    basis_transform, cartesian_path_difference, fractional_to_cartesian,
    qe_ibrav2_cell, reciprocal_basis, transform_fractional_coordinates,
)
from backend.pseudopotentials.provisioner import PSEUDODOJO_PB_PBE_NC_SR, PseudoProvisioner
from backend.pseudopotentials.upf import inspect_upf, inspect_upf_channels


def _write_test_pb_upf(path):
    """Write metadata-only TEST DATA; this is not a usable Pb potential."""
    path.write_text("""<?xml version=\"1.0\"?>
<UPF version=\"2.0.1\">
<PP_HEADER element=\"Pb\" functional=\"PBE\" pseudo_type=\"NC\"
 relativistic=\"scalar\" z_valence=\"14.0\" version=\"test-fixture\"/>
<PP_CHI.1 label=\"5D\" l=\"2\"/>
<PP_CHI.2 label=\"6S\" l=\"0\"/>
<PP_CHI.3 label=\"6P\" l=\"1\"/>
</UPF>
""")



class E5FoundationTests(unittest.TestCase):
    def test_epw_settings_and_native_writer_contract(self):
        p={"nk_coarse":[6,6,6],"nq_coarse":[6,6,6],"nk_fine":[16,16,16],"nq_fine":[8,8,8],"nbndsub":4,"fsthick":6,"degaussw":0.05,"degaussq":0.05,"a2f":True,"eliashberg":True,"tc_linear":True,"mu_star":0.1}
        text=epw_input(EPWSettings.from_parameters(p),"pb",".","pb")
        for token in ("epbwrite = .true.","epwwrite = .true.","a2f = .true.","eliashberg = .true.","tc_linear = .true.","muc = 0.1","nkf1 = 16"):
            self.assertIn(token,text)
    def test_a2f_integral_and_multi_series(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"pb.a2f"; path.write_text("w[meV] a2f a2f\n0 0 0\n1 1 2\n2 1 2\n")
            table=parse_a2f(path); self.assertEqual(table["unit"],"meV"); self.assertEqual(table["alpha2f"].shape,(3,2)); self.assertAlmostEqual(integrate_lambda(table["frequency_mev"],table["alpha2f"][:,0]),2.5)
    def test_a2f_rejects_malformed_table(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"bad.a2f"; path.write_text("w[meV] a2f\n1 2\n2 3 4\n")
            with self.assertRaises(EPWParseError): parse_a2f(path)
    def test_tc_crossing_interpolation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"tc.out"; path.write_text("1 0.7\n2 1.3\n")
            parsed=parse_tc_eigenvalues(path); self.assertAlmostEqual(parsed["tc_K"],1.5)
    def test_tc_requires_bracket(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"tc.out"; path.write_text("1 0.7\n2 0.9\n")
            with self.assertRaises(EPWParseError): parse_tc_eigenvalues(path)

    def test_pseudodojo_pb_metadata_and_managed_install(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory) / "Pb.test.upf"
            _write_test_pb_upf(path)
            record=inspect_upf(path,'pseudodojo','nc-sr-05_pbe_standard')
            self.assertEqual((record.element,record.xc_functional,record.pseudo_type.value,record.relativity.value),("Pb","pbe","NC","SCALAR_RELATIVISTIC"))
            self.assertEqual(record.sha256,hashlib.sha256(path.read_bytes()).hexdigest())

    def test_pseudodojo_pb_declares_s_p_d_channels(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory) / "Pb.test.upf"
            _write_test_pb_upf(path)
            channels=inspect_upf_channels(path)
            self.assertEqual(channels["z_valence"],14.0)
            self.assertEqual({item["label"] for item in channels["channels"]},{"5D","6S","6P"})
            self.assertTrue({0,1,2}.issubset(set(channels["available_l"])))

    def test_epw_collector_is_deterministic_and_validates_contract(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"source"; root.mkdir(); (root/"_ph0"/"pb.phsave").mkdir(parents=True); (root/"_ph0"/"pb.phsave"/"control_ph.xml").write_text("ok")
            for i in (1,2):
                (root/f"pb.dyn{i}").write_text(f"dyn{i}"); target=root/"_ph0" if i==1 else root/f"_ph0/pb.q_{i}"; target.mkdir(parents=True,exist_ok=True); (target/"pb.dvscf1").write_text(f"dvscf{i}")
            out=Path(d)/"save"; manifest=collect_epw_phonon_artifacts(root,"pb",2,out)
            self.assertEqual([Path(x.destination).name for x in manifest["artifacts"][:4]],["pb.dyn_q1","pb.dvscf_q1","pb.dyn_q2","pb.dvscf_q2"])
            with self.assertRaises(EPWArtifactError): collect_epw_phonon_artifacts(root,"pb",3,Path(d)/"other")

if __name__=="__main__": unittest.main()

class E5CoarseStateTests(unittest.TestCase):

    def test_wannier_version_is_part_of_epw_state_identity(self):
        from backend.engines.epw.models import EPWCoarseState
        base=dict(structure_fingerprint="s",pseudo_sha256=("p",),functional="pbe",cutoffs=(60.,240.),scf_mesh=(8,8,8),coarse_k_mesh=(6,6,6),coarse_q_mesh=(3,3,3),nbnd=14,nbndsub=9,projections=("Pb:d","Pb:sp3"))
        old=EPWCoarseState(**base,wannier_version="3.1.0")
        modern=EPWCoarseState(**base,wannier_version="4.0.2")
        self.assertFalse(old.compatible_for(modern))

    def test_projectability_requires_wannier4(self):
        from backend.engines.epw.wannier_capabilities import parse_wannier_version, supports_projectability, require_projectability
        self.assertEqual(parse_wannier_version("Wannier90: 3.1.0"), (3, 1, 0))
        self.assertEqual(parse_wannier_version("Wannier90: 4.0.2"), (4, 0, 2))
        self.assertFalse(supports_projectability("3.1.0"))
        with self.assertRaises(RuntimeError): require_projectability("3.1.0")
        self.assertTrue(supports_projectability("4.0.2", "dis_froz_proj dis_proj_auto dis_proj_min dis_proj_max"))

    def test_coarse_state_identity_invalidates_scientific_changes(self):
        from backend.engines.epw.models import EPWCoarseState
        base=dict(structure_fingerprint='s',pseudo_sha256=('p',),functional='pbe',cutoffs=(90.,360.),scf_mesh=(8,8,8),coarse_k_mesh=(6,6,6),coarse_q_mesh=(3,3,3),nbnd=10,nbndsub=4,projections=('Pb:sp3',))
        state=EPWCoarseState(**base)
        fine=EPWCoarseState(**base)
        self.assertTrue(state.compatible_for(fine))
        self.assertFalse(state.compatible_for(EPWCoarseState(**{**base,'pseudo_sha256':('changed',)})))
        self.assertFalse(state.compatible_for(EPWCoarseState(**{**base,'coarse_q_mesh':(6,6,6)})))


class E5BandForensicsTests(unittest.TestCase):
    def test_wannier_block_parser_preserves_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pb_band.dat"
            blocks = []
            for band in range(4):
                blocks.append("\n".join(f"{index * 0.01:.8f} {band + index * 0.1:.8f}" for index in range(476)))
            path.write_text("\n\n".join(blocks) + "\n")
            table = parse_wannier_band_blocks(path, expected_kpoints=476)
            self.assertEqual(table['shape'], (476, 4))
            self.assertEqual(table['distance'].shape, (476,))
            self.assertTrue(np.all(np.diff(table['distance']) >= 0))

    def test_qe_band_parser_preserves_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pb.direct.dat"
            rows = ["nbnd = 10, nks = 476"]
            rows.extend(" ".join(f"{band + index * 0.01:.8f}" for band in range(10)) for index in range(476))
            path.write_text("\n".join(rows) + "\n")
            table = parse_qe_band_blocks(path, expected_bands=10, expected_kpoints=476)
            self.assertEqual(table['energies'].shape, (476, 10))

    def test_one_to_one_matching_is_permutation_safe(self):
        direct = np.array([[1.0, 2.0, 3.0]])
        wannier = np.array([[2.0, 1.0]])
        result = match_wannier_bands(direct, wannier, fermi_energy=0.0, candidate_indices=(0, 1, 2))
        self.assertEqual(result['all']['max_eV'], 0.0)
        self.assertEqual(len(set(result['assignments'][0])), 2)

    def test_matching_rejects_fewer_candidates(self):
        with self.assertRaises(EPWParseError):
            match_wannier_bands(np.zeros((1, 1)), np.zeros((1, 2)),
                                fermi_energy=0.0, candidate_indices=(0,))


class E5FullGridTests(unittest.TestCase):

    def test_coarse_state_round_trip_preserves_scdm_identity(self):
        from backend.engines.epw.models import EPWCoarseState
        base=dict(structure_fingerprint="s", pseudo_sha256=("p",), functional="pbe", cutoffs=(60.,240.), scf_mesh=(8,8,8), coarse_k_mesh=(12,12,12), coarse_q_mesh=(3,3,3), nbnd=14, nbndsub=9, projections=(), electronic_grid_mode="EPW_FULL_GRID_COMPATIBLE", explicit_kpoint_count=1728, wannier_subspace_method="SCDM_ERFC", scdm_fit_identity="fit", scdm_mu_eV=11.0943816, scdm_sigma_eV=1.93848604, auto_projections=True, scdm_proj=True, scdm_entanglement="erfc", dis_num_iter=0, use_ws_distance=True)
        state = EPWCoarseState(**base)
        self.assertEqual(EPWCoarseState.from_dict(state.to_dict()).identity, state.identity)
        self.assertFalse(state.compatible_for(EPWCoarseState(**{**base, "scdm_sigma_eV": 2.0})))

    def test_fine_mesh_must_be_strictly_finer_and_commensurate(self):
        self.assertEqual(require_finer_mesh((12,12,12), (24,24,24)), (24,24,24))
        with self.assertRaises(EPWGridError):
            require_finer_mesh((12,12,12), (12,12,12))
        with self.assertRaises(EPWGridError):
            require_finer_mesh((3,3,3), (10,10,10))

    def test_epw_grid_is_216_unique_deterministic_and_equal_weighted(self):
        first = epw_full_grid((6, 6, 6))
        second = epw_full_grid((6, 6, 6))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 216)
        self.assertEqual(len(set(first)), 216)
        report = validate_epw_grid((6, 6, 6), first, [1 / 216] * 216)
        self.assertEqual((report.expected_count, report.loaded_count, report.unique_count), (216, 216, 216))
        self.assertAlmostEqual(report.weight_sum, 1.0)

    def test_epw_grid_convergence_sizes_are_explicit_and_normalized(self):
        for mesh, count in [((8, 8, 8), 512), ((10, 10, 10), 1000), ((12, 12, 12), 1728)]:
            points = epw_full_grid(mesh)
            self.assertEqual(len(points), count)
            self.assertEqual(len(set(points)), count)
            self.assertAlmostEqual(sum([1.0 / count] * count), 1.0)

    def test_epw_grid_card_is_explicit_crystal_and_not_automatic(self):
        card = qe_full_grid_card((6, 6, 6))
        self.assertIn("K_POINTS crystal\n216\n", card)
        self.assertNotIn("K_POINTS automatic", card)
        self.assertEqual(len(card.splitlines()), 218)

    def test_epw_grid_validator_rejects_reduced_reordered_and_duplicate_states(self):
        points = list(epw_full_grid((6, 6, 6)))
        with self.assertRaises(EPWGridError):
            validate_epw_grid((6, 6, 6), points[:28])
        with self.assertRaises(EPWGridError):
            validate_epw_grid((6, 6, 6), points[1:] + points[:1])
        with self.assertRaises(EPWGridError):
            validate_epw_grid((6, 6, 6), points[:-1] + [points[0]])

    def test_epw_grid_validator_rejects_wrong_coordinate(self):
        points = list(epw_full_grid((6, 6, 6)))
        points[1] = (points[1][0] + 0.01, points[1][1], points[1][2])
        with self.assertRaises(EPWGridError):
            validate_epw_grid((6, 6, 6), points)

    def test_full_grid_mode_is_part_of_coarse_state_identity(self):
        from backend.engines.epw.models import EPWCoarseState
        base=dict(structure_fingerprint='s',pseudo_sha256=('p',),functional='pbe',cutoffs=(90.,360.),scf_mesh=(8,8,8),coarse_k_mesh=(6,6,6),coarse_q_mesh=(3,3,3),nbnd=10,nbndsub=4,projections=('Pb:sp3',))
        full=EPWCoarseState(**base,electronic_grid_mode='EPW_FULL_GRID_COMPATIBLE',explicit_kpoint_count=216)
        reduced=EPWCoarseState(**base,electronic_grid_mode='SYMMETRY_REDUCED',explicit_kpoint_count=28)
        self.assertFalse(full.compatible_for(reduced))
        self.assertFalse(reduced.compatible_for(full))
        changed_smearing=EPWCoarseState(**base,electronic_grid_mode='EPW_FULL_GRID_COMPATIBLE',explicit_kpoint_count=216,electronic_smearing=('mp',0.04))
        self.assertFalse(full.compatible_for(changed_smearing))

    def test_matcher_uses_requested_epc_window(self):
        direct = np.array([[0.0, 1.0], [0.3, 1.0]])
        wannier = np.array([[0.01], [0.31]])
        small = match_wannier_bands(direct, wannier, fermi_energy=0.0, candidate_indices=(0, 1), energy_window_eV=0.2)
        broad = match_wannier_bands(direct, wannier, fermi_energy=0.0, candidate_indices=(0, 1), energy_window_eV=2.0)
        self.assertEqual(small['energy_window_eV'], 0.2)
        self.assertEqual(small['fermi_window']['count'], 1)
        self.assertEqual(broad['fermi_window']['count'], 2)

    def test_fermi_crossings_report_fraction_distance_and_segment(self):
        crossings = fermi_crossings(
            np.array([[-1.0], [1.0], [2.0]]), fermi_energy=0.0,
            distances=np.array([0.0, 2.0, 3.0]), path_segments=(('G-X', 0, 1),),
        )
        self.assertEqual(len(crossings), 1)
        self.assertEqual(crossings[0]['segment'], 'G-X')
        self.assertAlmostEqual(crossings[0]['fraction'], 0.5)
        self.assertAlmostEqual(crossings[0]['path_distance'], 1.0)

    def test_matcher_rejects_nonpositive_window(self):
        with self.assertRaises(EPWParseError):
            match_wannier_bands(np.zeros((1, 2)), np.zeros((1, 1)), fermi_energy=0.0, candidate_indices=(0, 1), energy_window_eV=0.0)


class E5ReciprocalAuditTests(unittest.TestCase):
    def test_qe_ibrav2_cell_and_reciprocal_identity(self):
        cell = qe_ibrav2_cell(9.508849701769328)
        self.assertTrue(np.allclose(cell, [[-2.515933282, 0, 2.515933282],
                                           [0, 2.515933282, 2.515933282],
                                           [-2.515933282, 2.515933282, 0]]))
        reciprocal = reciprocal_basis(cell)
        self.assertTrue(np.allclose(cell @ reciprocal.T, 2 * np.pi * np.eye(3)))

    def test_unimodular_basis_change_preserves_cartesian_k(self):
        source = qe_ibrav2_cell(9.508849701769328)
        change = np.array([[0, 1, 0], [0, 1, -1], [-1, 1, 0]], dtype=float)
        target = change @ source
        actual, integer, error, determinant = basis_transform(source, target)
        self.assertTrue(np.allclose(actual, change))
        self.assertTrue(np.array_equal(integer, change.astype(int)))
        self.assertLess(error, 1e-12)
        self.assertEqual(determinant, 1.0)
        q = np.array([[0.125, 0.25, 0.375]])
        q_target = transform_fractional_coordinates(q, change)
        self.assertTrue(np.allclose(fractional_to_cartesian(q, reciprocal_basis(source)),
                                    fractional_to_cartesian(q_target, reciprocal_basis(target))))

    def test_cartesian_path_comparison_detects_same_fractionals_in_different_basis(self):
        source = qe_ibrav2_cell(9.508849701769328)
        target = np.array([[0, 2.515933282, 2.515933282],
                           [2.515933282, 0, 2.515933282],
                           [2.515933282, 2.515933282, 0]])
        path = np.array([[0, 0, 0], [0.125, 0.25, 0.375]])
        maximum, rms, mean = cartesian_path_difference(path, reciprocal_basis(source), path, reciprocal_basis(target))
        self.assertGreater(maximum, 0.1)
        self.assertGreater(rms, 0.1)
        self.assertGreater(mean, 0.1)



class E5TrainingHamiltonianTests(unittest.TestCase):
    def test_hr_parser_and_gamma_evaluation(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x_hr.dat"
            p.write_text("test\n2\n1\n1\n0 0 0 1 1 1.0 0.0\n0 0 0 1 2 0.0 0.0\n0 0 0 2 1 0.0 0.0\n0 0 0 2 2 2.0 0.0\n")
            table = parse_wannier_hr(p)
            values = evaluate_wannier_hr(table, np.array([[0.0, 0.0, 0.0]]))
            self.assertTrue(np.allclose(values, [[1.0, 2.0]]))


class E5ProjectabilityTests(unittest.TestCase):
    def test_projectability_contract_invalidates_electronic_state(self):
        from backend.engines.epw.models import EPWCoarseState
        base=dict(structure_fingerprint="s",pseudo_sha256=("p",),functional="pbe",cutoffs=(60.,240.),scf_mesh=(8,8,8),coarse_k_mesh=(6,6,6),coarse_q_mesh=(3,3,3),nbnd=14,nbndsub=9,projections=("Pb:d","Pb:sp3"))
        energy=EPWCoarseState(**base)
        projectability=EPWCoarseState(**{**base,"wannier_subspace_method":"PROJECTABILITY_DISENTANGLEMENT","projector_source":"QE pseudo-atomic","projector_normalization":"normalized","projectability_threshold_mode":"auto"})
        self.assertFalse(energy.compatible_for(projectability))
        self.assertEqual(projectability.nbndsub,9)
