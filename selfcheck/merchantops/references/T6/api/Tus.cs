using Microsoft.Data.Sqlite;
using System.Security.Cryptography;
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
            res.Headers["Tus-Version"]=Version;res.Headers["Tus-Extension"]="creation,checksum";
            res.Headers["Tus-Checksum-Algorithm"]="sha256";
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

    static FileStream? Recover(Store store,string id,long offset)
    {
        var path=FilePath(store,id);
        if(!File.Exists(path))return null;
        var file=new FileStream(path,FileMode.Open,FileAccess.ReadWrite,FileShare.Read);
        if(file.Length<offset){file.Dispose();return null;}
        if(file.Length>offset){file.SetLength(offset);file.Flush(true);}
        return file;
    }

    // The committed SQLite offset is authoritative. A tail beyond it was never acknowledged.
    static IResult Read(string id,HttpContext ctx,Store store,bool download)
    {
        if(Check(ctx) is {} error)return error;
        using var db=store.Open();
        using var tx=db.BeginTransaction();
        if(Get(db,tx,id,Documents.Owner(ctx.Request)!) is not {} upload)return Results.NotFound();
        using var file=Recover(store,id,upload.Offset);
        if(file is null)return Results.StatusCode(500);
        ctx.Response.Headers["Cache-Control"]="no-store";
        ctx.Response.Headers["Upload-Length"]=upload.Length.ToString(CultureInfo.InvariantCulture);
        ctx.Response.Headers["Upload-Offset"]=upload.Offset.ToString(CultureInfo.InvariantCulture);
        if(!download)return Results.Ok();
        if(upload.Offset!=upload.Length)return Results.Conflict();
        var data=new byte[checked((int)upload.Offset)];
        file.ReadExactly(data);
        return Results.File(data,"application/octet-stream");
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
        using var file=Recover(store,id,upload.Offset);
        if(file is null)return Results.StatusCode(500);
        if(ctx.Request.Headers.TryGetValue("Upload-Checksum",out var header))
        {
            var parts=header.ToString().Split(' ');
            var digest = new byte[32];
            if(parts.Length!=2||parts[0]!="sha256"||parts[1].Length!=44||
               !Convert.TryFromBase64String(parts[1],digest,out int written)||written!=digest.Length)return Results.BadRequest();
            if(!CryptographicOperations.FixedTimeEquals(digest,SHA256.HashData(chunk)))return Results.StatusCode(460);
        }
        file.Position=upload.Offset;
        if (Simulation.At(ctx.Request,"tus-during-write"))
        {
            file.Write(chunk.AsSpan(0,chunk.Length/2));
            file.Flush(true);
            Environment.FailFast("local tus simulation: partial write");
        }
        file.Write(chunk);
        var offset=upload.Offset+chunk.Length;
        file.SetLength(offset);
        file.Flush(true);
        using var update=db.Sql("UPDATE uploads SET offset=$offset WHERE id=$id",tx,("$offset",offset),("$id",id));
        update.ExecuteNonQuery();
        if(Simulation.At(ctx.Request,"tus-before-offset"))Environment.FailFast("local tus simulation: metadata uncommitted");
        tx.Commit();
        if(Simulation.At(ctx.Request,"tus-after-offset"))Environment.FailFast("local tus simulation: offset committed");
        ctx.Response.Headers["Upload-Offset"]=offset.ToString(CultureInfo.InvariantCulture);
        return Results.NoContent();
    }
}
