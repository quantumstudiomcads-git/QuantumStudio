"""Synthetic content-only package audit regressions; no customer/build data writes."""
import io
import zipfile
from unittest.mock import patch
import numpy as np
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from scripts import windows_packaging as audit

TRUSTED = "scipy/stats/_sobol_direction_numbers.npz"


def classify(tmp_path, data, relative="runtime.dll"):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return audit.audit_customer_package_contents(tmp_path)


def npy(array=None):
    buf = io.BytesIO()
    np.save(buf, np.arange(12, dtype=np.int64) if array is None else array, allow_pickle=False)
    return buf.getvalue()


def archive(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


@pytest.mark.parametrize("marker", audit._PRIVATE_KEY_MARKERS)
def test_binary_parser_literals_are_not_private_material(tmp_path, marker):
    data = b"MZ\0" + marker + b"\0parser table\0" + marker.replace(b"BEGIN", b"END")
    assert classify(tmp_path, data)["valid"]
    assert classify(tmp_path, marker+b"\n"+marker.replace(b"BEGIN", b"END"))["valid"]


def test_real_embedded_private_key_rejected(tmp_path):
    # Fixed synthetic test seed, never a production identity.
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    assert not classify(tmp_path, b"MZ\0" + pem + b"\0binary")["valid"]


@pytest.mark.parametrize("marker", audit._PRIVATE_KEY_MARKERS)
@pytest.mark.parametrize("body", [b"A"*80+b"\n", b"A"*80, b"A"*(audit.MAX_PEM_BYTES+100)], ids=["truncated-line", "truncated-no-newline", "oversized"])
def test_truncated_or_oversized_plausible_key_fails_closed(tmp_path, marker, body):
    assert not classify(tmp_path, marker+b"\n"+body)["valid"]


def test_pem_crosses_stream_boundary(tmp_path):
    pem=b"-----BEGIN PRIVATE KEY-----\n"+b"A"*80+b"\n-----END PRIVATE KEY-----"
    assert not classify(tmp_path,b"x"*(1024*1024-10)+pem)["valid"]


@pytest.mark.parametrize("data", [b'{"format":"quantum-studio-protected-key"}', b'licence-signing-ed25519', b'RESEND_API_KEY'])
def test_existing_protected_schema_and_server_credentials_rejected(tmp_path,data):
    assert not classify(tmp_path,data)["valid"]


def test_valid_numeric_npz_only_at_exact_scientific_path(tmp_path):
    data=archive([("poly.npy",npy()),("vinit.npy",npy())])
    assert classify(tmp_path,data,TRUSTED)["valid"]
    target=tmp_path/TRUSTED
    assert audit.audit_sensitive_payload_content(target)==("archive-container-forbidden",)
    target.unlink()
    assert not classify(tmp_path,data,"scipy/stats/arbitrary.npz")["valid"]


@pytest.mark.parametrize("name", ["../key.npy","/key.npy","C:/key.npy","dir/key.npy","dir\\key.npy","payload.zip","payload.py","key.pem","settings.json","runtime.exe"])
def test_npz_unsafe_members_rejected(tmp_path,name):
    assert not classify(tmp_path,archive([(name,npy())]),TRUSTED)["valid"]


@pytest.mark.parametrize("data", [b"PK\x03\x04bad",archive([("x.npy",b"not-numpy")]),archive([("x.npy",npy()+b"hidden")]),archive([("x.npy",archive([("secret.pem",b"secret")]))])])
def test_invalid_npz_and_nested_archives_rejected(tmp_path,data):
    assert not classify(tmp_path,data,TRUSTED)["valid"]


def test_npz_duplicate_and_symlink_rejected(tmp_path):
    assert not classify(tmp_path,archive([("x.npy",npy()),("X.npy",npy())]),TRUSTED)["valid"]
    info=zipfile.ZipInfo("x.npy");info.create_system=3;info.external_attr=0o120777<<16
    assert not classify(tmp_path,archive([(info,npy())]),TRUSTED)["valid"]


def test_npz_limits_and_object_arrays_rejected(tmp_path):
    assert not classify(tmp_path,archive([(f"a{i}.npy",npy()) for i in range(audit.MAX_NPZ_MEMBERS+1)]),TRUSTED)["valid"]
    with patch.object(audit,"MAX_NPZ_BYTES",1000):
        assert not classify(tmp_path,archive([("a.npy",npy(np.zeros(2000,dtype=np.uint8)))]),TRUSTED)["valid"]
    out=io.BytesIO();np.save(out,np.array([{}],dtype=object))
    assert not classify(tmp_path,archive([("a.npy",out.getvalue())]),TRUSTED)["valid"]


@pytest.mark.parametrize("data", [b"RESEND_API_KEY",b"quantum-studio-protected-key",b"SQLite format 3\0",b"PK\x03\x04nested",b'{"signing_key_path":"hidden"}',b"-----BEGIN PRIVATE KEY-----\n"+b"A"*80+b"\n-----END PRIVATE KEY-----"])
def test_npz_array_cannot_hide_protected_content(tmp_path,data):
    assert not classify(tmp_path,archive([("a.npy",npy(np.frombuffer(data,dtype=np.uint8)))]),TRUSTED)["valid"]
