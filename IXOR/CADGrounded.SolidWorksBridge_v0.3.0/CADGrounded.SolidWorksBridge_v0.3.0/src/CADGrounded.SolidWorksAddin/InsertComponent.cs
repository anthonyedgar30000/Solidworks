using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace CADGrounded.SolidWorksAddin
{
    internal sealed partial class SolidWorksDispatcher
    {
        private static string Digest(byte[] bytes)
        {
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();
        }

        private static string FileDigest(string path)
        {
            using (var stream = File.OpenRead(path))
            using (var sha = SHA256.Create())
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        private static string Numbers(double[] values)
        {
            return string.Join(",", Array.ConvertAll(values, v => v.ToString("R", CultureInfo.InvariantCulture)));
        }

        private string AssemblyDigest(AssemblyDoc assembly)
        {
            var rows = new List<string>();
            if (assembly.GetComponents(true) is Array components)
                foreach (Component2 c in components)
                    rows.Add(c.Name2 + "|" + c.GetPathName() + "|" + c.ReferencedConfiguration + "|" +
                        c.IsFixed() + "|" + c.IsSuppressed() + "|" + Numbers(ReadTransformArray(c)));
            rows.Sort(StringComparer.Ordinal);
            return Digest(Encoding.UTF8.GetBytes(string.Join("\n", rows)));
        }

        private BridgeResponse InsertComponent(BridgeRequest request)
        {
            var p = request.Params ?? new Dictionary<string, object>();
            ModelDoc2 model = RequireAssembly(out AssemblyDoc assembly);
            string sourcePath = GetString(p, "source_path", "");
            string title = GetString(p, "expected_document_title", "");
            string assemblyPath = GetString(p, "expected_document_path", "");
            string config = GetString(p, "configuration", "Default");
            bool apply = GetBool(p, "apply", false);
            double expectedCount = GetDouble(p, "expected_source_instances", -1);
            double[] rotation = GetDoubleArray(p, "rotation9", 9);
            double[] translation = GetDoubleArray(p, "translation_mm", 3);
            if (!ValidateRotation(rotation, out string rotationError))
                return BridgeResponse.Failure(request.Id, "INVALID_ROTATION", rotationError);
            foreach (double v in translation)
                if (double.IsNaN(v) || double.IsInfinity(v))
                    return BridgeResponse.Failure(request.Id, "INVALID_TRANSLATION", "Finite millimetres required.");
            if (expectedCount < 0 || expectedCount != Math.Floor(expectedCount) || expectedCount > 100000)
                return BridgeResponse.Failure(request.Id, "EXPECTED_COUNT_REQUIRED", "Provide the current source instance count (zero for the first rod). ");
            // Fully qualified drive paths only: no UNC/network fetches or drive-relative paths.
            if (sourcePath.Length < 4 || !char.IsLetter(sourcePath[0]) || sourcePath[1] != ':' || sourcePath[2] != '\\')
                return BridgeResponse.Failure(request.Id, "INVALID_SOURCE_PATH", "Use an absolute local drive path.");
            sourcePath = Path.GetFullPath(sourcePath);
            string extension = Path.GetExtension(sourcePath).ToLowerInvariant();
            if (extension != ".sldprt" && extension != ".sldasm")
                return BridgeResponse.Failure(request.Id, "NATIVE_SOURCE_REQUIRED", "Save STEP as a native SLDPRT or SLDASM first. STEP import is not part of this command.");
            if (!File.Exists(sourcePath))
                return BridgeResponse.Failure(request.Id, "SOURCE_NOT_FOUND", sourcePath);
            if (string.IsNullOrEmpty(config) || string.IsNullOrEmpty(model.GetPathName()) ||
                title != model.GetTitle() || !string.Equals(assemblyPath, model.GetPathName(), StringComparison.OrdinalIgnoreCase))
                return BridgeResponse.Failure(request.Id, "DOCUMENT_MISMATCH", "Provide the exact saved active assembly title/path and a configuration name.");
            if (string.Equals(sourcePath, model.GetPathName(), StringComparison.OrdinalIgnoreCase))
                return BridgeResponse.Failure(request.Id, "SELF_INSERTION", "Cannot insert the active assembly into itself.");

            int count = 0;
            var originals = new List<Component2>();
            var originalTransforms = new List<double[]>();
            if (assembly.GetComponents(true) is Array all)
                foreach (Component2 c in all)
                {
                    originals.Add(c);
                    originalTransforms.Add(ReadTransformArray(c));
                    if (string.Equals(c.GetPathName(), sourcePath, StringComparison.OrdinalIgnoreCase)) count++;
                }
            if (count != expectedCount)
                return BridgeResponse.Failure(request.Id, "SOURCE_COUNT_MISMATCH", "Actual instances=" + count + "; expected=" + expectedCount + ". Query the assembly before retrying.");
            if (originals.Count == 0)
                return BridgeResponse.Failure(request.Id, "EMPTY_ASSEMBLY", "This version requires a nonempty assembly (new components must float).");

            string sourceHash = FileDigest(sourcePath);
            string stateHash = AssemblyDigest(assembly);
            string token = Digest(Encoding.UTF8.GetBytes(model.GetPathName() + "\n" + title + "\n" +
                model.ConfigurationManager.ActiveConfiguration.Name + "\n" + sourcePath + "\n" + config + "\n" + sourceHash + "\n" + stateHash + "\n" +
                Numbers(rotation) + "\n" + Numbers(translation)));
            var result = new Dictionary<string, object>
            {
                ["dry_run"] = !apply, ["applied"] = false, ["source_path"] = sourcePath,
                ["source_sha256"] = sourceHash, ["configuration"] = config,
                ["source_instances_before"] = count, ["preflight_token"] = token,
                ["rotation9"] = rotation, ["translation_mm"] = translation,
                ["document_title"] = title, ["document_path"] = model.GetPathName(),
                ["source_classification"] = "insertion_preflight_only"
            };
            if (!apply) return BridgeResponse.Success(request.Id, result);
            if (GetString(p, "preflight_token", "") != token)
                return BridgeResponse.Failure(request.Id, "STALE_PREFLIGHT", "Run apply=false again; source, pose or assembly state changed.");

            Component2 inserted = null;
            string phase = "loading the native source";
            try
            {
                ModelDoc2 source = _swApp.GetOpenDocumentByName(sourcePath) as ModelDoc2;
                if (source == null)
                {
                    int errors = 0, warnings = 0;
                    source = _swApp.OpenDoc6(sourcePath,
                        extension == ".sldprt" ? (int)swDocumentTypes_e.swDocPART : (int)swDocumentTypes_e.swDocASSEMBLY,
                        (int)swOpenDocOptions_e.swOpenDocOptions_Silent, config, ref errors, ref warnings) as ModelDoc2;
                    if (source == null || errors != 0) throw new InvalidOperationException("OpenDoc6 error=" + errors + ", warnings=" + warnings);
                    result["source_open_warnings"] = warnings;
                }
                if (source.GetSaveFlag()) throw new InvalidOperationException("Source has unsaved changes; save it and repeat preflight.");
                if (source.ConfigurationManager.ActiveConfiguration.Name != config)
                    throw new InvalidOperationException("Open source configuration differs. Activate '" + config + "' in the source, then return to the assembly.");
                int activationError = 0;
                ModelDoc2 activated = _swApp.ActivateDoc3(title, false, (int)swRebuildOnActivation_e.swDontRebuildActiveDoc, ref activationError) as ModelDoc2;
                if (activated == null || !string.Equals(activated.GetPathName(), assemblyPath, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Could not reactivate the expected assembly.");
                if (AssemblyDigest(assembly) != stateHash || FileDigest(sourcePath) != sourceHash)
                    throw new InvalidOperationException("Source/assembly changed during loading. Repeat preflight.");
                phase = "inserting the component";
                // Audit intent before the first assembly mutation.
                _audit.Append(new Dictionary<string, object> { ["method"] = "sw_insert_component", ["stage"] = "intent", ["request"] = result });
                inserted = assembly.AddComponent5(sourcePath, (int)swAddComponentConfigOptions_e.swAddComponentConfigOptions_CurrentSelectedConfig,
                    "", false, "", 0, 0, 0);
                if (inserted == null) throw new InvalidOperationException("AddComponent5 returned null. Query the assembly before retrying.");
                phase = "positioning and verifying";
                if (inserted.IsFixed()) throw new InvalidOperationException("Inserted component is unexpectedly fixed.");
                double[] targetArray = MakeTransformArray(rotation, translation);
                MathUtility math = (MathUtility)_swApp.GetMathUtility();
                inserted.Transform2 = (MathTransform)math.CreateTransform(targetArray);
                if (!model.EditRebuild3()) throw new InvalidOperationException("Rebuild reported failure.");
                if (!TransformMatches(ReadTransformArray(inserted), targetArray, out string mismatch))
                    throw new InvalidOperationException(mismatch);
                if (inserted.ReferencedConfiguration != config) throw new InvalidOperationException("Inserted configuration mismatch.");
                for (int i = 0; i < originals.Count; i++)
                    if (!TransformMatches(ReadTransformArray(originals[i]), originalTransforms[i], out mismatch))
                        throw new InvalidOperationException("Existing component changed: " + originals[i].Name2 + ": " + mismatch);
                result["applied"] = true;
                result["source_classification"] = "applied_and_reverified";
                result["after"] = ComponentSnapshot(inserted);
                result["saved"] = false;
                try { _audit.Append(new Dictionary<string, object> { ["method"] = "sw_insert_component", ["stage"] = "complete", ["result"] = result }); }
                catch (Exception ex) { result["audit_warning"] = ex.Message; }
                return BridgeResponse.Success(request.Id, result);
            }
            catch (Exception ex)
            {
                // Do not delete by selection or falsely claim rollback: report any partial insertion.
                string detail = phase + ": " + ex.Message + (inserted == null ?
                    " No component handle returned; query before retrying." : " Inserted component: " + inserted.Name2 + ". Verification incomplete; do not retry insertion.") + " No files saved.";
                try { _audit.Append(new Dictionary<string, object> { ["method"] = "sw_insert_component", ["stage"] = "failed", ["detail"] = detail }); } catch { }
                return BridgeResponse.Failure(request.Id, "INSERTION_INCOMPLETE", detail);
            }
        }
    }
}
