# MerchantOps research starter

Start the API with `dotnet run --project api --urls http://127.0.0.1:5080`. In another terminal, run `npm ci` and `npm run dev` from `web/`. Use the address displayed by Vite. Test data is created on first launch. Set `MO_DATA` to a separate path to use a fresh SQLite database.

Amounts use integer minor units. Document ownership is simulated with the fixed local operators alice and bob. Do not use this fixture with real identities or payments.
