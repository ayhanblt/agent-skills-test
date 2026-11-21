using System.Net;
using System.Net.Http.Json;
using Xunit;

namespace MerchantOpsTests;
public class Regression
{
    [Fact] public async Task PaymentsRefundDisputesAndDocumentsRemainUsable()
    {
        await using var f=new Fixture();await f.Start();
        Assert.Equal(2,(await f.Get("/api/payments")).Value.GetArrayLength());
        var newPayment=await f.Client.PostAsJsonAsync("/api/payments",new {amount=140,currency="USD"});
        Assert.Equal(HttpStatusCode.Created,newPayment.StatusCode);
        var refund=await f.Client.PostAsJsonAsync("/api/payments/pay-1/refunds",new {amount=240});
        Assert.Equal(HttpStatusCode.OK,refund.StatusCode);
        Assert.Equal(240,(await f.Get("/api/payments/pay-1")).Number("refunded"));
        var dispute=await f.Client.PostAsJsonAsync("/api/disputes", new {paymentId="pay-1",note="Review this"});
        Assert.Equal(HttpStatusCode.Created,dispute.StatusCode);
        var url=dispute.Headers.Location!.ToString();
        using var get=await f.Client.GetAsync(url);
        using var update=Fixture.Request("PUT",url,JsonContent.Create(new {status="review",note="Updated"}));
        if(get.Headers.ETag is {} tag)update.Headers.TryAddWithoutValidation("If-Match",tag.ToString());
        Assert.Equal(HttpStatusCode.OK,(await f.Client.SendAsync(update)).StatusCode);
        Assert.Equal("Updated",(await f.Get(url)).Text("note"));
        var bytes=new byte[]{0,1,254,255};
        var document=await f.Client.SendAsync(Fixture.Request("POST",url+"/documents?name=evidence.bin",new ByteArrayContent(bytes),("X-Operator","alice")));
        Assert.Equal(HttpStatusCode.Created,document.StatusCode);
        var loc=document.Headers.Location!.ToString();
        using var own=await f.Client.SendAsync(Fixture.Request("GET",loc,null,("X-Operator","alice")));
        Assert.Equal(bytes,await own.Content.ReadAsByteArrayAsync());
        Assert.Equal(HttpStatusCode.NotFound,(await f.Client.SendAsync(Fixture.Request("GET",loc,null,("X-Operator","bob")))).StatusCode);
        Assert.Equal("pending",(await f.Get("/api/provider/payments/pay-2")).Text("state"));
    }
}
