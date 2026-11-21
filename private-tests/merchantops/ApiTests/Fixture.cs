using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using Xunit;

namespace MerchantOpsTests;

sealed class Fixture : IAsyncDisposable
{
    public const string Secret = "merchantops-local-test-fixture";
    readonly string data=Path.Combine(Path.GetTempPath(),"merchantops-test-"+Guid.NewGuid().ToString("N"));
    Process? api;
    public HttpClient Client {get;private set;}=null!;
    public string DataPath=>data;
    public async Task Start()
    {
        var dll=Environment.GetEnvironmentVariable("MO_API_DLL")??throw new InvalidOperationException("Set MO_API_DLL to the independent build.");
        Directory.CreateDirectory(data);
        var start=new ProcessStartInfo("dotnet"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
        foreach(var arg in new[]{dll,"--urls","http://127.0.0.1:0"})start.ArgumentList.Add(arg);
        start.Environment["MO_DATA"]=data;start.Environment["MO_PROVIDER_SECRET"]=Secret;
        start.Environment["MO_ENABLE_FAULTS"]="1";
        start.Environment["DOTNET_DbgEnableMiniDump"]="0";
        api=Process.Start(start)!;
        var address=new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
        api.OutputDataReceived+=(_,ev)=>{
            const string marker="Now listening on: ";
            if(ev.Data?.Contains(marker)==true)address.TrySetResult(ev.Data[(ev.Data.IndexOf(marker)+marker.Length)..].Trim());
        };
        api.ErrorDataReceived+=(_,ev)=>{if(ev.Data!=null)Console.Error.WriteLine(ev.Data);};
        api.EnableRaisingEvents=true;
        api.Exited+=(_,_)=>address.TrySetException(new InvalidOperationException("API exited during startup."));
        api.BeginOutputReadLine();api.BeginErrorReadLine();
        Client=new HttpClient{BaseAddress=new Uri(await address.Task.WaitAsync(TimeSpan.FromSeconds(8))),Timeout=TimeSpan.FromSeconds(10)};
    }

    public async Task Stop()
    {
        Client?.Dispose();
        if(api is not null){if(!api.HasExited)api.Kill(entireProcessTree:true);await api.WaitForExitAsync();api.Dispose();api=null;}
    }

    public async Task Crash(HttpRequestMessage req)
    {
        Assert.NotNull(api);
        await Assert.ThrowsAnyAsync<HttpRequestException>(async()=>{using var response=await Client.SendAsync(req);});
        await api.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
        Assert.NotEqual(0,api.ExitCode);
        await Stop();
    }

    // Independent inspection of the starter's existing SQLite tables.
    public async Task<string> Sql(string statement)
    {
        var start=new ProcessStartInfo("/usr/bin/sqlite3"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
        start.ArgumentList.Add(Path.Combine(data,"merchantops.sqlite"));start.ArgumentList.Add(statement);
        using var tool=Process.Start(start)!;
        var stdout=tool.StandardOutput.ReadToEndAsync();
        var stderr=tool.StandardError.ReadToEndAsync();
        await tool.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
        Assert.True(tool.ExitCode==0,await stderr);
        return (await stdout).Trim();
    }

    public static HttpRequestMessage Request(string method,string path,HttpContent? body=null,
        params (string,string)[] headers)
    {
        var r=new HttpRequestMessage(new HttpMethod(method),path){Content=body};
        foreach(var (key,value) in headers)r.Headers.TryAddWithoutValidation(key,value);
        return r;
    }

    public HttpRequestMessage Webhook(string json,long? time=null,string? signedBody=null,string? fault=null)
    {
        string t=(time??DateTimeOffset.UtcNow.ToUnixTimeSeconds()).ToString();
        var signature=Convert.ToHexStringLower(HMACSHA256.HashData(Encoding.UTF8.GetBytes(Secret),Encoding.UTF8.GetBytes(t+"."+(signedBody??json))));
        var r=Request("POST","/api/provider/webhook",new StringContent(json,Encoding.UTF8,"application/json"),
            ("X-Provider-Time",t),("X-Provider-Signature",signature));
        if(fault!=null)r.Headers.Add("X-Simulate-Fault",fault);
        return r;
    }

    public async Task<JsonElementValue> Get(string path)
    {
        using var response=await Client.GetAsync(path);
        Assert.Equal(HttpStatusCode.OK,response.StatusCode);
        return new(await response.Content.ReadFromJsonAsync<System.Text.Json.JsonElement>());
    }

    public async ValueTask DisposeAsync(){await Stop();if(Directory.Exists(data))Directory.Delete(data,true);}
}

readonly record struct JsonElementValue(System.Text.Json.JsonElement Value)
{
    public string? Text(string name)=>Value.GetProperty(name).GetString();
    public long Number(string name)=>Value.GetProperty(name).GetInt64();
}
