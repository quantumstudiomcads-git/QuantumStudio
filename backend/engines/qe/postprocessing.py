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
    if kind in {"qe_projwfc", "qe_lowdin"}: return serialize_namelist("PROJWFC",{"prefix":prefix,"outdir":outdir,"Emin":parameters.get("energy_window",[-10,10])[0],"Emax":parameters.get("energy_window",[-10,10])[1],"DeltaE":parameters.get("delta_e",0.01),"degauss":parameters.get("degauss")})+"\n"
    if kind=="qe_pp":
        plot={"charge":0,"spin":6,"elf":8,"potential":11,"band_decomposed_charge":7}[parameters["plot_kind"]]
        return serialize_namelist("INPUTPP",{"prefix":prefix,"outdir":outdir,"plot_num":plot,"filplot":parameters["plot_kind"]+".dat","kpoint":parameters.get("kpoint"),"kband":parameters.get("kband"),"spin_component":parameters.get("spin_component")})+"\n\n"+serialize_namelist("PLOT",{"iflag":3,"output_format":6,"fileout":parameters.get("artifact", parameters["plot_kind"]+".cube")})+"\n"
    if kind=="qe_q2r": return serialize_namelist("INPUT",parameters)+"\n"
    if kind=="qe_fs":
        mesh=parameters.get("mesh", parameters.get("kmesh", [8,8,8]))
        if not isinstance(mesh,(list,tuple)) or len(mesh)!=3 or any(int(x)<1 for x in mesh): raise InvalidQEParameterError("Fermi-surface mesh must contain three positive integers.")
        # fs.x reads the shared pw.x outdir/prefix and writes XCrySDen BXSF.
        return serialize_namelist("FERMI",{"prefix":prefix,"outdir":outdir,"file_fs":parameters.get("file_fs","fermi_surface"),"deltaE":float(parameters.get("deltaE",1.0))})+"\n"
    if kind=="qe_hp":
        values=dict(parameters); values.setdefault("prefix",prefix); values.setdefault("outdir",outdir)
        return serialize_namelist("INPUTHP",values)+"\n"
    if kind=="qe_matdyn":
        values={"flfrc":"force_constants","flfrq":"phonon_dos.dat","dos":True,"nk1":parameters["mesh"][0],"nk2":parameters["mesh"][1],"nk3":parameters["mesh"][2]}
        return serialize_namelist("INPUT",values)+"\n"
    raise InvalidQEParameterError(f"Unknown QE postprocessor {kind}.")
