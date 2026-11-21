using Xunit;
namespace MerchantOpsTests;
public class WebhookTests
{
    const string Body="""{"id":"event-1","type":"payment.paid","paymentId":"pay-2"}""";
    [Fact] public async Task RawBodyFreshnessAndValidation()
    {
        await using var f=new Fixture();await f.Start();
        Assert.Equal(401,(int)(await f.Client.SendAsync(f.Webhook(Body,signedBody:Body+" "))).StatusCode);
        Assert.Equal(401,(int)(await f.Client.SendAsync(f.Webhook(Body,DateTimeOffset.UtcNow.ToUnixTimeSeconds()-301))).StatusCode);
        Assert.Equal(401,(int)(await f.Client.SendAsync(Fixture.Request("POST","/api/provider/webhook",new StringContent(Body)))).StatusCode);
        Assert.Equal(400,(int)(await f.Client.SendAsync(f.Webhook("{"))).StatusCode);
        Assert.Equal("pending",(await f.Get("/api/payments/pay-2")).Text("state"));
        Assert.Equal(200,(int)(await f.Client.SendAsync(f.Webhook(Body+" "))).StatusCode);
        Assert.Equal("paid",(await f.Get("/api/payments/pay-2")).Text("state"));
    }
    [Fact] public async Task RollbackConcurrentRetryAndPersistentDeduplication()
    {
        await using var f=new Fixture();await f.Start();
        await f.Sql("""
          CREATE TABLE audit_writes(n INTEGER NOT NULL);
          CREATE TRIGGER count_webhook_updates AFTER UPDATE ON payments WHEN NEW.id='pay-2'
          BEGIN INSERT INTO audit_writes VALUES(1); END;
          """);
        Assert.Equal(503,(int)(await f.Client.SendAsync(f.Webhook(Body,fault:"webhook-before-commit"))).StatusCode);
        Assert.Equal("pending",(await f.Get("/api/payments/pay-2")).Text("state"));
        var results=await Task.WhenAll(Enumerable.Range(0,6).Select(_=>f.Client.SendAsync(f.Webhook(Body))));
        Assert.All(results,r=>Assert.Equal(200,(int)r.StatusCode));
        Assert.Equal("1",await f.Sql("SELECT COUNT(*) FROM audit_writes"));
        await f.Stop();await f.Start();
        Assert.Equal("paid",(await f.Get("/api/payments/pay-2")).Text("state"));
        Assert.Equal(200,(int)(await f.Client.SendAsync(f.Webhook(Body))).StatusCode);
        Assert.Equal(409,(int)(await f.Client.SendAsync(f.Webhook(Body+" "))).StatusCode);
        Assert.Equal("1",await f.Sql("SELECT COUNT(*) FROM audit_writes"));
    }
}
