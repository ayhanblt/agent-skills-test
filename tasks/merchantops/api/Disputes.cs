using Microsoft.Data.Sqlite;

namespace MerchantOps;

public static class Disputes
{
    public static void MapDisputes(this WebApplication app)
    {
        app.MapGet("/api/disputes", (Store store) =>
        {
            using var db = store.Open();
            using var cmd = db.Sql("SELECT id,payment_id,status,note FROM disputes ORDER BY id");
            using var rows = cmd.ExecuteReader();
            var list = new List<Dispute>();
            while (rows.Read()) list.Add(Read(rows));
            return list;
        });
        app.MapGet("/api/disputes/{id}", (string id, Store store) =>
        {
            using var db = store.Open();
            return Get(db,id) is { } item ? Results.Ok(item) : Results.NotFound();
        });
        app.MapPost("/api/disputes", (DisputeInput input, Store store) =>
        {
            if (string.IsNullOrWhiteSpace(input.Note) || input.Note.Length > 500) return Results.BadRequest();
            using var db = store.Open();
            if (Payments.Get(db,input.PaymentId) is null) return Results.NotFound();
            string id = Guid.NewGuid().ToString("N");
            using var cmd = db.Sql("INSERT INTO disputes(id,payment_id,status,note) VALUES($id,$p,'open',$n)",
                null,("$id",id),("$p",input.PaymentId),("$n",input.Note));
            cmd.ExecuteNonQuery();
            return Results.Created($"/api/disputes/{id}",Get(db,id));
        });
        app.MapPut("/api/disputes/{id}", (string id, DisputeUpdate input, Store store) =>
        {
            if (!Valid(input)) return Results.BadRequest();
            using var db = store.Open();
            using var cmd = db.Sql("UPDATE disputes SET status=$s,note=$n WHERE id=$id",null,
                ("$s",input.Status),("$n",input.Note),("$id",id));
            return cmd.ExecuteNonQuery()==0 ? Results.NotFound() : Results.Ok(Get(db,id));
        });
    }

    public static bool Valid(DisputeUpdate input) =>
        (input.Status is "open" or "review" or "closed") && input.Note is { Length: <= 500 };

    public static Dispute? Get(SqliteConnection db,string id,SqliteTransaction? tx=null)
    {
        using var cmd=db.Sql("SELECT id,payment_id,status,note FROM disputes WHERE id=$id",tx,("$id",id));
        using var row=cmd.ExecuteReader();
        return row.Read()?Read(row):null;
    }
    private static Dispute Read(SqliteDataReader row)=>new(row.GetString(0),row.GetString(1),row.GetString(2),row.GetString(3));
}
