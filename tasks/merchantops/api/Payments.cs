using Microsoft.Data.Sqlite;

namespace MerchantOps;
public static class Payments
{
    public static void MapPayments(this WebApplication app)
    {
        app.MapGet("/api/payments", (Store store) =>
        {
            using var db = store.Open();
            using var cmd = db.Sql("SELECT id,amount,currency,state,refunded FROM payments ORDER BY id");
            using var rows = cmd.ExecuteReader();
            var list = new List<Payment>();
            while (rows.Read()) list.Add(Read(rows));
            return list;
        });
        app.MapGet("/api/payments/{id}", (string id, Store store) =>
        {
            using var db = store.Open();
            return Get(db, id) is { } p ? Results.Ok(p) : Results.NotFound();
        });
        app.MapPost("/api/payments", (PaymentInput input, Store store) =>
        {
            if (input.Amount is <= 0 or > 100_000_000 || input.Currency != "USD") return Results.BadRequest();
            var id = Guid.NewGuid().ToString("N");
            using var db = store.Open();
            using var cmd = db.Sql("INSERT INTO payments(id,amount,currency,state) VALUES($id,$amount,'USD','pending')",
                null, ("$id", id), ("$amount", input.Amount));
            cmd.ExecuteNonQuery();
            return Results.Created($"/api/payments/{id}", Get(db,id));
        });
        app.MapPost("/api/payments/{id}/refunds", (string id, RefundInput input, Store store) =>
        {
            if (input.Amount <= 0) return Results.BadRequest();
            using var db = store.Open();
            using var tx = db.BeginTransaction();
            var payment = Get(db,id,tx);
            if (payment is null) return Results.NotFound();
            if (payment.State != "paid" || input.Amount > payment.Amount - payment.Refunded) return Results.Conflict();
            using (var update = db.Sql("UPDATE payments SET refunded=refunded+$n WHERE id=$id",tx,("$id",id),("$n",input.Amount)))
                update.ExecuteNonQuery();
            using (var create = db.Sql("INSERT INTO refunds VALUES($r,$id,$n)",tx,("$r",Guid.NewGuid().ToString("N")),("$id",id),("$n",input.Amount)))
                create.ExecuteNonQuery();
            var changed = Get(db,id,tx);
            tx.Commit();
            return Results.Ok(changed);
        });
    }

    public static Payment? Get(SqliteConnection db, string id, SqliteTransaction? tx = null)
    {
        using var cmd = db.Sql("SELECT id,amount,currency,state,refunded FROM payments WHERE id=$id",tx,("$id",id));
        using var row = cmd.ExecuteReader();
        return row.Read() ? Read(row) : null;
    }

    private static Payment Read(SqliteDataReader row) => new(row.GetString(0),row.GetInt64(1),row.GetString(2),row.GetString(3),row.GetInt64(4));
}
