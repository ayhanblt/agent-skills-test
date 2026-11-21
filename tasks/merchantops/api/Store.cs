using Microsoft.Data.Sqlite;

namespace MerchantOps;

public sealed class Store(string path)
{
    public string DataPath { get; } = Path.GetFullPath(path);

    public SqliteConnection Open()
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = Path.Combine(DataPath, "merchantops.sqlite"),
            ForeignKeys = true, Pooling = false, DefaultTimeout = 5
        }.ToString());
        connection.Open();
        connection.Sql("PRAGMA synchronous=FULL").ExecuteNonQuery();
        return connection;
    }

    public void Initialize()
    {
        Directory.CreateDirectory(DataPath);
        using var db = Open();
        using var command = db.Sql("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS payments(id TEXT PRIMARY KEY, amount INTEGER NOT NULL, currency TEXT NOT NULL,
              state TEXT NOT NULL, refunded INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS refunds(id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES payments(id), amount INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS disputes(id TEXT PRIMARY KEY, payment_id TEXT NOT NULL REFERENCES payments(id),
              status TEXT NOT NULL, note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, dispute_id TEXT NOT NULL REFERENCES disputes(id),
              owner TEXT NOT NULL, name TEXT NOT NULL, body BLOB NOT NULL);
            INSERT OR IGNORE INTO payments(id,amount,currency,state) VALUES ('pay-1',10000,'USD','paid'),('pay-2',5000,'USD','pending');
            INSERT OR IGNORE INTO disputes(id,payment_id,status,note) VALUES ('dis-1','pay-1','open','Fixture dispute');
            """);
        command.ExecuteNonQuery();
    }
}

static class SqliteCommands
{
    public static SqliteCommand Sql(this SqliteConnection db, string sql, SqliteTransaction? transaction = null,
        params (string Name, object? Value)[] parameters)
    {
        var cmd = db.CreateCommand();
        cmd.CommandText = sql;
        cmd.Transaction = transaction;
        foreach (var (name, value) in parameters) cmd.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return cmd;
    }
}
