from __future__ import annotations
import argparse, json, shutil, tempfile
from pathlib import Path
import numpy as np

def _load_qe(directory):
    from BoltzTraP2 import dft
    xml_files=sorted(Path(directory).rglob("*.xml"))
    if not xml_files: raise ValueError(f"No QE XML save data found below {directory}.")
    staging=Path(tempfile.mkdtemp(prefix="qs-qe-xml-"))
    try:
        shutil.copy2(xml_files[0], staging / "data-file-schema.xml")
        return dft.DFTData(str(staging)), staging
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

def _write_dense_state(data, destination):
    try:
        from .dense import DenseElectronicState
    except ImportError:
        from dense import DenseElectronicState
    state=DenseElectronicState.from_boltztrap_data(data)
    npz=destination.with_suffix(".npz")
    np.savez_compressed(npz, cell_A=state.cell_A, reciprocal_cell=state.reciprocal_cell, kpoints_fractional=state.kpoints_fractional, weights=state.weights, eigenvalues_eV=state.eigenvalues_eV)
    destination.write_text(json.dumps({"schema_version":1,"arrays":npz.name,"fermi_energy_eV":state.fermi_energy_eV,"electron_count":state.electron_count,"spin_mode":state.spin_mode,"spin_degeneracy":state.spin_degeneracy,"volume_A3":state.volume_A3,"number_of_bands":state.number_of_bands,"number_of_kpoints":state.number_of_kpoints,"pbc":list(state.pbc),"provenance":state.provenance}, indent=2, sort_keys=True)+"\n", encoding="utf-8")

def interpolate(qe_directory, output, multiplier):
    from BoltzTraP2 import fite, serialization, sphere
    data, staging=_load_qe(qe_directory)
    try:
        equivalences=sphere.get_equivalences(data.atoms, data.magmom, len(data.kpoints[0]))
        coeffs=fite.fitde3D(data, equivalences)
        serialization.save_calculation(str(output), data, equivalences, coeffs, serialization.gen_bt2_metadata(data, False))
        _write_dense_state(data, Path(output).with_name("dense_state.json"))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

def integrate(bt2_file, output, config_file):
    from BoltzTraP2 import bandlib, fite, serialization, units
    data, equivalences, coeffs, _=serialization.load_calculation(str(bt2_file))
    settings=json.loads(Path(config_file).read_text(encoding="utf-8"))["settings"]
    temperatures=np.asarray(settings["temperatures_kelvin"], dtype=float)
    mus=np.asarray(settings.get("chemical_potentials_ev") or [], dtype=float)
    if not len(mus):
        low, high, count=settings["chemical_potential_range_ev"]; mus=np.linspace(float(low), float(high), int(count))
    if not len(temperatures) or not len(mus): raise ValueError("Transport requires non-empty temperature and chemical-potential grids.")
    eband, vvband, cband=fite.getBTPbands(equivalences, coeffs, np.asarray(data.atoms.get_cell(), dtype=float), True, 1)
    epsilon,dos_values,sigma,_=bandlib.BTPDOS(eband, vvband, cband, npts=400); mur=float(data.fermi)+mus*float(units.eV)
    n, l0, l1, l2, _=bandlib.fermiintegrals(epsilon, dos_values, sigma, mur, temperatures, dosweight=float(getattr(data,"dosweight",2.0)))
    conductivity, seebeck, kappa, _=bandlib.calc_Onsager_coefficients(l0, l1, l2, mur, temperatures, data.get_volume())
    volume_cm3=float(data.get_volume())*(float(units.a0_SI)*100.0)**3
    payload={"schema_version":1,"backend":"BoltzTraP2","backend_version":"26.3.1","temperatures_K":temperatures.tolist(),"chemical_potential_eV":mus.tolist(),"carrier_concentration_cm3":((np.asarray(n,float)+float(data.nelect))/volume_cm3).tolist(),"electrical_conductivity_over_tau":np.asarray(conductivity).tolist(),"seebeck":np.asarray(seebeck).tolist(),"electronic_thermal_conductivity_over_tau":np.asarray(kappa).tolist(),"units":{"temperature":"K","chemical_potential":"eV relative to QE Fermi energy","carrier_concentration":"cm^-3","electrical_conductivity_over_tau":"S m^-1 s","seebeck":"V K^-1","electronic_thermal_conductivity_over_tau":"W m^-1 K^-1 s"},"method_assumptions":{"relaxation_time_model":"UNSPECIFIED_RELAXATION_TIME","spin_degeneracy":float(getattr(data,"dosweight",2.0)),"carrier_concentration_convention":"electron count per volume from BTP2 N + nelect reference","tensor_order":"xx,xy,xz,yx,yy,yz,zx,zy,zz","energy_reference":"chemical potentials are relative to QE Fermi energy"}}
    Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True)+"\n", encoding="utf-8")

def main(argv=None):
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command", required=True)
    i=sub.add_parser("interpolate"); i.add_argument("qe_directory", type=Path); i.add_argument("output", type=Path); i.add_argument("--multiplier", type=int, default=1)
    t=sub.add_parser("integrate"); t.add_argument("bt2_file", type=Path); t.add_argument("output", type=Path); t.add_argument("config", type=Path)
    args=parser.parse_args(argv)
    if args.command=="interpolate": interpolate(args.qe_directory,args.output,args.multiplier)
    else: integrate(args.bt2_file,args.output,args.config)
if __name__=="__main__": main()
