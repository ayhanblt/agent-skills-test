export function createPayments(provider) {
 return {async pay(key,request) {return provider.charge(key,request);}};
}
