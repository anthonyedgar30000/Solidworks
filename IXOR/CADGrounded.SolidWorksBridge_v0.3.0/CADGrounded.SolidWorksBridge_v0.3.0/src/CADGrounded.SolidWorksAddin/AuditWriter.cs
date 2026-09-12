using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;

namespace CADGrounded.SolidWorksAddin
{
    internal sealed class AuditWriter
    {
        private readonly object _gate = new object();
        private readonly string _path;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();

        public AuditWriter()
        {
            string dir = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "CADGrounded",
                "SolidWorksBridge");

            Directory.CreateDirectory(dir);
            _path = Path.Combine(dir, "audit.jsonl");
        }

        public void Append(Dictionary<string, object> record)
        {
            if (record == null)
                return;

            record["utc"] = DateTime.UtcNow.ToString("O");

            string line = _json.Serialize(record);
            lock (_gate)
            {
                File.AppendAllText(_path, line + Environment.NewLine, new UTF8Encoding(false));
            }
        }
    }
}
