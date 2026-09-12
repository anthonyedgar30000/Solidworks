using System;
using System.Collections.Generic;
using System.CodeDom.Compiler;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;
using Microsoft.CSharp;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace CADGrounded.SolidWorksAddin
{
    internal sealed partial class SolidWorksDispatcher
    {
        private sealed class PreparedCode
        {
            public string Source, Title, Path, Hash;
            public DateTime Expires;
            public MethodInfo Entry;
        }
        private readonly Dictionary<string, PreparedCode> _preparedCode = new Dictionary<string, PreparedCode>();

        private BridgeResponse ExecuteCode(BridgeRequest request)
        {
            var p = request.Params ?? new Dictionary<string, object>();
            string source = GetString(p, "source", "");
            string title = GetString(p, "expected_document_title", "");
            string path = GetString(p, "expected_document_path", "");
            bool apply = GetBool(p, "apply", false);
            // Node enforces maximum-control mode. The named pipe is a trusted local transport,
            // not an authentication boundary or a sandbox for submitted code.
            if (source.Length == 0 || source.Length > 200000)
                return BridgeResponse.Failure(request.Id, "SOURCE_SIZE", "Supply 1..200000 characters of C# source.");
            var model = _swApp.ActiveDoc as ModelDoc2;
            if ((model == null && (title != "" || path != "")) ||
                (model != null && (model.GetTitle() != title || !string.Equals(model.GetPathName(), path, StringComparison.OrdinalIgnoreCase))))
                return BridgeResponse.Failure(request.Id, "DOCUMENT_MISMATCH", "Read sw_status and supply its exact active title and path; empty strings require no active document.");
            string hash;
            using (var sha = SHA256.Create())
                hash = BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(source))).Replace("-", "").ToLowerInvariant();
            if (!apply)
            {
                var expired = new List<string>();
                foreach (var item in _preparedCode)
                    if (item.Value.Expires < DateTime.UtcNow) expired.Add(item.Key);
                foreach (string key in expired) _preparedCode.Remove(key);
                if (_preparedCode.Count >= 8)
                    return BridgeResponse.Failure(request.Id, "PREPARE_LIMIT", "Eight preparations pending; execute one or wait ten minutes.");
                using (var provider = new CSharpCodeProvider())
                {
                    var options = new CompilerParameters
                    {
                        GenerateExecutable = false, GenerateInMemory = true,
                        CompilerOptions = "/optimize /platform:x64"
                    };
                    options.ReferencedAssemblies.Add("System.dll");
                    options.ReferencedAssemblies.Add("System.Core.dll");
                    options.ReferencedAssemblies.Add("System.Web.Extensions.dll");
                    options.ReferencedAssemblies.Add("Microsoft.CSharp.dll");
                    options.ReferencedAssemblies.Add(typeof(SldWorks).Assembly.Location);
                    options.ReferencedAssemblies.Add(typeof(swDocumentTypes_e).Assembly.Location);
                    var compiled = provider.CompileAssemblyFromSource(options, source);
                    var diagnostics = new List<string>();
                    foreach (CompilerError error in compiled.Errors) diagnostics.Add(error.ToString());
                    if (compiled.Errors.HasErrors)
                        return BridgeResponse.Failure(request.Id, "COMPILE_FAILED", string.Join("\n", diagnostics));
                    var type = compiled.CompiledAssembly.GetType("BridgeScript", false);
                    var entry = type == null ? null : type.GetMethod("Run", BindingFlags.Public | BindingFlags.Static, null, new[] { typeof(SldWorks) }, null);
                    if (entry == null || entry.ReturnType != typeof(object))
                        return BridgeResponse.Failure(request.Id, "ENTRY_POINT", "Require public static object BridgeScript.Run(SldWorks app).");
                    string token = Guid.NewGuid().ToString("N");
                    _preparedCode[token] = new PreparedCode { Source = source, Title = title, Path = path, Hash = hash, Entry = entry, Expires = DateTime.UtcNow.AddMinutes(10) };
                    return BridgeResponse.Success(request.Id, new { compiled = true, executed = false, preflight_token = token, source_sha256 = hash, diagnostics = diagnostics, expires_in_seconds = 600 });
                }
            }
            string supplied = GetString(p, "preflight_token", "");
            PreparedCode prepared;
            if (!_preparedCode.TryGetValue(supplied, out prepared) || prepared.Expires < DateTime.UtcNow ||
                prepared.Source != source || prepared.Title != title || !string.Equals(prepared.Path, path, StringComparison.OrdinalIgnoreCase))
                return BridgeResponse.Failure(request.Id, "INVALID_PREFLIGHT", "Compile first. Token must match the exact source and document, be unexpired and unused.");
            _preparedCode.Remove(supplied); // Consume before execution; never replay after failure.
            _audit.Append(new Dictionary<string, object> { ["method"] = "sw_execute_code", ["phase"] = "intent", ["source_sha256"] = hash, ["source"] = source, ["document_title"] = title, ["document_path"] = path });
            try
            {
                object result = prepared.Entry.Invoke(null, new object[] { _swApp });
                // Return only plain JSON, never live COM objects. Serialization failure may follow writes.
                var serializer = new JavaScriptSerializer { MaxJsonLength = 1000000, RecursionLimit = 32 };
                object json = serializer.DeserializeObject(serializer.Serialize(result));
                string auditWarning = null;
                try { _audit.Append(new Dictionary<string, object> { ["method"] = "sw_execute_code", ["phase"] = "completed", ["source_sha256"] = hash }); }
                catch (Exception auditError) { auditWarning = auditError.Message; }
                return BridgeResponse.Success(request.Id, new { executed = true, source_sha256 = hash, result = json, audit_warning = auditWarning, verification = "Script completed; inspect operation-specific results and read back CAD state." });
            }
            catch (Exception ex)
            {
                Exception actual = ex is TargetInvocationException && ex.InnerException != null ? ex.InnerException : ex;
                return BridgeResponse.Failure(request.Id, "SCRIPT_FAILED_POSSIBLE_PARTIAL_CHANGES", actual.ToString() + "\nExecution began. Inspect live state before any retry. No automatic rollback.");
            }
        }
    }
}
