using System.Net.Http.Json;
using Xunit;
namespace MerchantOpsTests;
public class DisputeTests
{
    static HttpRequestMessage Put(string? tag,string note,string id="dis-1")
    {
        var request=Fixture.Request("PUT","/api/disputes/"+id,JsonContent.Create(new {status="review",note}));
        if(tag!=null)request.Headers.TryAddWithoutValidation("If-Match",tag);
        return request;
    }
    [Fact] public async Task PreconditionsUseStrongComparisonAndRestartStableRevision()
    {
        await using var f=new Fixture();await f.Start();
        var get=await f.Client.GetAsync("/api/disputes/dis-1");
        Assert.NotNull(get.Headers.ETag);
        var tag=get.Headers.ETag.ToString();
        Assert.False(get.Headers.ETag.IsWeak);
        Assert.Equal(428,(int)(await f.Client.SendAsync(Put(null,"no"))).StatusCode);
        Assert.Equal(400,(int)(await f.Client.SendAsync(Put("*","wild"))).StatusCode);
        Assert.Equal(400,(int)(await f.Client.SendAsync(Put("bare","malformed"))).StatusCode);
        Assert.Equal(412,(int)(await f.Client.SendAsync(Put("W/"+tag,"weak"))).StatusCode);
        Assert.Equal(404,(int)(await f.Client.SendAsync(Put(null,"missing","missing"))).StatusCode);
        var saved=await f.Client.SendAsync(Put("\"stale\", "+tag,"saved"));
        Assert.Equal(200,(int)saved.StatusCode);
        Assert.NotNull(saved.Headers.ETag);
        Assert.NotEqual(tag,saved.Headers.ETag.ToString());
        await f.Stop();await f.Start();
        var current=await f.Client.GetAsync("/api/disputes/dis-1");
        Assert.Equal(saved.Headers.ETag,current.Headers.ETag);
        Assert.Equal(412,(int)(await f.Client.SendAsync(Put(tag,"stale"))).StatusCode);
        Assert.Equal("saved",(await f.Get("/api/disputes/dis-1")).Text("note"));
    }
    [Fact] public async Task ConcurrentWritersDoNotOverwriteEachOther()
    {
        await using var f=new Fixture();await f.Start();
        var original=(await f.Client.GetAsync("/api/disputes/dis-1")).Headers.ETag;
        Assert.NotNull(original);
        var replies=await Task.WhenAll(f.Client.SendAsync(Put(original.ToString(),"one")),f.Client.SendAsync(Put(original.ToString(),"two")));
        Assert.Equal(new[]{200,412},replies.Select(x=>(int)x.StatusCode).Order());
        var winner=replies[0].IsSuccessStatusCode?"one":"two";
        Assert.Equal(winner,(await f.Get("/api/disputes/dis-1")).Text("note"));
        Assert.Equal(winner,(await f.Get("/api/disputes")).Value[0].GetProperty("note").GetString());
    }
}
