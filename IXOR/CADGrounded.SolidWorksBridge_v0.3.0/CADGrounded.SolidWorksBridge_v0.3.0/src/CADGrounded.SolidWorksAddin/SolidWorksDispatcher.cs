using System;
using System.Collections;
using System.Collections.Generic;
using SolidWorks.Interop.sldworks;
using SolidWorks.Interop.swconst;

namespace CADGrounded.SolidWorksAddin
{
    internal sealed partial class SolidWorksDispatcher
    {
        private const string BridgeVersion = "0.3.0";
        private const double RotationTolerance = 1e-8;
        private const double TranslationToleranceMm = 1e-4;

        private readonly SldWorks _swApp;
        private readonly AuditWriter _audit = new AuditWriter();

        public SolidWorksDispatcher(SldWorks swApp)
        {
            _swApp = swApp ?? throw new ArgumentNullException(nameof(swApp));
        }

        public BridgeResponse Dispatch(BridgeRequest request)
        {
            if (request == null)
                return BridgeResponse.Failure(null, "NULL_REQUEST", "Request was null.");

            string method = request.Method ?? string.Empty;

            try
            {
                switch (method)
                {
                    case "sw_execute_code":
                        return ExecuteCode(request);

                    case "sw_status":
                        return BridgeResponse.Success(request.Id, Status());

                    case "sw_query_components":
                        return BridgeResponse.Success(request.Id, QueryComponents(request.Params));

                    case "sw_set_transform":
                        return SetTransform(request);

                    case "sw_insert_component":
                        return InsertComponent(request);

                    default:
                        return BridgeResponse.Failure(request.Id, "UNKNOWN_METHOD", "Unknown method: " + method);
                }
            }
            catch (Exception ex)
            {
                return BridgeResponse.Failure(request.Id, "SOLIDWORKS_EXCEPTION", ex.ToString());
            }
        }

        private Dictionary<string, object> Status()
        {
            var result = new Dictionary<string, object>
            {
                ["bridge_version"] = BridgeVersion,
                ["source_classification"] = "verified_from_solidworks_api"
            };

            ModelDoc2 model = _swApp.ActiveDoc as ModelDoc2;
            if (model == null)
            {
                result["active_document"] = null;
                return result;
            }

            result["active_document"] = new Dictionary<string, object>
            {
                ["title"] = model.GetTitle(),
                ["path"] = model.GetPathName(),
                ["document_type"] = DocTypeName(model.GetType())
            };

            return result;
        }

        private Dictionary<string, object> QueryComponents(Dictionary<string, object> parameters)
        {
            ModelDoc2 model = RequireAssembly(out AssemblyDoc assembly);
            bool topLevelOnly = GetBool(parameters, "top_level_only", true);

            object raw = assembly.GetComponents(topLevelOnly);
            var list = new List<object>();

            if (raw is Array array)
            {
                foreach (object item in array)
                {
                    if (item is Component2 component)
                        list.Add(ComponentSnapshot(component));
                }
            }

            return new Dictionary<string, object>
            {
                ["source_classification"] = "verified_from_solidworks_api",
                ["document_title"] = model.GetTitle(),
                ["top_level_only"] = topLevelOnly,
                ["components"] = list
            };
        }

        private BridgeResponse SetTransform(BridgeRequest request)
        {
            Dictionary<string, object> p = request.Params ?? new Dictionary<string, object>();
            ModelDoc2 model = RequireAssembly(out AssemblyDoc assembly);

            string componentName = GetString(p, "component_name", null);
            if (string.IsNullOrWhiteSpace(componentName))
                return BridgeResponse.Failure(request.Id, "MISSING_COMPONENT_NAME", "component_name is required.");

            double[] rotation9 = GetDoubleArray(p, "rotation9", 9);
            double[] translationMm = GetDoubleArray(p, "translation_mm", 3);
            bool apply = GetBool(p, "apply", false);
            string expectedDocumentTitle = GetString(p, "expected_document_title", null);

            if (apply)
            {
                if (string.IsNullOrWhiteSpace(expectedDocumentTitle))
                    return BridgeResponse.Failure(request.Id, "EXPECTED_DOCUMENT_REQUIRED", "apply=true requires expected_document_title from a prior sw_status read.");

                if (!string.Equals(model.GetTitle(), expectedDocumentTitle, StringComparison.Ordinal))
                    return BridgeResponse.Failure(request.Id, "ACTIVE_DOCUMENT_MISMATCH", "Active document title changed. Actual='" + model.GetTitle() + "' expected='" + expectedDocumentTitle + "'.");

                if (!p.TryGetValue("expected_before", out object expectedBeforeRequired) || !(expectedBeforeRequired is Dictionary<string, object> expectedBeforeDict) ||
                    !expectedBeforeDict.ContainsKey("rotation9") || !expectedBeforeDict.ContainsKey("translation_mm"))
                {
                    return BridgeResponse.Failure(request.Id, "EXPECTED_BEFORE_REQUIRED", "apply=true requires expected_before.rotation9 and expected_before.translation_mm from a prior component query.");
                }
            }

            if (!ValidateRotation(rotation9, out string rotationError))
                return BridgeResponse.Failure(request.Id, "INVALID_ROTATION", rotationError);

            Component2 component = FindTopLevelComponentExact(assembly, componentName);
            if (component == null)
                return BridgeResponse.Failure(request.Id, "COMPONENT_NOT_FOUND", "No exact top-level component Name2 match: " + componentName);

            Dictionary<string, object> before = ComponentSnapshot(component);
            double[] beforeTransform = ReadTransformArray(component);

            if (p.TryGetValue("expected_before", out object expectedObj) && expectedObj is Dictionary<string, object> expected)
            {
                double expectedTol = GetDouble(expected, "translation_tolerance_mm", 0.001);
                if (!ExpectedBeforeMatches(beforeTransform, expected, expectedTol, out string mismatch))
                {
                    return BridgeResponse.Failure(request.Id, "STALE_BEFORE_STATE", mismatch);
                }
            }

            var proposed = new Dictionary<string, object>
            {
                ["rotation9"] = rotation9,
                ["translation_mm"] = translationMm
            };

            if (!apply)
            {
                return BridgeResponse.Success(request.Id, new Dictionary<string, object>
                {
                    ["source_classification"] = "requested_transform",
                    ["dry_run"] = true,
                    ["applied"] = false,
                    ["component_name"] = componentName,
                    ["before"] = before,
                    ["proposed"] = proposed
                });
            }

            if (component.IsFixed())
            {
                return BridgeResponse.Failure(
                    request.Id,
                    "COMPONENT_FIXED",
                    "Target component is fixed. v0.1 refuses to unfix components implicitly; float it deliberately before applying a transform.");
            }

            double[] requestedTransform = MakeTransformArray(rotation9, translationMm);
            MathUtility math = (MathUtility)_swApp.GetMathUtility();
            MathTransform target = (MathTransform)math.CreateTransform(requestedTransform);

            var auditRecord = new Dictionary<string, object>
            {
                ["method"] = "sw_set_transform",
                ["document_title"] = model.GetTitle(),
                ["component_name"] = componentName,
                ["before"] = before,
                ["requested"] = proposed
            };

            try
            {
                component.Transform2 = target;
                model.EditRebuild3();

                double[] afterTransform = ReadTransformArray(component);
                Dictionary<string, object> after = ComponentSnapshot(component);

                if (!TransformMatches(afterTransform, requestedTransform, out string verifyError))
                {
                    // Roll back to the exact before transform.
                    MathTransform rollback = (MathTransform)math.CreateTransform(beforeTransform);
                    component.Transform2 = rollback;
                    model.EditRebuild3();

                    auditRecord["success"] = false;
                    auditRecord["verification_error"] = verifyError;
                    auditRecord["rolled_back"] = true;
                    auditRecord["after_failed"] = after;
                    auditRecord["after_rollback"] = ComponentSnapshot(component);
                    _audit.Append(auditRecord);

                    return BridgeResponse.Failure(request.Id, "POST_WRITE_VERIFY_FAILED", verifyError + " Transform was rolled back.");
                }

                auditRecord["success"] = true;
                auditRecord["rolled_back"] = false;
                auditRecord["after"] = after;
                _audit.Append(auditRecord);

                return BridgeResponse.Success(request.Id, new Dictionary<string, object>
                {
                    ["source_classification"] = "applied_and_reverified",
                    ["dry_run"] = false,
                    ["applied"] = true,
                    ["component_name"] = componentName,
                    ["before"] = before,
                    ["requested"] = proposed,
                    ["after"] = after
                });
            }
            catch (Exception ex)
            {
                auditRecord["success"] = false;
                auditRecord["rolled_back"] = false;
                auditRecord["exception"] = ex.ToString();
                _audit.Append(auditRecord);
                throw;
            }
        }

        private ModelDoc2 RequireAssembly(out AssemblyDoc assembly)
        {
            ModelDoc2 model = _swApp.ActiveDoc as ModelDoc2;
            if (model == null)
                throw new InvalidOperationException("No active SOLIDWORKS document.");

            if (model.GetType() != (int)swDocumentTypes_e.swDocASSEMBLY)
                throw new InvalidOperationException("Active SOLIDWORKS document is not an assembly.");

            assembly = (AssemblyDoc)model;
            return model;
        }

        private Component2 FindTopLevelComponentExact(AssemblyDoc assembly, string exactName)
        {
            object raw = assembly.GetComponents(true);
            if (!(raw is Array array))
                return null;

            foreach (object item in array)
            {
                if (item is Component2 component && string.Equals(component.Name2, exactName, StringComparison.Ordinal))
                    return component;
            }

            return null;
        }

        private Dictionary<string, object> ComponentSnapshot(Component2 component)
        {
            double[] t = ReadTransformArray(component);
            var rotation = new double[9];
            Array.Copy(t, 0, rotation, 0, 9);

            var translationMm = new[]
            {
                t[9] * 1000.0,
                t[10] * 1000.0,
                t[11] * 1000.0
            };

            var result = new Dictionary<string, object>
            {
                ["name2"] = component.Name2,
                ["path"] = component.GetPathName(),
                ["fixed"] = component.IsFixed(),
                ["suppressed"] = component.IsSuppressed(),
                ["rotation9"] = rotation,
                ["translation_mm"] = translationMm,
                ["transform_source"] = "Component2.Transform2",
                ["source_classification"] = "verified_from_solidworks_api"
            };

            try
            {
                object rawBox = component.GetBox(false, false);
                if (rawBox is Array boxArray && boxArray.Length >= 6)
                {
                    double[] box = ToDoubleArray(boxArray);
                    result["bounding_box_mm_approx"] = new Dictionary<string, object>
                    {
                        ["min"] = new[] { box[0] * 1000.0, box[1] * 1000.0, box[2] * 1000.0 },
                        ["max"] = new[] { box[3] * 1000.0, box[4] * 1000.0, box[5] * 1000.0 },
                        ["source"] = "Component2.GetBox(false,false)",
                        ["source_classification"] = "approximate_from_solidworks_getbox"
                    };
                }
            }
            catch
            {
                result["bounding_box_mm_approx"] = null;
            }

            return result;
        }

        private static double[] ReadTransformArray(Component2 component)
        {
            MathTransform transform = component.Transform2;
            if (transform == null)
                throw new InvalidOperationException("Component has no Transform2: " + component.Name2);

            object raw = transform.ArrayData;
            if (!(raw is Array array) || array.Length < 16)
                throw new InvalidOperationException("Unexpected Transform2.ArrayData for component: " + component.Name2);

            double[] values = ToDoubleArray(array);
            var result = new double[16];
            Array.Copy(values, result, 16);
            return result;
        }

        private static double[] MakeTransformArray(double[] rotation9, double[] translationMm)
        {
            var a = new double[16];
            Array.Copy(rotation9, 0, a, 0, 9);
            a[9] = translationMm[0] / 1000.0;
            a[10] = translationMm[1] / 1000.0;
            a[11] = translationMm[2] / 1000.0;
            a[12] = 1.0;
            a[13] = 0.0;
            a[14] = 0.0;
            a[15] = 0.0;
            return a;
        }

        private static bool ExpectedBeforeMatches(double[] actual, Dictionary<string, object> expected, double translationToleranceMm, out string mismatch)
        {
            mismatch = null;

            if (expected.ContainsKey("rotation9"))
            {
                double[] r = GetDoubleArray(expected, "rotation9", 9);
                for (int i = 0; i < 9; i++)
                {
                    if (Math.Abs(actual[i] - r[i]) > RotationTolerance)
                    {
                        mismatch = "expected_before rotation mismatch at index " + i + ".";
                        return false;
                    }
                }
            }

            if (expected.ContainsKey("translation_mm"))
            {
                double[] tr = GetDoubleArray(expected, "translation_mm", 3);
                for (int i = 0; i < 3; i++)
                {
                    double actualMm = actual[9 + i] * 1000.0;
                    if (Math.Abs(actualMm - tr[i]) > translationToleranceMm)
                    {
                        mismatch = "expected_before translation mismatch at index " + i + ": actual=" + actualMm + " mm expected=" + tr[i] + " mm.";
                        return false;
                    }
                }
            }

            return true;
        }

        private static bool TransformMatches(double[] actual, double[] requested, out string error)
        {
            for (int i = 0; i < 9; i++)
            {
                if (Math.Abs(actual[i] - requested[i]) > RotationTolerance)
                {
                    error = "Rotation verification failed at index " + i + ": actual=" + actual[i] + " requested=" + requested[i];
                    return false;
                }
            }

            for (int i = 9; i <= 11; i++)
            {
                double deltaMm = Math.Abs(actual[i] - requested[i]) * 1000.0;
                if (deltaMm > TranslationToleranceMm)
                {
                    error = "Translation verification failed at Transform2 index " + i + ": delta=" + deltaMm + " mm.";
                    return false;
                }
            }

            error = null;
            return true;
        }

        private static bool ValidateRotation(double[] r, out string error)
        {
            if (r == null || r.Length != 9)
            {
                error = "rotation9 must contain exactly 9 values.";
                return false;
            }

            foreach (double v in r)
            {
                if (double.IsNaN(v) || double.IsInfinity(v))
                {
                    error = "rotation9 contains a non-finite value.";
                    return false;
                }
            }

            double[] row0 = { r[0], r[1], r[2] };
            double[] row1 = { r[3], r[4], r[5] };
            double[] row2 = { r[6], r[7], r[8] };

            if (Math.Abs(Norm(row0) - 1.0) > RotationTolerance ||
                Math.Abs(Norm(row1) - 1.0) > RotationTolerance ||
                Math.Abs(Norm(row2) - 1.0) > RotationTolerance ||
                Math.Abs(Dot(row0, row1)) > RotationTolerance ||
                Math.Abs(Dot(row0, row2)) > RotationTolerance ||
                Math.Abs(Dot(row1, row2)) > RotationTolerance)
            {
                error = "rotation9 is not orthonormal within tolerance.";
                return false;
            }

            double det =
                r[0] * (r[4] * r[8] - r[5] * r[7]) -
                r[1] * (r[3] * r[8] - r[5] * r[6]) +
                r[2] * (r[3] * r[7] - r[4] * r[6]);

            if (Math.Abs(det - 1.0) > RotationTolerance)
            {
                error = "rotation9 determinant must be +1; got " + det + ".";
                return false;
            }

            error = null;
            return true;
        }

        private static double Norm(double[] a) => Math.Sqrt(Dot(a, a));
        private static double Dot(double[] a, double[] b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

        private static string DocTypeName(int type)
        {
            if (type == (int)swDocumentTypes_e.swDocPART) return "part";
            if (type == (int)swDocumentTypes_e.swDocASSEMBLY) return "assembly";
            if (type == (int)swDocumentTypes_e.swDocDRAWING) return "drawing";
            return "unknown";
        }

        private static string GetString(Dictionary<string, object> p, string key, string defaultValue)
        {
            if (p != null && p.TryGetValue(key, out object value) && value != null)
                return Convert.ToString(value);
            return defaultValue;
        }

        private static bool GetBool(Dictionary<string, object> p, string key, bool defaultValue)
        {
            if (p != null && p.TryGetValue(key, out object value) && value != null)
                return Convert.ToBoolean(value);
            return defaultValue;
        }

        private static double GetDouble(Dictionary<string, object> p, string key, double defaultValue)
        {
            if (p != null && p.TryGetValue(key, out object value) && value != null)
                return Convert.ToDouble(value);
            return defaultValue;
        }

        private static double[] GetDoubleArray(Dictionary<string, object> p, string key, int expectedLength)
        {
            if (p == null || !p.TryGetValue(key, out object value) || value == null)
                throw new ArgumentException(key + " is required.");

            double[] result;
            if (value is Array array)
            {
                result = ToDoubleArray(array);
            }
            else if (value is ArrayList list)
            {
                result = new double[list.Count];
                for (int i = 0; i < list.Count; i++)
                    result[i] = Convert.ToDouble(list[i]);
            }
            else
            {
                throw new ArgumentException(key + " must be an array.");
            }

            if (result.Length != expectedLength)
                throw new ArgumentException(key + " must contain exactly " + expectedLength + " values.");

            return result;
        }

        private static double[] ToDoubleArray(Array array)
        {
            var result = new double[array.Length];
            for (int i = 0; i < array.Length; i++)
                result[i] = Convert.ToDouble(array.GetValue(i));
            return result;
        }
    }
}
