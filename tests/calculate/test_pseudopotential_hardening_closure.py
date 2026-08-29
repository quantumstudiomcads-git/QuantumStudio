import hashlib
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from backend.pseudopotentials import PseudoProvisioner, ProvisionError, SSSP_EFFICIENCY_130, application_data_root, import_local_pseudopotential
from backend.pseudopotentials.compatibility import cutoff_policy

def upf(element="Si", relativity="scalar"):
    return (f'<UPF version="2.0.1"><PP_HEADER element="{element}" functional="PBE" pseudo_type="USPP" relativistic="{relativity}"/></UPF>').encode()

def archive(body):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info=tarfile.TarInfo("Si.UPF"); info.size=len(body); t.addfile(info,io.BytesIO(body))
    return buf.getvalue()

class PseudopotentialHardeningClosureTests(unittest.TestCase):
    def test_manifest_si_identity(self):
        manifest=json.loads(Path("backend/pseudopotentials/sssp_efficiency_1.3.0_manifest.json").read_text())
        si=next(x for x in manifest["files"] if x["element"]=="Si")
        self.assertEqual(si["sha256"],"ae3aefd0811f9499dbc4a72f1f9ae02ef4fc7f3568bf6f559b68668719c69e2b")
        self.assertEqual(SSSP_EFFICIENCY_130.version,"1.3.0")

    def test_cache_mutation_is_quarantined(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)/"sssp_efficiency"/"1.3.0"; base.mkdir(parents=True)
            (base/"Si.UPF").write_bytes(upf())
            p=PseudoProvisioner(root)
            self.assertEqual(p._records(SSSP_EFFICIENCY_130), ())
            self.assertTrue(list((Path(root)/"quarantine").rglob("Si.UPF.*")))

    def test_local_import_survives_source_relocation_and_reuses_digest(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/"one.UPF"; source.write_bytes(upf())
            other=Path(root)/"two.UPF"; other.write_bytes(source.read_bytes())
            first=import_local_pseudopotential(source,Path(root)/"repo")
            source.unlink()
            second=import_local_pseudopotential(other,Path(root)/"repo")
            self.assertEqual(first.sha256,second.sha256)
            self.assertEqual(first.path,second.path)
            self.assertTrue(Path(first.path).is_file())

    def test_managed_te_soc_is_not_compatible(self):
        with tempfile.TemporaryDirectory() as root:
            body=upf("Te"); payload=archive(body)
            provider=type(SSSP_EFFICIENCY_130)("sssp_efficiency","SSSP Efficiency","1.3.0","https://archive.materialscloud.org/fixture",hashlib.md5(payload).hexdigest(),("pbe",),1024*1024)
            p=PseudoProvisioner(root,(provider,),lambda url,maximum: payload)
            with self.assertRaises(ProvisionError):
                p.provision("Te","pbe",soc=True)

    def test_platform_paths(self):
        self.assertEqual(application_data_root("win32",{"LOCALAPPDATA":"C:/Local"},"/home/u"),Path("C:/Local/QuantumStudio/pseudopotentials"))
        self.assertEqual(application_data_root("darwin",{},"/home/u"),Path("/home/u/Library/Application Support/QuantumStudio/pseudopotentials"))
        self.assertEqual(application_data_root("linux",{"XDG_DATA_HOME":"/tmp/data"},"/home/u"),Path("/tmp/data/QuantumStudio/pseudopotentials"))

    def test_cutoff_floor_and_custom_warning(self):
        from backend.pseudopotentials.models import PseudoPotentialRecord
        r=PseudoPotentialRecord("Si","Si.UPF","x",recommended_ecutwfc_ry=30,recommended_ecutrho_ry=240)
        values,_=cutoff_policy({"ecutwfc":20,"ecutrho":100},(r,),automatic=True)
        self.assertEqual((values["ecutwfc"],values["ecutrho"]),(30.0,240.0))
        _,warnings=cutoff_policy({"ecutwfc":20,"ecutrho":250},(r,),automatic=False)
        self.assertIn("ecutwfc",warnings[0])

    def test_transient_retry_then_success(self):
        payload=archive(upf()); calls=[]
        def transport(url,maximum):
            calls.append(1)
            if len(calls)<2: raise OSError("connection reset")
            return payload
        provider=type(SSSP_EFFICIENCY_130)("fixture","Fixture","1","https://archive.materialscloud.org/a",hashlib.md5(payload).hexdigest(),("pbe",),1024*1024)
        with tempfile.TemporaryDirectory() as root:
            p=PseudoProvisioner(root,(provider,),transport)
            result=p.provision("Si","pbe")
            self.assertEqual(result.record.element,"Si")
            self.assertEqual(len(calls),2)

if __name__ == "__main__":
    unittest.main()
