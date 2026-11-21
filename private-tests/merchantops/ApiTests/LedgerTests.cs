using System.Net.Http.Json;
using System.Text.Json;
using Xunit;
namespace MerchantOpsTests;
public class LedgerTests
{
    static async Task<int> Send(Fixture f,string id,string kind,long amount,string? reference=null,string payment="pay-1",string? fault=null)
    {
        using var request=Fixture.Request("POST","/api/financial-events",
            JsonContent.Create(new {id,paymentId=payment,kind,amount,currency="USD",@ref=reference}));
        if(fault!=null)request.Headers.Add("X-Simulate-Fault",fault);
        using var response=await f.Client.SendAsync(request);
        return (int)response.StatusCode;
    }
    static async Task<JsonElement[]> Rows(Fixture f,string payment="pay-1")=>
        (await f.Get("/api/ledger/"+payment)).Value.EnumerateArray().ToArray();
    static void Pair(JsonElement[] all,string id,string debit,string credit,long amount)
    {
        var rows=all.Where(x=>x.GetProperty("eventId").GetString()==id).ToArray();
        Assert.Equal(2,rows.Length);
        Assert.Equal(debit,rows[0].GetProperty("account").GetString());
        Assert.Equal(credit,rows[1].GetProperty("account").GetString());
        Assert.Equal(amount,rows[0].GetProperty("debit").GetInt64());
        Assert.Equal(0,rows[0].GetProperty("credit").GetInt64());
        Assert.Equal(amount,rows[1].GetProperty("credit").GetInt64());
        Assert.Equal(0,rows[1].GetProperty("debit").GetInt64());
        Assert.All(rows,r=>Assert.Equal("USD",r.GetProperty("currency").GetString()));
    }
    [Fact] public async Task DeferredReversalAndSettlementDrainInCorrectOrder()
    {
        await using var f=new Fixture();await f.Start();
        Assert.Equal(202,await Send(f,"reverse","reverse",7500,"settle"));
        Assert.Equal(202,await Send(f,"refund","refund",2500));
        Assert.Equal(202,await Send(f,"settle","settle",7500));
        Assert.Empty(await Rows(f));
        Assert.Equal(200,await Send(f,"capture","capture",10000));
        var rows=await Rows(f);
        Assert.Equal(new[]{"capture","capture","refund","refund","settle","settle","reverse","reverse"},
             rows.Select(r=>r.GetProperty("eventId").GetString()));
        Pair(rows,"capture","processor","merchant",10000);Pair(rows,"refund","merchant","processor",2500);
        Pair(rows,"settle","cash","processor",7500);Pair(rows,"reverse","processor","cash",7500);
        Assert.Equal(409,await Send(f,"reverse-again","reverse",7500,"settle"));
        Assert.Equal(409,await Send(f,"too-high","refund",7501));
        Assert.Equal(8,(await Rows(f)).Length);
    }
    [Fact] public async Task FailpointRollsBackBothLegsAndRetryIsDurable()
    {
        await using var f=new Fixture();await f.Start();
        Assert.Equal(503,await Send(f,"capture","capture",10000,fault:"ledger-after-debit"));
        Assert.Empty(await Rows(f));
        var concurrent=await Task.WhenAll(Enumerable.Range(0,6).Select(_=>Send(f,"capture","capture",10000)));
        Assert.All(concurrent,status=>Assert.Equal(200,status));
        await f.Stop();await f.Start();
        Assert.Equal(200,await Send(f,"capture","capture",10000));
        Assert.Equal(409,await Send(f,"capture","capture",9999));
        Pair(await Rows(f),"capture","processor","merchant",10000);
    }
    [Fact] public async Task UncertainCaptureWaitsForProviderAndCannotPostTwice()
    {
        await using var f=new Fixture();await f.Start();
        Assert.Equal(202,await Send(f,"uncertain","uncertain",5000,payment:"pay-2"));
        Assert.Empty(await Rows(f,"pay-2"));
        Assert.Equal(200,(int)(await f.Client.SendAsync(f.Webhook("""{"id":"provider-e","type":"payment.paid","paymentId":"pay-2"}"""))).StatusCode);
        Assert.Equal(200,await Send(f,"uncertain","uncertain",5000,payment:"pay-2"));
        Assert.Equal(200,await Send(f,"uncertain","uncertain",5000,payment:"pay-2"));
        Pair(await Rows(f,"pay-2"),"uncertain","processor","merchant",5000);
    }
}
