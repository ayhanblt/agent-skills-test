namespace MerchantOps;
public static class Provider
{
    public static void MapProvider(this WebApplication app)
    {
        app.MapGet("/api/provider/payments/{id}",(string id,Store store) =>
        {
            using var db=store.Open();
            return Payments.Get(db,id) is { } p ? Results.Ok(new {p.Id,p.State}) : Results.NotFound();
        });
        app.MapPost("/api/provider/webhook",(ProviderEvent input,Store store) =>
        {
            if (string.IsNullOrWhiteSpace(input.Id) || input.Type!="payment.paid")return Results.BadRequest();
            using var db=store.Open();
            using var cmd=db.Sql("UPDATE payments SET state='paid' WHERE id=$id",null,("$id",input.PaymentId));
            return cmd.ExecuteNonQuery()==0 ? Results.NotFound() : Results.Ok();
        });
    }
}
