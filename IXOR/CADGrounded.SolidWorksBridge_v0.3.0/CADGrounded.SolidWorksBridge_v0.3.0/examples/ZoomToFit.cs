using System;
using SolidWorks.Interop.sldworks;
public static class BridgeScript
{
    public static object Run(SldWorks app)
    {
        ModelDoc2 model = app.ActiveDoc as ModelDoc2;
        if (model == null) throw new InvalidOperationException("No active document.");
        model.ViewZoomtofit2();
        return new { title = model.GetTitle(), zoom_requested = true, saved_by_script = false };
    }
}
