from .base import ScientificPlotWidget
class DOSPlot(ScientificPlotWidget):
    def _draw(self,result):
        x=result.arrays.get("frequency", result.arrays.get("energy")); y=result.arrays.get("dos",result.arrays.get("total_dos"))
        if x is None: return
        if y is not None: self.axes.plot(x,y,color="#55C7D9",linewidth=1.3,label="DOS")
        for index, component in enumerate(result.metadata.get("components",())):
            values=result.metadata.get("component_values",())
            if index < len(values): self.axes.plot(x,values[index],linewidth=1.0,label=str(component.get("label") or component.get("orbital") or f"channel {index+1}"))
        units=result.metadata.get("energy_unit", result.metadata.get("frequency_unit", "eV"))
        self.axes.set_xlabel(("Frequency" if "frequency" in result.arrays else "Energy")+f" ({units})",color="#D9DCE3"); self.axes.set_ylabel("DOS",color="#D9DCE3"); self.axes.set_title("Phonon DOS" if "frequency" in result.arrays else "Density of States",color="#E8EAF0")
        if len(result.metadata.get("components",())) <= 8:self.axes.legend(facecolor="#17191F",labelcolor="#E8EAF0")
