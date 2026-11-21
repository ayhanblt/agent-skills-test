namespace MerchantOps;
public static class Ledger
{
    public static void MapLedger(this WebApplication app)
    {
        app.MapGet("/api/ledger/{paymentId}", (string paymentId,Store store) =>
        {
            using var db=store.Open();
            return Payments.Get(db,paymentId) is null ? Results.NotFound() : Results.Ok(Array.Empty<object>());
        });
        app.MapPost("/api/financial-events", (FinancialEvent input) => Results.StatusCode(501));
    }
}
