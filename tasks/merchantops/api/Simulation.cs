namespace MerchantOps;
public static class Simulation
{
    // Local fixtures only. Failpoints are dormant unless the host explicitly enables them.
    public static bool At(HttpRequest req,string point) =>
        Environment.GetEnvironmentVariable("MO_ENABLE_FAULTS")=="1" &&
        req.Headers["X-Simulate-Fault"].ToString()==point;
}
