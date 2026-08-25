from backend.engines.qe.writer import serialize_namelist
from backend.engines.epw.models import EPWSettings
def epw_input(settings:EPWSettings,prefix,outdir,seed):
 return serialize_namelist('INPUTEPW',{'prefix':prefix,'outdir':outdir,'dvscf_dir':'../qe_ph_epw','wannierize':False,'epbwrite':True,'epbread':False,'elph':True,'nk1':settings.nk_coarse[0],'nk2':settings.nk_coarse[1],'nk3':settings.nk_coarse[2],'nq1':settings.nq_coarse[0],'nq2':settings.nq_coarse[1],'nq3':settings.nq_coarse[2],'nkf1':settings.nk_fine[0],'nkf2':settings.nk_fine[1],'nkf3':settings.nk_fine[2],'nqf1':settings.nq_fine[0],'nqf2':settings.nq_fine[1],'nqf3':settings.nq_fine[2],'filukk':seed})+'\n'
