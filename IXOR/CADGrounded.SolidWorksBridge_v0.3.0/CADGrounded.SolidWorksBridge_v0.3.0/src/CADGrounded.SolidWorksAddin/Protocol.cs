using System.Collections.Generic;

namespace CADGrounded.SolidWorksAddin
{
    public sealed class BridgeRequest
    {
        public string Id { get; set; }
        public string Method { get; set; }
        public Dictionary<string, object> Params { get; set; }
    }

    public sealed class BridgeError
    {
        public string Code { get; set; }
        public string Message { get; set; }
    }

    public sealed class BridgeResponse
    {
        public string Id { get; set; }
        public bool Ok { get; set; }
        public object Result { get; set; }
        public BridgeError Error { get; set; }

        public static BridgeResponse Success(string id, object result)
        {
            return new BridgeResponse
            {
                Id = id,
                Ok = true,
                Result = result,
                Error = null
            };
        }

        public static BridgeResponse Failure(string id, string code, string message)
        {
            return new BridgeResponse
            {
                Id = id,
                Ok = false,
                Result = null,
                Error = new BridgeError { Code = code, Message = message }
            };
        }
    }
}
