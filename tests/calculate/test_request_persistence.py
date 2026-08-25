import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtWidgets import QApplication

from frontend.calculate import CalculateWorkspace
from frontend.core import Atom, Project, Structure
from frontend.device_builder.model import Device, DeviceRegion
from frontend.services.calculation_service import CalculationService
from frontend.calculations.catalog import CALCULATIONS

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def app():
    return QApplication.instance() or QApplication([])


def structure(name, element="Si", a=4.0):
    result = Structure(
        [Atom(element, 0.0, 0.0, 0.0), Atom(element, 1.0, 1.0, 1.0)],
        [[a, 0.0, 0.0], [0.0, a, 0.0], [0.0, 0.0, a]], name=name,
    )
    result.periodic = [True, True, True]
    return result


class CalculationRequestPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.service = CalculationService(CALCULATIONS)

    def _request(self, project, calculation_id, parameters, name=None):
        prepared = self.service.create_request(project, [calculation_id], parameters=parameters, name=name)
        project.add_calculation(prepared.backend_request)
        return prepared.backend_request

    def test_legacy_project_without_calculations_and_v03_device_project_load(self):
        source = structure("Legacy")
        with TemporaryDirectory() as directory:
            legacy_path = Path(directory) / "legacy.qs"
            legacy_path.write_text(json.dumps({
                "format": "qstudio", "version": "0.2", "project": {"name": "Legacy"},
                "structure": source.to_dict(), "calculator": {}, "workflows": {}, "results": {}, "analysis": {},
            }))
            legacy = Project.load(legacy_path)
            self.assertEqual(legacy.get_calculations(), ())
            self.assertEqual(legacy.get_structure().to_dict(), source.to_dict())
            device = Device(name="Persisted Device")
            device.add_region(DeviceRegion(source.copy(), name="Region"))
            current = Project("Device v03")
            current.set_structure(source)
            current.set_device(device)
            current_path = Path(directory) / "device-v03.qs"
            payload = current.to_dict()
            payload["version"] = "0.3"
            payload.pop("calculations")
            current_path.write_text(json.dumps(payload))
            loaded = Project.load(current_path)
        self.assertIsNotNone(loaded.get_device())
        self.assertEqual(loaded.get_device().to_dict(), device.to_dict())
        self.assertEqual(loaded.get_calculations(), ())

    def test_multiple_requests_round_trip_preserves_ids_names_parameters_and_snapshots(self):
        project = Project("Requests")
        snapshot_a = structure("Snapshot A", "Si", 4.0)
        project.set_structure(snapshot_a)
        scf = self._request(project, "scf", {"accuracy": "low"}, "Ground state")
        bands = self._request(project, "bands", {"accuracy": "high", "soc": True}, "Bands A")
        dos = self._request(project, "dos", {"accuracy": "standard"}, "DOS A")
        current_b = structure("Current B", "C", 5.0)
        project.set_structure(current_b)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "requests.qs"
            project.save(path)
            loaded = Project.load(path)
        self.assertEqual(loaded.get_structure().to_dict(), current_b.to_dict())
        restored = loaded.get_calculations()
        self.assertEqual([item.id for item in restored], [scf.id, bands.id, dos.id])
        self.assertEqual([item.name for item in restored], ["Ground state", "Bands A", "DOS A"])
        self.assertEqual([item.selected_calculations for item in restored], [["scf"], ["bands"], ["dos"]])
        self.assertEqual([item.parameters for item in restored], [scf.parameters, bands.parameters, dos.parameters])
        self.assertTrue(all(item.structure == snapshot_a.to_dict() for item in restored))
        self.assertFalse(loaded.modified)

    def test_snapshot_independence_update_from_current_duplicate_and_remove(self):
        project = Project("Updates")
        first = structure("A", "Si")
        project.set_structure(first)
        request = self._request(project, "bands", {"accuracy": "low"}, "Bands A")
        project.set_structure(structure("B", "C", 5.0))
        updated_parameters = self.service.update_request_parameters(request, {"accuracy": "high"}, name="Bands tuned")
        project.update_calculation(updated_parameters)
        self.assertEqual(updated_parameters.structure, first.to_dict())
        replaced = self.service.update_request_from_project(updated_parameters, project)
        project.update_calculation(replaced)
        self.assertEqual(replaced.structure, project.get_structure().to_dict())
        duplicate = self.service.duplicate_request(replaced)
        project.add_calculation(duplicate)
        self.assertNotEqual(duplicate.id, replaced.id)
        self.assertEqual(duplicate.structure, replaced.structure)
        self.assertEqual(duplicate.parameters, replaced.parameters)
        before_structure = project.get_structure().to_dict()
        self.assertTrue(project.remove_calculation(replaced.id))
        self.assertEqual(project.get_structure().to_dict(), before_structure)
        self.assertEqual([item.id for item in project.get_calculations()], [duplicate.id])
        self.assertTrue(project.modified)

    def test_valid_request_survives_malformed_neighbor_record(self):
        project = Project("Malformed")
        source = structure("A")
        project.set_structure(source)
        valid = self._request(project, "bands", {"accuracy": "high"}, "Valid")
        payload = project.to_dict()
        payload["calculations"]["requests"].append({"id": "bad", "name": "Broken", "structure": "not-a-structure"})
        with TemporaryDirectory() as directory:
            path = Path(directory) / "malformed.qs"
            path.write_text(json.dumps(payload))
            loaded = Project.load(path)
        self.assertEqual([request.id for request in loaded.get_calculations()], [valid.id])
        self.assertTrue(loaded.calculation_load_errors)
        self.assertEqual(loaded.get_structure().to_dict(), source.to_dict())

    def test_restored_request_recompiles_using_saved_snapshot(self):
        project = Project("Recompile")
        snapshot = structure("Bands A", "Si")
        project.set_structure(snapshot)
        request = self._request(project, "bands", {"accuracy": "high"}, "Bands request")
        project.set_structure(structure("Current B", "C", 5.0))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bands.qs"
            project.save(path)
            loaded = Project.load(path)
        prepared = self.service.prepare_persisted_request(loaded.get_calculation(request.id))
        plan = self.service.compile_request(prepared)
        self.assertEqual(plan.resolved_calculations, ["scf", "bands"])
        self.assertEqual(plan.structure, snapshot.to_dict())
        self.assertEqual(loaded.get_structure().name, "Current B")


class CalculationRequestWorkspaceTests(unittest.TestCase):
    def test_configured_list_selection_and_snapshot_remain_available_without_current_structure(self):
        app()
        project = Project("Workspace")
        source = structure("Saved Input")
        project.set_structure(source)
        service = CalculationService(CALCULATIONS)
        request = service.create_request(project, ["bands"], parameters={"accuracy": "standard"}, name="Saved Bands")
        project.add_calculation(request.backend_request)
        project.set_structure(Structure(name="Empty Current Structure"))
        workspace = CalculateWorkspace(project)
        self.assertEqual(workspace.configured_list.count(), 1)
        workspace.configured_list.setCurrentRow(0)
        self.assertEqual(workspace.calculation_request.backend_request.id, request.id)
        self.assertEqual(workspace.calculation_request.structure_snapshot.to_dict(), source.to_dict())
        self.assertEqual(workspace.execution_plan.resolved_calculations, ["scf", "bands"])
        self.assertIn("Structure snapshot: Saved Input", workspace.execution_preview.text())
        self.assertFalse(workspace.current_structure_summary.valid)
        workspace.close()
