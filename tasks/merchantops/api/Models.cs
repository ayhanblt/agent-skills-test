namespace MerchantOps;

public sealed record Payment(string Id, long Amount, string Currency, string State, long Refunded);
public sealed record RefundInput(long Amount);
public sealed record PaymentInput(long Amount, string Currency);
public sealed record Dispute(string Id, string PaymentId, string Status, string Note);
public sealed record DisputeInput(string PaymentId, string Note);
public sealed record DisputeUpdate(string Status, string Note);
public sealed record Document(string Id, string DisputeId, string Name, int Size);
public sealed record ProviderEvent(string Id, string Type, string PaymentId);
public sealed record FinancialEvent(string Id, string PaymentId, string Kind, long Amount, string Currency, string? Ref);
