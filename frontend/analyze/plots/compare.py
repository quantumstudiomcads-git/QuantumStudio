from .base import ScientificPlotWidget
import numpy as np
class ComparisonPlot(ScientificPlotWidget):
    def set_comparison(self, model):
        self._result=model; self.axes.clear(); self.axes.set_facecolor("#111318")
        colors=["#55C7D9","#E8A85C","#9B8CFF","#6FD08C","#E77E9A"]
        handles=[]
        for index,series in enumerate(model.visible_series()):
            result=series.scientific_result; color=colors[index%len(colors)]
            if series.result_type=="BandStructureResult":
                y=np.asarray(result.arrays.get("energies",result.arrays.get("energy",[]))); x=np.asarray(result.arrays.get("path_coordinate",np.arange(len(y))))
                if y.ndim==1:y=y[:,None]
                for band in range(y.shape[1]): self.axes.plot(x,y[:,band],color=color,linewidth=1.0,alpha=.85)
                handles.append(self.axes.plot([],[],color=color,label=series.label)[0])
            elif series.result_type in {"DOSResult","PDOSResult","PhononDOSResult"}:
                x=result.arrays.get("frequency",result.arrays.get("energy")); y=result.arrays.get("dos",result.arrays.get("total_dos"));
                if x is not None and y is not None: handles.append(self.axes.plot(x,y,color=color,label=series.label)[0])
        if handles:self.axes.legend(handles=handles,facecolor="#17191F",labelcolor="#E8EAF0")
        self.axes.set_title(model.title,color="#E8EAF0"); self.axes.set_xlabel("Path coordinate / Energy",color="#D9DCE3"); self.axes.set_ylabel("Value",color="#D9DCE3"); self.canvas.draw_idle()
