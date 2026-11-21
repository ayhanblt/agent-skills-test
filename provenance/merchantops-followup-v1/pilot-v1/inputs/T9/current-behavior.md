# Mevcut davranış

Sipariş geçmişinde self-servis iptal yok. Desteğin bugün kullandığı iptal kanalı mevcut. Ödemeler asenkron iade servisini kullanıyor. Depo, taşıyıcıya teslim durumunu asenkron işler. Servis çağrısı zaman aşımına uğradığında çağrının sonucu bilinmeyebilir.
