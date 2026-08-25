from .base import ScientificPlotWidget
class BandPlot(ScientificPlotWidget):
    def _draw(self,result):
        import numpy as np
        x=result.arrays.get("path_coordinate",result.arrays.get("kpoint")); y=result.arrays.get("energies",result.arrays.get("energy"));
        if y is None:return
        y=np.asarray(y); x=np.arange(len(y)) if x is None else np.asarray(x); y=y[:,None] if y.ndim==1 else y
        for i in range(y.shape[1]): self.axes.plot(x,y[:,i],color="#55C7D9",linewidth=1.2)
        f=result.metadata.get("fermi_energy", result.scalars.get("fermi_energy",{}).get("value"))
        if f is not None:self.axes.axhline(float(f),color="#E8A85C",linewidth=1,linestyle="--")
        self.axes.set_xlabel("Path coordinate",color="#D9DCE3"); self.axes.set_ylabel("Energy (eV)",color="#D9DCE3"); self.axes.set_title("Band Structure",color="#E8EAF0")
