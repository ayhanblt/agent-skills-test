using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace MerchantOps;
public static class Provider
{
    public static void MapProvider(this WebApplication app)
    {
        using (var db = app.Services.GetRequiredService<Store>().Open())
        using (var cmd = db.Sql("CREATE TABLE IF NOT EXISTS provider_events(id TEXT PRIMARY KEY, digest BLOB NOT NULL)"))
            cmd.ExecuteNonQuery();
        app.MapGet("/api/provider/payments/{id}",(string id,Store store) =>
        {
            using var db=store.Open();
            return Payments.Get(db,id) is { } p ? Results.Ok(new {p.Id,p.State}) : Results.NotFound();
        });
        app.MapPost("/api/provider/webhook", Receive);
    }

    static async Task<IResult> Receive(HttpRequest req, Store store, TimeProvider clock, CancellationToken ct)
    {
        var body = await Documents.ReadLimited(req,16_384,ct);
        if(body is null)return Results.StatusCode(413);
        var time = req.Headers["X-Provider-Time"].ToString();
        var signature = req.Headers["X-Provider-Signature"].ToString();
        var secret = Environment.GetEnvironmentVariable("MO_PROVIDER_SECRET");
        var now=clock.GetUtcNow().ToUnixTimeSeconds();
        if(string.IsNullOrEmpty(secret) || !long.TryParse(time,NumberStyles.None,CultureInfo.InvariantCulture,out var seconds)
            || time!=seconds.ToString(CultureInfo.InvariantCulture) || seconds<now-300 || seconds>now+300
            || signature.Length!=64 || signature.Any(c=>!(c is >= '0' and <= '9' or >= 'a' and <= 'f')))
            return Results.Unauthorized();
        byte[] signed = [..Encoding.UTF8.GetBytes(time+"."),..body];
        var mac = HMACSHA256.HashData(Encoding.UTF8.GetBytes(secret), signed);
        if(!CryptographicOperations.FixedTimeEquals(mac,Convert.FromHexString(signature)))return Results.Unauthorized();
        ProviderEvent? ev;
        try { ev = JsonSerializer.Deserialize<ProviderEvent>(body,JsonSerializerOptions.Web); }
        catch(JsonException) {return Results.BadRequest();}
        if(ev is null || string.IsNullOrWhiteSpace(ev.Id) || ev.Type!="payment.paid" || string.IsNullOrWhiteSpace(ev.PaymentId))
            return Results.BadRequest();
        var digest=SHA256.HashData(body);
        using var db=store.Open();
        using var tx=db.BeginTransaction();
        using(var seen=db.Sql("SELECT digest FROM provider_events WHERE id=$id",tx,("$id",ev.Id)))
            if(seen.ExecuteScalar() is byte[] prior)return prior.SequenceEqual(digest)?Results.Ok():Results.Conflict();
        using(var change=db.Sql("UPDATE payments SET state='paid' WHERE id=$p",tx,("$p",ev.PaymentId)))
            if(change.ExecuteNonQuery()==0)return Results.NotFound();
        using(var insert=db.Sql("INSERT INTO provider_events VALUES($id,$digest)",tx,("$id",ev.Id),("$digest",digest)))
            insert.ExecuteNonQuery();
        if(Simulation.At(req,"webhook-before-commit"))return Results.StatusCode(503);
        tx.Commit();
        return Results.Ok();
    }
}
