from backend.engines.qe.writer import serialize_namelist
from backend.engines.epw.models import EPWSettings
def epw_input(settings:EPWSettings,prefix,outdir,seed,*,dvscf_dir="../qe_out/_ph0/"):
 values={"prefix":prefix,"outdir":outdir,"dvscf_dir":dvscf_dir,"elph":True,"epbwrite":True,"epbread":False,"epwwrite":True,"epwread":False,"wannierize":False,"nbndsub":settings.nbndsub,"fsthick":settings.fsthick_ev,"degaussw":settings.degaussw_ev,"degaussq":settings.degaussq_mev,"a2f":settings.a2f,"phonselfen":settings.a2f,"eliashberg":settings.eliashberg,"tc_linear":settings.tc_linear,"muc":settings.mu_star,"tc_linear_solver":settings.tc_linear_solver,"nk1":settings.nk_coarse[0],"nk2":settings.nk_coarse[1],"nk3":settings.nk_coarse[2],"nq1":settings.nq_coarse[0],"nq2":settings.nq_coarse[1],"nq3":settings.nq_coarse[2],"nkf1":settings.nk_fine[0],"nkf2":settings.nk_fine[1],"nkf3":settings.nk_fine[2],"nqf1":settings.nq_fine[0],"nqf2":settings.nq_fine[1],"nqf3":settings.nq_fine[2],"filukk":seed}
 if settings.auto_projections or settings.scdm_proj:
  from backend.engines.epw.scdm import validate_scdm_contract
  validate_scdm_contract(num_wann=settings.nbndsub, auto_projections=settings.auto_projections, scdm_proj=settings.scdm_proj, entanglement=settings.scdm_entanglement, mu_eV=float(settings.scdm_mu_eV), sigma_eV=float(settings.scdm_sigma_eV))
  values.update(auto_projections=True, scdm_proj=True, scdm_entanglement=settings.scdm_entanglement, scdm_mu=settings.scdm_mu_eV, scdm_sigma=settings.scdm_sigma_eV, wannierize=True)
 return serialize_namelist("INPUTEPW",values)+"\n"
