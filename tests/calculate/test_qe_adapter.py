"""C4 Quantum ESPRESSO adapter tests: translation/export only, never execution."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import backend.calculations  # noqa: F401 -- registers active definitions
from backend.compiler.calculation_compiler import CalculationCompiler
from backend.core.calculation_request import CalculationRequest
from backend.engines.qe import (
    InvalidQEParameterError,
    MissingPseudopotentialError,
    QEOutputExistsError,
    QuantumEspressoAdapter,
    UnsupportedQECalculationError,
)
from backend.engines.qe.writer import serialize_namelist, structure_cards


STRUCTURE_A = {
    "name": "Carbon A",
    "atoms": [{"element": "C", "x": 0.0, "y": 0.0, "z": 0.0}],
    "cell": [[2.46, 0.0, 0.0], [0.0, 2.46, 0.0], [0.0, 0.0, 15.0]],
    "periodic": [True, True, True],
}
PSEUDOS = {"C": {"filename": "C.pbe-n-kjpaw_psl.1.0.0.UPF", "functional": "PBE"}}


def request(selected, *, structure=None, parameters=None, request_id="qe-request-01"):
    values = {"pseudopotentials": PSEUDOS}
    values.update(parameters or {})
    return CalculationRequest(
        id=request_id, structure=STRUCTURE_A if structure is None else structure,
        selected_calculations=list(selected), parameters=values, execution_target="local",
    )


class QENamelistTests(unittest.TestCase):
    def test_stable_namelist_serialization_and_unsupported_values(self):
        text = serialize_namelist("control", {"zeta": None, "alpha": "a'b", "gamma": True, "beta": 4, "delta": 1.25})
        self.assertEqual(text, "&CONTROL\n  alpha = 'a''b'\n  beta = 4\n  delta = 1.25\n  gamma = .true.\n/")
        with self.assertRaisesRegex(InvalidQEParameterError, "Unsupported QE namelist"):
            serialize_namelist("SYSTEM", {"bad": [1, 2]})

    def test_structure_cards_preserve_geometry_and_first_appearance_species_order(self):
        snapshot = json.loads(json.dumps(STRUCTURE_A))
        text = structure_cards(snapshot, {"C": type("Pseudo", (), {"filename": "C.UPF"})()})
        self.assertIn("ATOMIC_SPECIES\nC 12.011 C.UPF", text)
        self.assertIn("CELL_PARAMETERS angstrom\n2.46 0 0\n0 2.46 0\n0 0 15", text)
        self.assertIn("ATOMIC_POSITIONS angstrom\nC 0 0 0", text)
        self.assertEqual(snapshot, STRUCTURE_A)


class QEAdapterTests(unittest.TestCase):
    def test_scf_preview_has_pw_input_geometry_parameters_and_shared_context(self):
        plan = CalculationCompiler(request(["scf"], parameters={"pseudopotentials": PSEUDOS, "ecutwfc": 72})).compile()
        generated = QuantumEspressoAdapter().compile_plan(plan)
        task = generated.task_for_calculation("scf")
        self.assertEqual(task.executable, "pw.x")
        self.assertIn("calculation = 'scf'", task.input_text)
        self.assertIn("ecutwfc = 72", task.input_text)
        self.assertIn("CELL_PARAMETERS angstrom", task.input_text)
        self.assertIn("K_POINTS automatic\n6 6 6 0 0 0", task.input_text)
        self.assertEqual(generated.context.prefix, "qs_qe_request_01")

    def test_phonon_generation_shares_scf_runtime_state(self):
        plan = CalculationCompiler(request(["phonons"])).compile()
        generated = QuantumEspressoAdapter().compile_plan(plan)
        scf, phonons = generated.tasks
        self.assertEqual((scf.calculation_id, phonons.calculation_id), ("scf", "phonons"))
        self.assertEqual(phonons.executable, "ph.x")
        self.assertIn("prefix = 'qs_qe_request_01'", phonons.input_text)
        self.assertIn("outdir = '../qe_out'", phonons.input_text)
        self.assertEqual(phonons.depends_on_task_ids, (scf.task_id,))

    def test_deferred_dos_and_bands_are_not_misrepresented_as_qe_supported(self):
        for calculation_id in ("bands", "dos", "pdos"):
            plan = CalculationCompiler(request([calculation_id])).compile()
            with self.assertRaisesRegex(UnsupportedQECalculationError, calculation_id):
                QuantumEspressoAdapter().compile_plan(plan)

    def test_e3_soc_requires_every_species_be_fully_relativistic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); scalar=root/"C.UPF"; scalar.write_text("<UPF><PP_HEADER element=\"C\" functional=\"PBE\" pseudo_type=\"NC\" relativistic=\"scalar-relativistic\"/></UPF>")
            import hashlib
            selected={"C":{"filename":scalar.name,"source":str(scalar),"sha256":hashlib.sha256(scalar.read_bytes()).hexdigest()}}
            with self.assertRaisesRegex(InvalidQEParameterError,"fully relativistic pseudopotential for C"):
                QuantumEspressoAdapter().compile_plan(CalculationCompiler(request(["scf"],parameters={"pseudopotentials":selected,"spin_treatment":"SOC"})).compile())
            full=root/"C_rel.UPF"; full.write_text("<UPF><PP_HEADER element=\"C\" functional=\"PBE\" pseudo_type=\"NC\" relativistic=\"fully-relativistic\" has_so=\"T\"/></UPF>")
            selected={"C":{"filename":full.name,"source":str(full),"sha256":hashlib.sha256(full.read_bytes()).hexdigest()}}
            generated=QuantumEspressoAdapter().compile_plan(CalculationCompiler(request(["scf"],parameters={"pseudopotentials":selected,"spin_treatment":"SOC"})).compile())
            self.assertIn("noncolin = .true.",generated.tasks[0].input_text); self.assertIn("lspinorb = .true.",generated.tasks[0].input_text); self.assertNotIn("nspin = 2",generated.tasks[0].input_text)

    def test_missing_pseudo_is_typed_and_transactional(self):
        structure = json.loads(json.dumps(STRUCTURE_A))
        structure["atoms"].append({"element": "N", "x": 1.0, "y": 1.0, "z": 1.0})
        plan = CalculationCompiler(request(["scf"], structure=structure)).compile()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(MissingPseudopotentialError, "N"):
                QuantumEspressoAdapter().write_plan(plan, root)
            self.assertEqual(list(root.iterdir()), [])

    def test_export_is_deterministic_snapshot_bound_and_refuses_replacement(self):
        source_a = json.loads(json.dumps(STRUCTURE_A))
        with tempfile.TemporaryDirectory() as pseudo_root, tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            source = Path(pseudo_root) / "C.pbe-n-kjpaw_psl.1.0.0.UPF"
            source.write_text('<UPF version="2"><PP_HEADER element="C" functional="PBE" pseudo_type="NC" relativistic="scalar-relativistic"/></UPF>', encoding="utf-8")
            import hashlib
            pseudos = {"C": {"filename": source.name, "source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "functional": "PBE"}}
            plan = CalculationCompiler(request(["scf"], structure=source_a, parameters={"pseudopotentials": pseudos})).compile()
            output_a = QuantumEspressoAdapter().write_plan(plan, first)
            output_b = QuantumEspressoAdapter().write_plan(plan, second)
            input_a = (output_a / "001_scf" / "scf.in").read_bytes()
            input_b = (output_b / "001_scf" / "scf.in").read_bytes()
            self.assertEqual(input_a, input_b)
            self.assertIn(b"2.46 0 0", input_a)
            self.assertNotIn(b"99", input_a)
            self.assertTrue((output_a / "pseudos" / source.name).is_file())
            with self.assertRaises(QEOutputExistsError):
                QuantumEspressoAdapter().write_plan(plan, first)

    def test_persisted_request_round_trip_generates_same_scientific_input(self):
        original = request(["scf"])
        restored = CalculationRequest.from_persistence_dict(original.to_persistence_dict())
        before = QuantumEspressoAdapter().compile_plan(CalculationCompiler(original).compile()).tasks[0].input_text
        after = QuantumEspressoAdapter().compile_plan(CalculationCompiler(restored).compile()).tasks[0].input_text
        self.assertEqual(before, after)

    def test_relax_and_vc_relax_have_distinct_pw_namelists(self):
        for calculation_id, expected in (("relax", "calculation = 'relax'"), ("vc_relax", "calculation = 'vc-relax'")):
            plan = CalculationCompiler(request([calculation_id])).compile()
            task = QuantumEspressoAdapter().compile_plan(plan).tasks[0]
            self.assertEqual(task.executable, "pw.x")
            self.assertIn(expected, task.input_text)
            self.assertIn("&IONS", task.input_text)
            if calculation_id == "vc_relax":
                self.assertIn("&CELL", task.input_text)



if __name__ == "__main__":
    unittest.main()
