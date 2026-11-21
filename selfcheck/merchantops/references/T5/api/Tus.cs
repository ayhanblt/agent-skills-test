using Microsoft.Data.Sqlite;
using System.Globalization;

namespace MerchantOps;
public static class Tus
{
    const string Version = "1.0.0";
    record Upload(long Length,long Offset);

    public static void MapTus(this WebApplication app)
    {
        using (var db=app.Services.GetRequiredService<Store>().Open())
        using (var init=db.Sql("CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, owner TEXT NOT NULL, length INTEGER NOT NULL, offset INTEGER NOT NULL)"))
            init.ExecuteNonQuery();
        app.MapMethods("/api/uploads",["OPTIONS"],(HttpResponse res)=>
        {
            res.Headers["Tus-Version"]=Version;res.Headers["Tus-Extension"]="creation";
            res.Headers["Tus-Max-Size"]=Documents.MaxSize.ToString(CultureInfo.InvariantCulture);
            return Results.NoContent();
        });
        app.MapPost("/api/uploads",Create);
        app.MapMethods("/api/uploads/{id}",["HEAD"],(string id,HttpContext ctx,Store store)=>Read(id,ctx,store,false));
        app.MapGet("/api/uploads/{id}/content",(string id,HttpContext ctx,Store store)=>Read(id,ctx,store,true));
        app.MapMethods("/api/uploads/{id}",["PATCH"],Patch);
    }

    static IResult? Check(HttpContext ctx)
    {
        ctx.Response.Headers["Tus-Resumable"]=Version;
        if(ctx.Request.Headers["Tus-Resumable"].ToString()!=Version)
        {
            ctx.Response.Headers["Tus-Version"]=Version;
            return Results.StatusCode(412);
        }
        return Documents.Owner(ctx.Request) is null?Results.Unauthorized():null;
    }

    static bool Int(HttpRequest req,string name,out long value)=>
        long.TryParse(req.Headers[name].ToString(),NumberStyles.None,CultureInfo.InvariantCulture,out value);
    static string FilePath(Store store,string id)=>Path.Combine(store.DataPath,id+".part");

    static async Task<IResult> Create(HttpContext ctx,Store store,CancellationToken ct)
    {
        if(Check(ctx) is {} error)return error;
        if(!Int(ctx.Request,"Upload-Length",out var length))return Results.BadRequest();
        if(length>Documents.MaxSize)return Results.StatusCode(413);
        if(await Documents.ReadLimited(ctx.Request,0,ct) is null)return Results.BadRequest();
        var id=Guid.NewGuid().ToString("N");
        using(var file=File.Create(FilePath(store,id)))file.Flush(true);
        using var db=store.Open();
        using var cmd=db.Sql("INSERT INTO uploads VALUES($id,$owner,$length,0)",null,
            ("$id",id),("$owner",Documents.Owner(ctx.Request)),("$length",length));
        cmd.ExecuteNonQuery();
        ctx.Response.Headers["Upload-Offset"]="0";
        return Results.Created($"/api/uploads/{id}", (object?)null);
    }

    static Upload? Get(SqliteConnection db,SqliteTransaction? tx,string id,string owner)
    {
        using var cmd=db.Sql("SELECT length,offset FROM uploads WHERE id=$id AND owner=$owner",tx,("$id",id),("$owner",owner));
        using var row=cmd.ExecuteReader();
        return row.Read()?new(row.GetInt64(0),row.GetInt64(1)):null;
    }

    static IResult Read(string id,HttpContext ctx,Store store,bool download)
    {
        if(Check(ctx) is {} error)return error;
        using var db=store.Open();
        using var tx=db.BeginTransaction();
        if(Get(db,tx,id,Documents.Owner(ctx.Request)!) is not {} upload)return Results.NotFound();
        ctx.Response.Headers["Cache-Control"]="no-store";
        ctx.Response.Headers["Upload-Length"]=upload.Length.ToString(CultureInfo.InvariantCulture);
        ctx.Response.Headers["Upload-Offset"]=upload.Offset.ToString(CultureInfo.InvariantCulture);
        if(!download)return Results.Ok();
        if(upload.Offset!=upload.Length)return Results.Conflict();
        return Results.File(File.ReadAllBytes(FilePath(store,id)),"application/octet-stream");
    }

    static async Task<IResult> Patch(string id,HttpContext ctx,Store store,CancellationToken ct)
    {
        if(Check(ctx) is {} error)return error;
        if(!string.Equals(ctx.Request.ContentType,"application/offset+octet-stream",StringComparison.OrdinalIgnoreCase))return Results.StatusCode(415);
        if(!Int(ctx.Request,"Upload-Offset",out var supplied))return Results.BadRequest();
        var chunk=await Documents.ReadLimited(ctx.Request,Documents.MaxSize,ct);
        if(chunk is null)return Results.StatusCode(413);
        using var db=store.Open();
        using var tx=db.BeginTransaction();
        if(Get(db,tx,id,Documents.Owner(ctx.Request)!) is not {} upload)return Results.NotFound();
        if(upload.Offset!=supplied)return Results.Conflict();
        if(chunk.Length>upload.Length-upload.Offset)return Results.StatusCode(413);
        using var file=new FileStream(FilePath(store,id),FileMode.Open,FileAccess.Write,FileShare.Read);
        file.Position=upload.Offset;
        file.Write(chunk);
        var offset=upload.Offset+chunk.Length;
        file.SetLength(offset);
        file.Flush(true);
        using var update=db.Sql("UPDATE uploads SET offset=$offset WHERE id=$id",tx,("$offset",offset),("$id",id));
        update.ExecuteNonQuery();
        tx.Commit();
        ctx.Response.Headers["Upload-Offset"]=offset.ToString(CultureInfo.InvariantCulture);
        return Results.NoContent();
    }
}
