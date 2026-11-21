using Microsoft.Data.Sqlite;
using Microsoft.Net.Http.Headers;

namespace MerchantOps;

public static class Disputes
{
    public sealed record VersionedDispute(string Id,string PaymentId,string Status,string Note,long Revision);
    static string Tag(VersionedDispute value)=>$"\"r{value.Revision}\"";

    public static void MapDisputes(this WebApplication app)
    {
        using(var db=app.Services.GetRequiredService<Store>().Open())
        {
            using(var check=db.Sql("SELECT COUNT(*) FROM pragma_table_info('disputes') WHERE name='revision'"))
                if(Convert.ToInt64(check.ExecuteScalar())==0)
                    using(var alter=db.Sql("ALTER TABLE disputes ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"))alter.ExecuteNonQuery();
        }
        app.MapGet("/api/disputes", (Store store) =>
        {
            using var db = store.Open();
            using var cmd = db.Sql("SELECT id,payment_id,status,note,revision FROM disputes ORDER BY id");
            using var rows = cmd.ExecuteReader();
            var list = new List<VersionedDispute>();
            while (rows.Read()) list.Add(Read(rows));
            return list;
        });
        app.MapGet("/api/disputes/{id}", (string id, Store store, HttpResponse response) =>
        {
            using var db = store.Open();
            if(Get(db,id) is not { } item)return Results.NotFound();
            response.Headers.ETag=Tag(item);
            return Results.Ok(item);
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
        app.MapPut("/api/disputes/{id}", (string id, DisputeUpdate input, Store store, HttpContext context) =>
        {
            if (!Valid(input)) return Results.BadRequest();
            using var db = store.Open();
            using var tx = db.BeginTransaction();
            if(Get(db,id,tx) is not { } current)return Results.NotFound();
            if(!context.Request.Headers.TryGetValue("If-Match",out var values))return Results.StatusCode(428);
            if(!EntityTagHeaderValue.TryParseStrictList(values.ToArray(),out var tags)
                || tags.Count==0 || tags.Any(t=>t.Tag.Value=="*"))return Results.BadRequest();
            var tag = new EntityTagHeaderValue(Tag(current));
            if(!tags.Any(t=>t.Compare(tag,true)))return Results.StatusCode(412);
            using var cmd=db.Sql("UPDATE disputes SET status=$s,note=$n,revision=revision+1 WHERE id=$id AND revision=$r",tx,
                ("$s",input.Status),("$n",input.Note),("$id",id),("$r",current.Revision));
            if(cmd.ExecuteNonQuery()!=1)return Results.StatusCode(412);
            var changed=Get(db,id,tx)!;
            tx.Commit();
            context.Response.Headers.ETag=Tag(changed);
            return Results.Ok(changed);
        });
    }

    public static bool Valid(DisputeUpdate input) =>
        (input.Status is "open" or "review" or "closed") && input.Note is { Length: <= 500 };

    public static VersionedDispute? Get(SqliteConnection db,string id,SqliteTransaction? tx=null)
    {
        using var cmd=db.Sql("SELECT id,payment_id,status,note,revision FROM disputes WHERE id=$id",tx,("$id",id));
        using var row=cmd.ExecuteReader();
        return row.Read()?Read(row):null;
    }
    private static VersionedDispute Read(SqliteDataReader row)=>new(row.GetString(0),row.GetString(1),row.GetString(2),row.GetString(3),row.GetInt64(4));
}
