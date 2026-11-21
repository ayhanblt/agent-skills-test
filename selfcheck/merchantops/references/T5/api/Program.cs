using MerchantOps;

SQLitePCL.raw.SetProvider(new SQLitePCL.SQLite3Provider_sqlite3());
var builder = WebApplication.CreateBuilder(args);
builder.WebHost.ConfigureKestrel(k => k.Limits.MaxRequestBodySize = 1_100_000);
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton(new Store(builder.Configuration["MO_DATA"] ?? "data"));
var app = builder.Build();
app.Services.GetRequiredService<Store>().Initialize();
app.MapGet("/health", () => Results.Ok(new { status = "ready" }));
app.MapPayments();
app.MapDisputes();
app.MapDocuments();
app.MapProvider();
app.MapLedger();
app.MapTus();
app.Run();

public partial class Program;
