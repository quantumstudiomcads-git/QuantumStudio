"""Parsers for electronic-property artifacts produced by QE and Bader."""
from __future__ import annotations
import hashlib, re
from pathlib import Path
import numpy as np
from .models import ResultProvenance, ResultStatus, ScientificResult

_NUM=r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?"
def _f(value): return float(str(value).replace("D","E").replace("d","e"))
def _prov(path, *, tool_id, parser_id, **kwargs):
    path=Path(path).resolve()
    return ResultProvenance(kwargs.get("request_id", ""),kwargs.get("execution_id", ""),kwargs.get("task_id", ""),kwargs.get("engine_id", "quantum_espresso"),tool_id,(str(path),),{str(path):hashlib.sha256(path.read_bytes()).hexdigest()},parser_id)

def parse_bxsf(path, **kwargs):
    """Parse the QE fs.x XCrySDen BXSF grid contract."""
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    if "BEGIN_BLOCK_BANDGRID_3D" not in text or "BANDGRID_3D_BANDS" not in text:
        raise ValueError("BXSF artifact is missing a BANDGRID_3D block.")
    lines=[line.strip() for line in text.splitlines()]; start=next(i for i,x in enumerate(lines) if x=="BANDGRID_3D_BANDS")
    try:
        band_count=int(lines[start+1].split()[0])
        dims=tuple(int(x) for x in lines[start+2].split()[:3])
        origin=np.asarray([_f(x) for x in lines[start+3].split()[:3]],float)
        reciprocal=np.asarray([[_f(x) for x in lines[start+4+j].split()[:3]] for j in range(3)],float)
    except (StopIteration,IndexError,ValueError) as error: raise ValueError("BXSF grid header is malformed.") from error
    if len(dims)!=3 or any(x<1 for x in dims) or not np.all(np.isfinite(reciprocal)): raise ValueError("BXSF grid dimensions or reciprocal vectors are invalid.")
    bands=[]; i=start+7
    while i<len(lines):
        if lines[i].startswith("BAND:"):
            i+=1; values=[]
            while i<len(lines) and not lines[i].startswith(("BAND:","END_BANDGRID_3D")):
                try: values.extend(_f(x) for x in lines[i].split())
                except ValueError: pass
                i+=1
            expected=int(np.prod(dims))
            if len(values)!=expected: raise ValueError(f"BXSF band has {len(values)} values; expected {expected}.")
            bands.append(np.asarray(values,float).reshape(dims))
        else: i+=1
    if not bands: raise ValueError("BXSF contains no bands.")
    if len(bands)!=band_count: raise ValueError(f"BXSF contains {len(bands)} bands; header declares {band_count}.")
    energies=np.asarray(bands,float)
    if not np.all(np.isfinite(energies)): raise ValueError("BXSF energies contain non-finite values.")
    fermi=None
    match=re.search(r"Fermi(?:\s+Energy)?\s*[:=]\s*("+_NUM+r")",text,re.I)
    if match: fermi=_f(match.group(1))
    metadata={"grid_dimensions":list(dims),"origin":origin.tolist(),"reciprocal_lattice":reciprocal.tolist(),"fermi_energy_eV":fermi,"bands_crossing_fermi":[],"spin_semantics":kwargs.get("method_metadata",{}).get("spin_treatment","SCALAR_NONSPIN"),"units":{"energy":"eV","reciprocal_lattice":"1/angstrom"}}
    if fermi is not None: metadata["bands_crossing_fermi"]=[i+1 for i,band in enumerate(energies) if float(np.nanmin(band))<=fermi<=float(np.nanmax(band))]
    return ScientificResult("FermiSurfaceResult",ResultStatus.VALID,_prov(path,tool_id="fs.x",parser_id="qe.fs.bxsf",**kwargs),arrays={"energies":energies},metadata=metadata)

def parse_bader_acf(path, *, species=(), z_valence=(), source_density=None, expected_atom_count=None, **kwargs):
    """Parse Bader 1.05 ACF.dat without renormalizing pseudo-valence charges."""
    lines=Path(path).read_text(encoding="utf-8",errors="replace").splitlines(); rows=[]
    for line in lines:
        fields=line.split()
        if not fields or not fields[0].isdigit(): continue
        if len(fields) < 5: raise ValueError("Malformed Bader atom row: expected index, position, population and fields.")
        try: rows.append([int(fields[0])] + [_f(x) for x in fields[1:]])
        except ValueError as error: raise ValueError(f"Malformed Bader atom row: {line.strip()}") from error
    if not rows: raise ValueError("Bader ACF.dat contains no atom rows.")
    n=len(rows)
    if expected_atom_count is not None and n != int(expected_atom_count): raise ValueError(f"Bader atom count mismatch: parsed {n}, expected {expected_atom_count}.")
    atom_index=np.asarray([row[0] for row in rows],int)
    if len(set(atom_index.tolist())) != n: raise ValueError("Bader ACF.dat contains duplicate atom indices.")
    positions=np.asarray([row[1:4] for row in rows],float); population=np.asarray([row[4] for row in rows],float)
    volume=np.asarray([row[6] if len(row)>6 else np.nan for row in rows],float); minimum=np.asarray([row[5] if len(row)>5 else np.nan for row in rows],float)
    if not np.all(np.isfinite(positions)) or not np.all(np.isfinite(population)): raise ValueError("Bader positions or populations contain non-finite values.")
    species_list=list(species) if species else ["" for _ in range(n)]; z=list(z_valence) if z_valence else [np.nan for _ in range(n)]
    if len(species_list)!=n: raise ValueError("Bader species mapping does not match atom count.")
    if len(z)!=n: raise ValueError("Bader pseudo-valence mapping does not match atom count.")
    zarr=np.asarray(z,float); charge=zarr-population
    finite_z=bool(np.all(np.isfinite(zarr)))
    metadata={"species":species_list,"source_density":"pseudo-valence charge density","z_valence":zarr.tolist(),"total_bader_electrons":float(population.sum()),"expected_valence_electrons":float(zarr.sum()) if finite_z else None,"charge_conservation_difference":float(zarr.sum()-population.sum()) if finite_z else None,"total_net_atomic_charge":float(charge.sum()) if finite_z else None,"diagnostics":[] if finite_z else ["Pseudopotential valence charges were unavailable; net charges are not established."]}
    arrays={"atom_index":atom_index,"positions_A":positions,"bader_electrons":population,"basin_volume_A3":volume,"basin_volumes":volume,"minimum_distance_A":minimum,"min_distances":minimum,"pseudo_valence_charge":zarr,"pseudo_valence_charges":zarr,"net_charge":charge}
    status=ResultStatus.VALID if finite_z else ResultStatus.PARTIAL
    return ScientificResult("BaderChargeResult",status,_prov(path,tool_id="bader",parser_id="bader.acf",**kwargs),arrays=arrays,metadata=metadata)

def parse_lowdin(path, *, species=(), expected_atom_count=None, method_metadata=None, **kwargs):
    """Parse QE 7.6 projwfc.x ``Lowdin Charges`` output exactly.

    QE emits one line per atom/projector (s, p, d, f), with additional spin-up,
    spin-down and polarization lines for collinear calculations.
    """
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    has_section=bool(re.search(r"Lowdin\s+Charges\s*:", text, re.I))
    if not has_section and not re.search(r"Atom\s*#", text, re.I):
        raise ValueError("projwfc output contains no Lowdin Charges section.")
    number=_NUM; labels={"s":0,"p":1,"d":2,"f":3,"total":-1}; records=[]; current={}; spin_records={}
    in_section=has_section
    for raw in text.splitlines():
        line=raw.strip()
        if re.search(r"Lowdin\s+Charges\s*:", line, re.I): in_section=True; continue
        if not in_section and not re.search(r"Atom\s*#", line, re.I): continue
        if re.search(r"Atom\s*#", line, re.I): in_section=True
        m=re.search(r"Atom\s*#\s*(\d+)\s*(?:\(([^)]+)\))?:\s*(?:total|Lowdin)\s+charge\s*=\s*(%s)(.*)$" % number,line,re.I)
        if m:
            current={"atom":int(m.group(1)),"species":(m.group(2) or "").strip(),"total":_f(m.group(3))}; records.append(current)
            matched=False
            for pm in re.finditer(r"([spdf])\s*=\s*(%s)" % number,m.group(4),re.I):
                matched=True; records.append({"atom":current["atom"],"species":current["species"],"projector":pm.group(1).lower(),"population":_f(pm.group(2))})
            if not matched: records.append({"atom":current["atom"],"species":current["species"],"projector":"total","population":_f(m.group(3))})
            continue
        if not current: continue
        kind=re.search(r"spin\s+(up|down)|polarization",line,re.I)
        if kind:
            spin=kind.group(1).upper() if kind.group(1) else "DIFFERENCE"
            for pm in re.finditer(r"([spdf])\s*=\s*(%s)" % number,line,re.I):
                spin_records[(current["atom"],pm.group(1).lower(),spin)]=_f(pm.group(2))
    projectors=[r for r in records if "projector" in r]
    if not projectors:
        raise ValueError("Lowdin Charges section contains no projector population rows.")
    atoms=sorted({r["atom"] for r in projectors})
    if expected_atom_count is not None and len(atoms)!=int(expected_atom_count): raise ValueError(f"Lowdin atom count mismatch: parsed {len(atoms)}, expected {expected_atom_count}.")
    if len(set(atoms)) != len(atoms): raise ValueError("Lowdin atom mapping is not unique.")
    species_list=list(species) if species else [next((r["species"] for r in projectors if r["atom"]==atom),"") for atom in atoms]
    if species and len(species_list)!=len(atoms): raise ValueError("Lowdin species mapping does not match atom count.")
    atom_index=[]; population=[]; pup=[]; pdown=[]; diff=[]; labels_out=[]; lvals=[]
    for r in projectors:
        atom=r["atom"]; proj=r["projector"]; up=spin_records.get((atom,proj,"UP")); down=spin_records.get((atom,proj,"DOWN")); delta=spin_records.get((atom,proj,"DIFFERENCE"))
        atom_index.append(atom); population.append(float(r["population"])); pup.append(np.nan if up is None else up); pdown.append(np.nan if down is None else down); diff.append(np.nan if delta is None else delta); labels_out.append(proj); lvals.append(labels[proj])
    finite=bool(np.all(np.isfinite(population)))
    metadata={"species_by_atom":species_list,"species":[species_list[atoms.index(a)] if a in atoms else "" for a in atom_index],"projector_labels":labels_out,"population_semantics":"QE projwfc.x Lowdin projected population","basis_incompleteness":True,"total_projected_population":float(np.sum(population)),"projection_completeness_diagnostic":"QE spilling parameter / atomic projection basis is incomplete; populations are not normalized.","electronic_method":method_metadata or {}}
    arrays={"atom_index":np.asarray(atom_index,int),"projector_index":np.arange(1,len(atom_index)+1,dtype=int),"l":np.asarray(lvals,int),"population":np.asarray(population,float),"population_up":np.asarray(pup,float),"population_down":np.asarray(pdown,float),"spin_difference":np.asarray(diff,float)}
    status=ResultStatus.VALID if finite else ResultStatus.PARSE_FAILED
    return ScientificResult("LowdinPopulationResult",status,_prov(path,tool_id="projwfc.x",parser_id="qe.lowdin",**kwargs),arrays=arrays,metadata=metadata)

def parse_orbital_projection(path, *, method_metadata=None, **kwargs):
    """Parse QE ``filproj`` text written by projwfc.x (k, band, projector weights)."""
    source=Path(path)
    if source.is_dir():
        candidates=sorted(source.glob("*.projwfc_up"))
        if not candidates: raise ValueError("projwfc projection directory contains no .projwfc_up artifact.")
        source=candidates[0]
    lines=source.read_text(encoding="utf-8",errors="replace").splitlines(); rows=[]; projector=None
    header=re.compile(r"^\s*(\d+)\s+(\d+)\s+(\S+)\s+(\S+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)(?:\s+.*)?$")
    sample=re.compile(r"^\s*(\d+)\s+(\d+)\s+(%s)\s*$" % _NUM)
    for line in lines:
        m=header.match(line)
        if m and re.search(r"[A-Za-z]", m.group(4)):
            projector={"projector_index":int(m.group(1)),"atom_index":int(m.group(2)),"species":m.group(3),"orbital_label":m.group(4),"l":int(m.group(6)),"m":int(m.group(7))}; continue
        m=sample.match(line)
        if m and projector is not None:
            rows.append((projector.copy(),int(m.group(1)),int(m.group(2)),_f(m.group(3))))
    if not rows: raise ValueError("projwfc projection artifact contains no k/band/projector rows.")
    arrays={"k_index":np.asarray([r[1] for r in rows],int),"band_index":np.asarray([r[2] for r in rows],int),"projection_weight":np.asarray([r[3] for r in rows],float),"projector_index":np.asarray([r[0]["projector_index"] for r in rows],int),"atom_index":np.asarray([r[0]["atom_index"] for r in rows],int),"l":np.asarray([r[0]["l"] for r in rows],int),"m":np.asarray([r[0]["m"] for r in rows],int)}
    if not np.all(np.isfinite(arrays["projection_weight"])) or np.any(arrays["projection_weight"]<0): raise ValueError("Projection weights are non-finite or negative.")
    metadata={"species":[r[0]["species"] for r in rows],"projector_labels":[r[0]["orbital_label"] for r in rows],"spin_semantics":(method_metadata or {}).get("spin_treatment","SCALAR_NONSPIN"),"electronic_method":method_metadata or {},"projection_semantics":"QE projwfc.x |projection| weights"}
    return ScientificResult("OrbitalCharacterResult",ResultStatus.VALID,_prov(source,tool_id="projwfc.x",parser_id="qe.projwfc.projection",**kwargs),arrays=arrays,metadata=metadata)


def parse_hubbard_parameters(path, **kwargs):
    """Parse QE hp.x final Hubbard-U table (values already printed in eV)."""
    text=Path(path).read_text(encoding="utf-8",errors="replace")
    rows=[]
    in_table=False
    for line in text.splitlines():
        if "Hubbard U parameters:" in line: in_table=True; continue
        if in_table and "=" in line and "---" in line: break
        if in_table:
            parts=line.split()
            if len(parts)>=7 and parts[0].isdigit():
                try: rows.append((int(parts[0]),parts[2],parts[-2],_f(parts[-1])))
                except ValueError: pass
    if not rows: raise ValueError("QE hp.x output contains no final Hubbard U parameter table.")
    return ScientificResult("HubbardParameterResult",ResultStatus.VALID,_prov(path,tool_id="hp.x",parser_id="qe.hp",**kwargs),arrays={"site":np.asarray([r[0] for r in rows],int),"U_eV":np.asarray([r[3] for r in rows],float)},metadata={"species":[r[1] for r in rows],"manifold":[r[2] for r in rows],"units":{"U_eV":"eV"},"backend":"QE hp.x linear response"})
