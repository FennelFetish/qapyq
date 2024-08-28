from .view import ViewTool

# Right click (?) sets origin point
# Mouse move updates ruler that shows distance in pixels (manhattan distance?)
# Also rectangular measurement? selected via tool bar?

class MeasureTool(ViewTool):
    def __init__(self, tab):
        super().__init__(tab)
        print("MeasureTool Ctor")