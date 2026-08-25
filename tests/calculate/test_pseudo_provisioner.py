import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from backend.pseudopotentials import DownloadableProvider, ProvisionError, PseudoProvisioner


def upf(element, functional="PBE", relativity="scalar-relativistic"):
    return (f'<UPF version="2.0.1"><PP_HEADER element="{element}" functional="{functional}" '
            f'pseudo_type="NC" relativistic="{relativity}" z_valence="4" ecutwfc="50" ecutrho="400"/></UPF>').encode()


def archive(members):
    payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode="w:gz") as tar:
        for name,body in members.items():
            info=tarfile.TarInfo(name); info.size=len(body); tar.addfile(info,io.BytesIO(body))
    return payload.getvalue()


class PseudoProvisionerTests(unittest.TestCase):
    def _provider(self, payload, functional="pbe", provider="fixture"):
        return DownloadableProvider(provider,"Fixture", "1", f"https://archive.materialscloud.org/{provider}.tar.gz", hashlib.md5(payload).hexdigest(), (functional,), 1024*1024)

    def test_pbe_cache_then_hse_reuse_without_second_download(self):
        payload=archive({"Si.UPF":upf("Si")}); calls=[]; provider=self._provider(payload)
        with tempfile.TemporaryDirectory() as tmp:
            def transport(url,maximum): calls.append(url); return payload
            provisioner=PseudoProvisioner(tmp,(provider,),transport)
            pbe=provisioner.provision("Si","pbe")
            cached=provisioner.provision("Si","pbe")
            hse=provisioner.provision("Si","hse06")
            self.assertTrue(pbe.downloaded); self.assertFalse(cached.downloaded); self.assertFalse(hse.downloaded)
            self.assertEqual(pbe.record.sha256,hse.record.sha256); self.assertEqual(len(calls),1)

    def test_b3lyp_requires_blyp_provider_and_pz_pw91_remain_exact(self):
        blyp=archive({"Si-blyp.UPF":upf("Si","BLYP")}); pz=archive({"Si-pz.UPF":upf("Si","PZ")}); pw91=archive({"Si-pw91.UPF":upf("Si","PW91")})
        providers=(self._provider(blyp,"blyp","blyp"),self._provider(pz,"pz","pz"),self._provider(pw91,"pw91","pw91"))
        body={provider.archive_url: value for provider,value in zip(providers,(blyp,pz,pw91))}
        with tempfile.TemporaryDirectory() as tmp:
            provisioner=PseudoProvisioner(tmp,providers,lambda url,maximum:body[url])
            self.assertEqual(provisioner.provision("Si","b3lyp").record.xc_functional,"blyp")
            self.assertEqual(provisioner.provision("Si","pz").record.xc_functional,"pz")
            self.assertEqual(provisioner.provision("Si","pw91").record.xc_functional,"pw91")

    def test_soc_prefers_fully_relativistic_cached_candidate(self):
        payload=archive({"Si-sr.UPF":upf("Si"),"Si-fr.UPF":upf("Si",relativity="fully-relativistic")}); provider=self._provider(payload)
        with tempfile.TemporaryDirectory() as tmp:
            record=PseudoProvisioner(tmp,(provider,),lambda *_:payload).provision("Si","pbe",soc=True).record
            self.assertEqual(record.relativity.value,"FULLY_RELATIVISTIC")

    def test_bad_checksum_and_unsafe_archive_leave_no_final_cache(self):
        payload=archive({"../../escape.UPF":upf("Si")}); provider=DownloadableProvider("bad","Bad","1","https://archive.materialscloud.org/bad.tar.gz",hashlib.md5(payload).hexdigest(),("pbe",),1024*1024)
        with tempfile.TemporaryDirectory() as tmp:
            provisioner=PseudoProvisioner(tmp,(provider,),lambda *_:payload)
            with self.assertRaises(ProvisionError): provisioner.provision("Si","pbe")
            self.assertFalse((Path(tmp)/"bad"/"1").exists())

    def test_missing_family_never_falls_back_to_pbe(self):
        payload=archive({"Si.UPF":upf("Si")}); provider=self._provider(payload)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ProvisionError,"BLYP"):
                PseudoProvisioner(tmp,(provider,),lambda *_:payload).provision("Si","b3lyp")

    def test_malformed_upf_never_becomes_a_managed_install(self):
        payload=archive({"Si.UPF":b"not a UPF"}); provider=self._provider(payload)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ProvisionError):
                PseudoProvisioner(tmp,(provider,),lambda *_:payload).provision("Si","pbe")
            self.assertFalse((Path(tmp)/provider.library_id/provider.version).exists())
