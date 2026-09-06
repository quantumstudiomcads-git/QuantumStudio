"""Deterministic QE post-processing input writers (C8A), without parsing."""
from __future__ import annotations
from .writer import serialize_namelist, pw_input
from .models import InvalidQEParameterError

def pw_bands_input(parameters, structure, context, pseudos):
    points=parameters.get("band_path")
    if not isinstance(points,list) or len(points)<2: raise InvalidQEParameterError("Band structure requires explicit band_path.")
    text=pw_input("qe_pw_nscf", parameters, structure, context, pseudos).replace("calculation = 'nscf'", "calculation = 'bands'")
    return text

def post_input(kind, parameters, context):
    prefix,outdir=context.prefix,context.outdir
    if kind=="qe_bands": return serialize_namelist("BANDS",{"prefix":prefix,"outdir":outdir,"filband":parameters.get("filband","bands.dat")})+"\n"
    if kind=="qe_dos":
        window=parameters.get("energy_window",[])
        if not isinstance(window,(list,tuple)) or len(window)!=2 or float(window[1])<=float(window[0]): raise InvalidQEParameterError("DOS energy_window requires Emin < Emax.")
        return serialize_namelist("DOS",{"prefix":prefix,"outdir":outdir,"fildos":"dos.dat","Emin":float(window[0]),"Emax":float(window[1]),"DeltaE":parameters.get("delta_e",0.01),"degauss":parameters.get("degauss")})+"\n"
    if kind in {"qe_projwfc", "qe_lowdin"}: return serialize_namelist("PROJWFC",{"prefix":prefix,"outdir":outdir,"Emin":parameters.get("energy_window",[-10,10])[0],"Emax":parameters.get("energy_window",[-10,10])[1],"DeltaE":parameters.get("delta_e",0.01),"degauss":parameters.get("degauss"),"filproj":parameters.get("filproj")})+"\n"
    if kind=="qe_pp":
        plot={"charge":0,"spin":6,"elf":8,"potential":11,"band_decomposed_charge":7}[parameters["plot_kind"]]
        return serialize_namelist("INPUTPP",{"prefix":prefix,"outdir":outdir,"plot_num":plot,"filplot":parameters["plot_kind"]+".dat","kpoint":parameters.get("kpoint"),"kband":parameters.get("kband"),"spin_component":parameters.get("spin_component")})+"\n\n"+serialize_namelist("PLOT",{"iflag":3,"output_format":6,"fileout":parameters.get("artifact", parameters["plot_kind"]+".cube")})+"\n"
    if kind=="qe_q2r":
        values={"fildyn":parameters.get("fildyn","dynamical-matrix"),"flfrc":parameters.get("flfrc","force_constants"),"zasr":parameters.get("zasr","crystal")}
        return serialize_namelist("INPUT",values)+"\n"
    if kind=="qe_fs":
        mesh=parameters.get("mesh", parameters.get("kmesh", [8,8,8]))
        if not isinstance(mesh,(list,tuple)) or len(mesh)!=3 or any(int(x)<1 for x in mesh): raise InvalidQEParameterError("Fermi-surface mesh must contain three positive integers.")
        # fs.x reads the shared pw.x outdir/prefix and writes XCrySDen BXSF.
        return serialize_namelist("FERMI",{"prefix":prefix,"outdir":outdir,"file_fs":parameters.get("file_fs","fermi_surface"),"deltaE":float(parameters.get("deltaE",1.0))})+"\n"
    if kind=="qe_hp":
        values={key: value for key, value in dict(parameters).items()
                if key in {"prefix", "outdir", "iverbosity", "max_seconds", "nq1", "nq2", "nq3",
                           "skip_equivalence_q", "determine_num_pert_only", "determine_q_mesh_only",
                           "find_atpert", "docc_thr", "start_q", "last_q", "sum_pertq", "compute_hp"}}
        qmesh=parameters.get("qmesh")
        if isinstance(qmesh,(list,tuple)) and len(qmesh)==3:
            values.update({"nq1":int(qmesh[0]),"nq2":int(qmesh[1]),"nq3":int(qmesh[2])})
        values.setdefault("prefix",prefix); values.setdefault("outdir",outdir)
        return serialize_namelist("INPUTHP",values)+"\n"
    if kind=="qe_dynmat":
        direction=parameters.get("direction", [1.0,0.0,0.0])
        if not isinstance(direction,(list,tuple)) or len(direction)!=3: raise InvalidQEParameterError("dynmat direction requires three components.")
        values={"fildyn":parameters.get("fildyn","polar_gamma"),"asr":parameters.get("asr","crystal"),"q(1)":float(direction[0]),"q(2)":float(direction[1]),"q(3)":float(direction[2]),"filout":parameters.get("filout","dynmat.out"),"fileig":parameters.get("fileig","modes.eig"),"lperm":parameters.get("purpose") != "raman"}; values.update({"lplasma":True} if parameters.get("purpose")=="phonon_dielectric" else {})
        return serialize_namelist("INPUT",values)+"\n"
    if kind=="qe_matdyn":
        mesh=parameters.get("mesh",[12,12,12])
        if not isinstance(mesh,(list,tuple)) or len(mesh)!=3 or any(int(x)<1 for x in mesh): raise InvalidQEParameterError("matdyn mesh must contain three positive integers.")
        values={"flfrc":parameters.get("flfrc","force_constants"),"asr":parameters.get("asr","crystal"),"dos":parameters.get("mode")=="dos","nk1":int(mesh[0]),"nk2":int(mesh[1]),"nk3":int(mesh[2]),"fldos":parameters.get("fldos","matdyn.dos"),"flfrq":parameters.get("flfrq","matdyn.freq"),"deltaE":float(parameters.get("deltaE",1.0))}
        text=serialize_namelist("INPUT",values)+"\n"
        if parameters.get("mode")=="dispersion":
            path=parameters.get("q_path")
            if not isinstance(path,list) or not path: raise InvalidQEParameterError("Phonon dispersion requires an explicit q_path.")
            text=serialize_namelist("INPUT",{key:value for key,value in values.items() if key not in {"dos","nk1","nk2","nk3","fldos","deltaE"}}|{"q_in_cryst_coord":True})+"\n"+str(len(path))+"\n"+"\n".join(" ".join(str(float(x)) for x in (point.get("coordinates", point) if isinstance(point, dict) else point)) for point in path)+"\n"
        return text
    raise InvalidQEParameterError(f"Unknown QE postprocessor {kind}.")
