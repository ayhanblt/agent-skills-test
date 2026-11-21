namespace MerchantOps;
public static class Documents
{
    public const int MaxSize = 1_048_576;
    public static string? Owner(HttpRequest request) => request.Headers["X-Operator"].ToString() switch
    { "alice" => "alice", "bob" => "bob", _ => null };

    public static void MapDocuments(this WebApplication app)
    {
        app.MapGet("/api/disputes/{disputeId}/documents", (string disputeId,HttpRequest req,Store store) =>
        {
            if (Owner(req) is not { } owner) return Results.Unauthorized();
            using var db=store.Open();
            using var cmd=db.Sql("SELECT id,name,length(body) FROM documents WHERE dispute_id=$d AND owner=$o ORDER BY id",
                null,("$d",disputeId),("$o",owner));
            using var rows=cmd.ExecuteReader();
            var list=new List<Document>();
            while(rows.Read())list.Add(new(rows.GetString(0),disputeId,rows.GetString(1),rows.GetInt32(2)));
            return Results.Ok(list);
        });
        app.MapPost("/api/disputes/{disputeId}/documents", async (string disputeId,HttpRequest req,Store store,CancellationToken ct) =>
        {
            if (Owner(req) is not { } owner) return Results.Unauthorized();
            var name=req.Query["name"].ToString();
            if (name.Length is 0 or >100) return Results.BadRequest();
            var body=await ReadLimited(req,MaxSize,ct);
            if(body is null)return Results.StatusCode(413);
            using var db=store.Open();
            if(Disputes.Get(db,disputeId) is null)return Results.NotFound();
            var id=Guid.NewGuid().ToString("N");
            using var cmd=db.Sql("INSERT INTO documents VALUES($id,$d,$o,$n,$b)",null,
                ("$id",id),("$d",disputeId),("$o",owner),("$n",name),("$b",body));
            cmd.ExecuteNonQuery();
            return Results.Created($"/api/documents/{id}",new Document(id,disputeId,name,body.Length));
        });
        app.MapGet("/api/documents/{id}",(string id,HttpRequest req,Store store) =>
        {
            if(Owner(req) is not { } owner)return Results.Unauthorized();
            using var db=store.Open();
            using var cmd=db.Sql("SELECT name,body FROM documents WHERE id=$id AND owner=$o",null,("$id",id),("$o",owner));
            using var row=cmd.ExecuteReader();
            return row.Read()?Results.File((byte[])row[1],"application/octet-stream",row.GetString(0)):Results.NotFound();
        });
    }

    public static async Task<byte[]?> ReadLimited(HttpRequest req,int limit,CancellationToken ct)
    {
        if (req.ContentLength>limit) return null;
        using var output = new MemoryStream();
        var chunk = new byte[8192];
        for(int n;(n=await req.Body.ReadAsync(chunk,ct))!=0;)
        {
            if(output.Length+n>limit)return null;
            output.Write(chunk,0,n);
        }
        return output.ToArray();
    }
}
