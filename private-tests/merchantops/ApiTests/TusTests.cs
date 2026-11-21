using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using Xunit;
namespace MerchantOpsTests;

public class TusCore
{
    public static HttpRequestMessage Tus(string method,string path,string owner="alice",string? version="1.0.0",
        HttpContent? body=null,params (string,string)[] headers)
    {
        var request=Fixture.Request(method,path,body,headers);
        request.Headers.Add("X-Operator",owner);
        if(version is not null)request.Headers.Add("Tus-Resumable",version);
        return request;
    }
    internal static async Task<string> Create(Fixture f,int size)
    {
        using var req=Tus("POST","/api/uploads",headers:[("Upload-Length",size.ToString(CultureInfo.InvariantCulture))]);
        using var response=await f.Client.SendAsync(req);
        Assert.Equal(201,(int)response.StatusCode);
        Assert.Equal("0",response.Headers.GetValues("Upload-Offset").Single());
        Assert.Equal("1.0.0",response.Headers.GetValues("Tus-Resumable").Single());
        Assert.NotNull(response.Headers.Location);
        return response.Headers.Location.ToString();
    }
    public static HttpRequestMessage Patch(string path,int offset,string text,string owner="alice",string? checksum=null,string? fault=null)
    {
        var content=new ByteArrayContent(Encoding.UTF8.GetBytes(text));
        content.Headers.ContentType=new("application/offset+octet-stream");
        var r=Tus("PATCH",path,owner,body:content,headers:[("Upload-Offset",offset.ToString(CultureInfo.InvariantCulture))]);
        if(checksum!=null)r.Headers.TryAddWithoutValidation("Upload-Checksum",checksum);
        if(fault!=null)r.Headers.TryAddWithoutValidation("X-Simulate-Fault",fault);
        return r;
    }
    internal static async Task Offset(Fixture f,string path,int expected)
    {
        using var response=await f.Client.SendAsync(Tus("HEAD",path));
        Assert.Equal(200,(int)response.StatusCode);
        Assert.Equal(expected.ToString(CultureInfo.InvariantCulture),response.Headers.GetValues("Upload-Offset").Single());
        Assert.True(response.Headers.CacheControl?.NoStore);
    }
    [Fact] public async Task CoreHeadersOwnerAndFaultFreeResumeAcrossRestart()
    {
        await using var f=new Fixture();await f.Start();
        var options=await f.Client.SendAsync(Tus("OPTIONS","/api/uploads",version:null));
        Assert.Equal(204,(int)options.StatusCode);
        Assert.Equal("1.0.0",options.Headers.GetValues("Tus-Version").Single());
        Assert.Contains("creation",string.Join(",",options.Headers.GetValues("Tus-Extension")).Split(','));
        Assert.Equal("1048576",options.Headers.GetValues("Tus-Max-Size").Single());
        foreach(var version in new string?[]{null,"2.0.0"})
        {
            var unsupported=await f.Client.SendAsync(Tus("POST","/api/uploads",version:version));
            Assert.Equal(412,(int)unsupported.StatusCode);
            Assert.Equal("1.0.0",unsupported.Headers.GetValues("Tus-Version").Single());
        }
        Assert.Equal(400,(int)(await f.Client.SendAsync(Tus("POST","/api/uploads",headers:[("Upload-Length","-1")]))).StatusCode);
        Assert.Equal(413,(int)(await f.Client.SendAsync(Tus("POST","/api/uploads",headers:[("Upload-Length","1048577")]))).StatusCode);
        var path=await Create(f,6);
        Assert.Equal(401,(int)(await f.Client.SendAsync(Tus("HEAD",path,"unknown"))).StatusCode);
        Assert.Equal(404,(int)(await f.Client.SendAsync(Tus("HEAD",path,"bob"))).StatusCode);
        Assert.Equal(404,(int)(await f.Client.SendAsync(Patch(path,0,"abc","bob"))).StatusCode);
        Assert.Equal(415,(int)(await f.Client.SendAsync(Tus("PATCH",path,body:new StringContent("abc"),headers:[("Upload-Offset","0")]))).StatusCode);
        Assert.Equal(409,(int)(await f.Client.SendAsync(Patch(path,1,"abc"))).StatusCode);
        var compete=await Task.WhenAll(f.Client.SendAsync(Patch(path,0,"abc")),f.Client.SendAsync(Patch(path,0,"abc")));
        Assert.Equal(new[]{204,409},compete.Select(r=>(int)r.StatusCode).Order());
        await f.Stop();await f.Start();
        await Offset(f,path,3);
        Assert.Equal(413,(int)(await f.Client.SendAsync(Patch(path,3,"wxyz"))).StatusCode);
        Assert.Equal(204,(int)(await f.Client.SendAsync(Patch(path,3,"def"))).StatusCode);
        var final=await f.Client.SendAsync(Tus("GET",path+"/content"));
        Assert.Equal("abcdef",await final.Content.ReadAsStringAsync());
    }
}
public class TusCrash
{
    static string Checksum(string text)=>"sha256 "+Convert.ToBase64String(SHA256.HashData(Encoding.UTF8.GetBytes(text)));

    [Fact] public async Task HeaderAndChecksumErrorsLeaveTheOffsetUnchanged()
    {
        await using var f=new Fixture();await f.Start();
        var options=await f.Client.SendAsync(TusCore.Tus("OPTIONS","/api/uploads",version:null));
        Assert.Equal("sha256",options.Headers.GetValues("Tus-Checksum-Algorithm").Single());
        Assert.Contains("checksum",string.Join(",",options.Headers.GetValues("Tus-Extension")).Split(','));
        var path=await TusCore.Create(f,6);
        foreach(var bad in new[]{"md5 abcd","sha256 !bad"})
            Assert.Equal(400,(int)(await f.Client.SendAsync(TusCore.Patch(path,0,"abc",checksum:bad))).StatusCode);
        Assert.Equal(460,(int)(await f.Client.SendAsync(TusCore.Patch(path,0,"abc",checksum:Checksum("xyz")))).StatusCode);
        await TusCore.Offset(f,path,0);
        Assert.Equal(204,(int)(await f.Client.SendAsync(TusCore.Patch(path,0,"abc",checksum:Checksum("abc")))).StatusCode);
        await TusCore.Offset(f,path,3);
    }

    [Fact] public async Task AShortCommittedFileIsReportedWithoutSilentlyRepairingIt()
    {
        await using var f=new Fixture();await f.Start();
        var path=await TusCore.Create(f,6);
        Assert.Equal(204,(int)(await f.Client.SendAsync(TusCore.Patch(path,0,"abc",checksum:Checksum("abc")))).StatusCode);
        await f.Stop();
        var id=path.Split('/').Last();
        var file=Path.Combine(f.DataPath,id+".part");
        await File.WriteAllTextAsync(file,"ab");
        await f.Start();
        Assert.Equal(500,(int)(await f.Client.SendAsync(TusCore.Tus("HEAD",path))).StatusCode);
        Assert.Equal(500,(int)(await f.Client.SendAsync(TusCore.Patch(path,3,"def",checksum:Checksum("def")))).StatusCode);
        Assert.Equal("ab",await File.ReadAllTextAsync(file));
    }

    [Theory]
    [InlineData("tus-during-write",3)]
    [InlineData("tus-before-offset",3)]
    [InlineData("tus-after-offset",6)]
    public async Task ProcessCrashDoesNotLoseCommittedBytesOrExposeSpeculativeBytes(string fault,int committed)
    {
        await using var f=new Fixture();await f.Start();
        var path=await TusCore.Create(f,6);
        Assert.Equal(204,(int)(await f.Client.SendAsync(TusCore.Patch(path,0,"abc",checksum:Checksum("abc")))).StatusCode);
        await f.Crash(TusCore.Patch(path,3,"DEF",checksum:Checksum("DEF"),fault:fault));
        await f.Start();
        await TusCore.Offset(f,path,committed);
        var retry=await f.Client.SendAsync(TusCore.Patch(path,3,"def",checksum:Checksum("def")));
        Assert.Equal(committed==6?409:204,(int)retry.StatusCode);
        var final=await f.Client.SendAsync(TusCore.Tus("GET",path+"/content"));
        Assert.Equal(committed==6?"abcDEF":"abcdef",await final.Content.ReadAsStringAsync());
    }
}
