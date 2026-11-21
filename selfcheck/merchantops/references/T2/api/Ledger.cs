using Microsoft.Data.Sqlite;
namespace MerchantOps;

public static class Ledger
{
    record Entry(FinancialEvent Event, string Status);
    record Line(string EventId, string Account, long Debit, long Credit, string Currency);
    sealed class Fault : Exception;

    public static void MapLedger(this WebApplication app)
    {
        using (var db = app.Services.GetRequiredService<Store>().Open())
        using (var init = db.Sql("""
            CREATE TABLE IF NOT EXISTS financial_events(seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, payment TEXT NOT NULL,
              kind TEXT NOT NULL, amount INTEGER NOT NULL, currency TEXT NOT NULL, ref TEXT, status TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS journal(seq INTEGER PRIMARY KEY, payment TEXT NOT NULL, event TEXT NOT NULL,
              account TEXT NOT NULL, debit INTEGER NOT NULL, credit INTEGER NOT NULL, currency TEXT NOT NULL);
            CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON journal BEGIN SELECT RAISE(ABORT,'immutable journal'); END;
            CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON journal BEGIN SELECT RAISE(ABORT,'immutable journal'); END;
            """)) init.ExecuteNonQuery();
        app.MapGet("/api/ledger/{paymentId}",(string paymentId,Store store) =>
        {
            using var db=store.Open();
            if(Payments.Get(db,paymentId) is null)return Results.NotFound();
            using var select=db.Sql("SELECT event,account,debit,credit,currency FROM journal WHERE payment=$p ORDER BY seq",null,("$p",paymentId));
            using var rows=select.ExecuteReader();var lines=new List<Line>();
            while(rows.Read())lines.Add(new(rows.GetString(0),rows.GetString(1),rows.GetInt64(2),rows.GetInt64(3),rows.GetString(4)));
            return Results.Ok(lines);
        });
        app.MapPost("/api/financial-events",Receive);
    }

    static List<Entry> Read(SqliteConnection db,SqliteTransaction tx)
    {
        using var read=db.Sql("SELECT id,payment,kind,amount,currency,ref,status FROM financial_events ORDER BY seq",tx);
        using var rows=read.ExecuteReader();var items=new List<Entry>();
        while(rows.Read())items.Add(new(new(rows.GetString(0),rows.GetString(1),rows.GetString(2),rows.GetInt64(3),
            rows.GetString(4),rows.IsDBNull(5)?null:rows.GetString(5)),rows.GetString(6)));
        return items;
    }

    static IResult Receive(FinancialEvent ev, HttpRequest request, Store store)
    {
        if(string.IsNullOrWhiteSpace(ev.Id)||string.IsNullOrWhiteSpace(ev.PaymentId)||ev.Amount is <1 or >100_000_000
            || ev.Currency!="USD" || ev.Kind is not ("capture" or "uncertain" or "refund" or "settle" or "reverse")
            || (ev.Kind=="reverse" ? string.IsNullOrWhiteSpace(ev.Ref) : ev.Ref is not null))return Results.BadRequest();
        using var db=store.Open();
        using var tx=db.BeginTransaction();
        if(Payments.Get(db,ev.PaymentId,tx) is not { } payment)return Results.NotFound();
        var entries=Read(db,tx);
        var prior=entries.FirstOrDefault(x=>x.Event.Id==ev.Id);
        if(prior is not null && prior.Event!=ev)return Results.Conflict();
        if(prior is not null && (prior.Status!="waiting" || ev.Kind!="uncertain"))return Result(prior.Status);
        var state=Classify(ev,payment,entries);
        if(state=="rejected" && prior is null)return Results.Conflict();
        try
        {
            if(prior is null)
            {
                using var insert=db.Sql("INSERT INTO financial_events(id,payment,kind,amount,currency,ref,status) VALUES($id,$p,$k,$a,$c,$r,'waiting')",
                    tx,("$id",ev.Id),("$p",ev.PaymentId),("$k",ev.Kind),("$a",ev.Amount),("$c",ev.Currency),("$r",ev.Ref));
                insert.ExecuteNonQuery();
            }
            Write(db,tx,ev,state,request);
            if(state=="applied")
            {
                bool changed;
                do
                {
                    changed=false;
                    foreach(var waiting in Read(db,tx).Where(x=>x.Status=="waiting"&&x.Event.PaymentId==ev.PaymentId&&x.Event.Kind!="uncertain"))
                    {
                        var next=Classify(waiting.Event,payment,Read(db,tx));
                        if(next=="waiting")continue;
                        Write(db,tx,waiting.Event,next,request);changed=true;
                    }
                }while(changed);
            }
            tx.Commit();
            return Result(state);
        }
        catch(Fault){return Results.StatusCode(503);}
    }

    static string Classify(FinancialEvent ev,Payment payment,List<Entry> entries)
    {
        const string applied="applied", waiting="waiting", rejected="rejected";
        var own=entries.Where(x=>x.Status==applied&&x.Event.PaymentId==ev.PaymentId).Select(x=>x.Event).ToArray();
        var captured=own.FirstOrDefault(x=>x.Kind is "capture" or "uncertain");
        if(ev.Kind is "capture" or "uncertain")
            return captured is not null||ev.Amount!=payment.Amount ? rejected : ev.Kind=="uncertain" && payment.State!="paid" ? waiting : applied;
        if(ev.Kind=="reverse")
        {
            var settled=entries.FirstOrDefault(x=>x.Event.Id==ev.Ref);
            if(settled is null)return waiting;
            if(settled.Event.Kind!="settle"||settled.Event.PaymentId!=ev.PaymentId||settled.Event.Amount!=ev.Amount||settled.Status==rejected)return rejected;
            if(settled.Status!=applied)return waiting;
            return own.Any(x=>x.Kind=="reverse"&&x.Ref==ev.Ref)?rejected:applied;
        }
        if(captured is null)return waiting;
        var remaining=captured.Amount-own.Where(x=>x.Kind=="refund").Sum(x=>x.Amount);
        if(own.Any(x=>x.Kind=="settle"&&!own.Any(y=>y.Kind=="reverse"&&y.Ref==x.Id)))return rejected;
        return (ev.Kind=="refund"?ev.Amount<=remaining:ev.Amount==remaining)?applied:rejected;
    }

    static void Write(SqliteConnection db,SqliteTransaction tx,FinancialEvent ev,string status,HttpRequest request)
    {
        using(var update=db.Sql("UPDATE financial_events SET status=$s WHERE id=$id",tx,("$id",ev.Id),("$s",status)))update.ExecuteNonQuery();
        if(status!="applied")return;
        var (debit,credit)=ev.Kind switch
        {
            "refund"=>("merchant","processor"),"settle"=>("cash","processor"),"reverse"=>("processor","cash"),_=>("processor","merchant")
        };
        Add(debit,ev.Amount,0);
        if(Simulation.At(request,"ledger-after-debit"))throw new Fault();
        Add(credit,0,ev.Amount);
        void Add(string account,long debit,long credit)
        {
            using var insert=db.Sql("INSERT INTO journal(payment,event,account,debit,credit,currency) VALUES($p,$id,$a,$d,$c,$currency)",
                tx,("$p",ev.PaymentId),("$id",ev.Id),("$a",account),("$d",debit),("$c",credit),("$currency",ev.Currency));
            insert.ExecuteNonQuery();
        }
    }

    static IResult Result(string state)=>state switch
    {"applied"=>Results.Ok(new {status=state}),"waiting"=>Results.Accepted(value:new {status=state}),_=>Results.Conflict(new {status=state})};
}
