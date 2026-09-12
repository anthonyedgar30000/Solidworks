using System;
using SolidWorks.Interop.sldworks;
public static class BridgeScript
{
    public static object Run(SldWorks app)
    {
        ModelDoc2 model = app.ActiveDoc as ModelDoc2;
        if (model == null) return new { active_document = false };
        return new { title = model.GetTitle(), path = model.GetPathName(), document_type = model.GetType() };
    }
}
