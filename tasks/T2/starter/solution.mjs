export function createPayments(provider,store) {
 return {async pay(key,request){return provider.charge(key,request);},webhook(event){store.set(event.key,event);return event;},status(key){return store.get(key)??null;}};
}
