using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Win32;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swpublished;

namespace CADGrounded.SolidWorksAddin
{
    [ComVisible(true)]
    [Guid("CA55FBFC-011B-4868-9226-0A2362148F93")]
    public sealed class Addin : ISwAddin
    {
        private const string AddinTitle = "CADGrounded SolidWorks Bridge";
        private const string AddinDescription = "Narrow, audited CAD-grounded MCP bridge for SOLIDWORKS.";

        private SldWorks _swApp;
        private int _cookie;
        private Control _uiMarshal;
        private PipeServer _pipeServer;
        private SolidWorksDispatcher _dispatcher;

        public bool ConnectToSW(object ThisSW, int Cookie)
        {
            _swApp = (SldWorks)ThisSW;
            _cookie = Cookie;

            _swApp.SetAddinCallbackInfo2(0, this, _cookie);

            // Create the Control on SOLIDWORKS' UI thread. Pipe requests arrive on
            // worker threads and are synchronously marshalled back here before any
            // SOLIDWORKS COM object is touched.
            _uiMarshal = new Control();
            _uiMarshal.CreateControl();
            var forceHandleCreation = _uiMarshal.Handle;

            _dispatcher = new SolidWorksDispatcher(_swApp);
            _pipeServer = new PipeServer(DispatchOnUiThread);
            _pipeServer.Start();

            return true;
        }

        public bool DisconnectFromSW()
        {
            try
            {
                _pipeServer?.Dispose();
            }
            catch
            {
                // SOLIDWORKS shutdown should not be blocked by bridge cleanup.
            }

            try
            {
                _uiMarshal?.Dispose();
            }
            catch
            {
            }

            _pipeServer = null;
            _dispatcher = null;
            _uiMarshal = null;
            _swApp = null;

            return true;
        }

        private BridgeResponse DispatchOnUiThread(BridgeRequest request)
        {
            if (_uiMarshal == null || _uiMarshal.IsDisposed)
            {
                return BridgeResponse.Failure(request?.Id, "UI_MARSHAL_UNAVAILABLE", "SOLIDWORKS UI marshal is unavailable.");
            }

            try
            {
                if (_uiMarshal.InvokeRequired)
                {
                    return (BridgeResponse)_uiMarshal.Invoke(
                        new Func<BridgeRequest, BridgeResponse>(_dispatcher.Dispatch),
                        request);
                }

                return _dispatcher.Dispatch(request);
            }
            catch (Exception ex)
            {
                return BridgeResponse.Failure(request?.Id, "DISPATCH_EXCEPTION", ex.ToString());
            }
        }

        [ComRegisterFunction]
        public static void RegisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString().ToUpperInvariant() + "}";

            using (RegistryKey addinKey = Registry.LocalMachine.CreateSubKey(@"SOFTWARE\SolidWorks\Addins\" + guid))
            {
                addinKey.SetValue(null, 0, RegistryValueKind.DWord);
                addinKey.SetValue("Title", AddinTitle, RegistryValueKind.String);
                addinKey.SetValue("Description", AddinDescription, RegistryValueKind.String);
            }

            using (RegistryKey startupKey = Registry.CurrentUser.CreateSubKey(@"Software\SolidWorks\AddInsStartup"))
            {
                startupKey.SetValue(guid, 1, RegistryValueKind.DWord);
            }
        }

        [ComUnregisterFunction]
        public static void UnregisterFunction(Type t)
        {
            string guid = "{" + t.GUID.ToString().ToUpperInvariant() + "}";

            try
            {
                Registry.LocalMachine.DeleteSubKeyTree(@"SOFTWARE\SolidWorks\Addins\" + guid, false);
            }
            catch
            {
            }

            try
            {
                using (RegistryKey startupKey = Registry.CurrentUser.OpenSubKey(@"Software\SolidWorks\AddInsStartup", true))
                {
                    startupKey?.DeleteValue(guid, false);
                }
            }
            catch
            {
            }
        }
    }
}
