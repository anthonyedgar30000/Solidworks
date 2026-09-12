using System;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

namespace CADGrounded.SolidWorksAddin
{
    public sealed class PipeServer : IDisposable
    {
        public const string PipeName = "CADGrounded.SolidWorksBridge.v0.1";

        private readonly Func<BridgeRequest, BridgeResponse> _handler;
        private readonly JavaScriptSerializer _json = new JavaScriptSerializer();
        private Thread _thread;
        private volatile bool _running;

        public PipeServer(Func<BridgeRequest, BridgeResponse> handler)
        {
            _handler = handler ?? throw new ArgumentNullException(nameof(handler));
            _json.MaxJsonLength = 1024 * 1024;
        }

        public void Start()
        {
            if (_running)
                return;

            _running = true;
            _thread = new Thread(ServerLoop)
            {
                IsBackground = true,
                Name = "CADGrounded.SolidWorksBridge.PipeServer"
            };
            _thread.Start();
        }

        private void ServerLoop()
        {
            while (_running)
            {
                try
                {
                    using (var pipe = new NamedPipeServerStream(
                        PipeName,
                        PipeDirection.InOut,
                        1,
                        PipeTransmissionMode.Byte,
                        PipeOptions.None))
                    {
                        pipe.WaitForConnection();

                        if (!_running)
                            return;

                        using (var reader = new StreamReader(pipe, new UTF8Encoding(false), false, 4096, true))
                        using (var writer = new StreamWriter(pipe, new UTF8Encoding(false), 4096, true) { AutoFlush = true })
                        {
                            string line = reader.ReadLine();
                            if (string.IsNullOrWhiteSpace(line))
                            {
                                writer.WriteLine(_json.Serialize(BridgeResponse.Failure(null, "EMPTY_REQUEST", "Request line was empty.")));
                                continue;
                            }

                            BridgeRequest request;
                            try
                            {
                                request = _json.Deserialize<BridgeRequest>(line);
                            }
                            catch (Exception ex)
                            {
                                writer.WriteLine(_json.Serialize(BridgeResponse.Failure(null, "INVALID_JSON", ex.Message)));
                                continue;
                            }

                            BridgeResponse response = _handler(request);
                            writer.WriteLine(_json.Serialize(response));
                        }
                    }
                }
                catch (Exception)
                {
                    if (!_running)
                        return;

                    Thread.Sleep(100);
                }
            }
        }

        public void Dispose()
        {
            _running = false;

            // Wake WaitForConnection so the worker can exit promptly.
            try
            {
                using (var client = new NamedPipeClientStream(".", PipeName, PipeDirection.Out))
                {
                    client.Connect(150);
                }
            }
            catch
            {
            }

            try
            {
                _thread?.Join(500);
            }
            catch
            {
            }
        }
    }
}
