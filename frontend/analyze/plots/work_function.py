from __future__ import annotations
from .base import ScientificPlotWidget
class WorkFunctionPlot(ScientificPlotWidget):
 def _draw(self,result):
  meta=result.metadata.get("work_function_analysis",{}); x=result.arrays.get("distance_A",[]); y=result.arrays.get("potential_eV",[]); self.axes.plot(x,y,label="Planar potential"); macro=result.arrays.get("macroscopic_eV");
  if macro is not None: self.axes.plot(x,macro,label="Macroscopic average")
  fermi=(result.scalars.get("fermi_energy") or {}).get("value");
  if fermi is not None: self.axes.axhline(fermi,linestyle="--",label="E_F")
  for level in meta.get("vacuum_levels",[]):
   length=max(x,default=0); start=level["start_fractional"]*length; end=level["end_fractional"]*length; self.axes.axhline(level["level_eV"],linestyle=":",label="E_vac"); self.axes.axvspan(start,end,alpha=.12) if start<=end else (self.axes.axvspan(start,length,alpha=.12),self.axes.axvspan(0,end,alpha=.12))
  phi=(meta.get("work_functions_eV") or [None])[0]; self.axes.set_xlabel("Distance along surface normal (Å)"); self.axes.set_ylabel("Electrostatic potential (eV)"); self.axes.set_title("Work function" + (" — Φ = %.3f eV" % phi if phi is not None else "")); self.axes.legend()

