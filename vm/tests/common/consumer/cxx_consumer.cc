/* C++11 installed SDK consumer exercising RAII, memory limits, interrupts,
 * callbacks, modules, Promises and OOM recovery without private headers. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

struct InterruptState {
    int calls;
    int limit;
};

int on_interrupt(JSContext *ctx, void *opaque)
{
    (void)ctx;
    InterruptState *state = static_cast<InterruptState *>(opaque);
    state->calls++;
    return state->limit > 0 && state->calls >= state->limit;
}

JSValue relay_callback(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    (void)this_val;
    assert(argc == 2);
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}

class ScopedRuntime {
  public:
    ScopedRuntime() : rt_(JS_NewRuntime())
    {
        assert(rt_ != nullptr);
    }
    ~ScopedRuntime()
    {
        if (rt_ != nullptr)
            JS_FreeRuntime(rt_);
    }
    ScopedRuntime(const ScopedRuntime &) = delete;
    ScopedRuntime &operator=(const ScopedRuntime &) = delete;

    JSRuntime *get() const
    {
        return rt_;
    }

  private:
    JSRuntime *rt_;
};

class ScopedContext {
  public:
    explicit ScopedContext(JSRuntime *rt) : ctx_(JS_NewContext(rt))
    {
        assert(ctx_ != nullptr);
    }
    ~ScopedContext()
    {
        if (ctx_ != nullptr)
            JS_FreeContext(ctx_);
    }
    ScopedContext(const ScopedContext &) = delete;
    ScopedContext &operator=(const ScopedContext &) = delete;

    JSContext *get() const
    {
        return ctx_;
    }

  private:
    JSContext *ctx_;
};

} /* namespace */

int main()
{
    ScopedRuntime rt;
    const size_t memory_limit = 8u * 1024u * 1024u;
    JS_SetMemoryLimit(rt.get(), memory_limit);

    InterruptState interrupt_state = {0, 0};
    JS_SetInterruptHandler(rt.get(), on_interrupt, &interrupt_state);

    ScopedContext ctx(rt.get());
    JSValue global = JS_GetGlobalObject(ctx.get());
    assert(!JS_IsException(global));
    assert(JS_SetPropertyStr(ctx.get(), global, "relay",
                             JS_NewCFunction(ctx.get(), relay_callback, "relay", 2)) >= 0);

    const char *fn_src = "(function(a){let b=relay(x=>x+1,a);try{throw b+2}catch(e){return e}})";
    JSValue fn =
        JS_Eval(ctx.get(), fn_src, std::strlen(fn_src), "cxx_consumer.js", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(fn));
    for (int i = 0; i < 300; i++) {
        JSValue arg = JS_NewInt32(ctx.get(), i);
        JSValue res = JS_Call(ctx.get(), fn, JS_UNDEFINED, 1, &arg);
        int32_t out = 0;
        assert(!JS_IsException(res));
        assert(JS_ToInt32(ctx.get(), &out, res) == 0 && out == i + 3);
        JS_FreeValue(ctx.get(), res);
        JS_FreeValue(ctx.get(), arg);
    }
    JS_FreeValue(ctx.get(), fn);

    const char *mod_src = "globalThis.cxxTotal = 0;"
                          "Promise.resolve(40).then(v => { globalThis.cxxTotal = v + 2; });";
    JSValue mod_promise =
        JS_Eval(ctx.get(), mod_src, std::strlen(mod_src), "cxx_mod.mjs", JS_EVAL_TYPE_MODULE);
    assert(!JS_IsException(mod_promise));
    assert(JS_IsPromise(mod_promise));
    assert(JS_PromiseState(ctx.get(), mod_promise) == JS_PROMISE_FULFILLED);
    JS_FreeValue(ctx.get(), mod_promise);

    JSContext *job_ctx = nullptr;
    int job_status = 0;
    while ((job_status = JS_ExecutePendingJob(rt.get(), &job_ctx)) > 0) {
        assert(job_ctx == ctx.get());
    }
    assert(job_status == 0);

    JSValue total_val = JS_GetPropertyStr(ctx.get(), global, "cxxTotal");
    int32_t total = 0;
    assert(JS_ToInt32(ctx.get(), &total, total_val) == 0 && total == 42);
    JS_FreeValue(ctx.get(), total_val);

    const char *oom_src = "new ArrayBuffer(16 * 1024 * 1024);";
    JSValue oom_res = JS_Eval(ctx.get(), oom_src, std::strlen(oom_src), "oom.js", 0);
    assert(JS_IsException(oom_res));
    JS_FreeValue(ctx.get(), oom_res);
    JSValue exc = JS_GetException(ctx.get());
    assert(!JS_IsUndefined(exc));
    JS_FreeValue(ctx.get(), exc);

    interrupt_state.calls = 0;
    interrupt_state.limit = 1;
    const char *loop_src = "for (;;) {}";
    JSValue loop_res = JS_Eval(ctx.get(), loop_src, std::strlen(loop_src), "loop.js", 0);
    assert(JS_IsException(loop_res));
    JS_FreeValue(ctx.get(), loop_res);
    JSValue loop_exc = JS_GetException(ctx.get());
    assert(!JS_IsUndefined(loop_exc));
    JS_FreeValue(ctx.get(), loop_exc);
    assert(interrupt_state.calls >= 1);

    JS_FreeValue(ctx.get(), global);
    JS_RunGC(rt.get());

    JSMemoryUsage usage;
    JS_ComputeMemoryUsage(rt.get(), &usage);
    assert(usage.malloc_limit == static_cast<int64_t>(memory_limit));
    assert(usage.malloc_size > 0 && usage.malloc_size <= static_cast<int64_t>(memory_limit));

    std::puts("INSTALLED_CXX11_CONSUMER_PASS");
    return 0;
}
