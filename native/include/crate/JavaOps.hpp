// Runtime helpers used by code that `levicrate convert` generates from Java bytecode.
// They reproduce Java semantics where C++ differs (wrap-around, shifts, division, float->int casts).
#pragma once
#include <cmath>
#include <cstdint>
#include <functional>
#include <limits>
#include <type_traits>

namespace levicrate {

// Java would throw here; we report and continue with a defined value.
inline std::function<void(const char*)>& faultHandler() { static std::function<void(const char*)> h; return h; }
inline void jfault(const char* what) { if (faultHandler()) faultHandler()(what); }
inline void junsupported(const char* method) { jfault(method); }  // call to a method that could not be translated

template <class T> inline T jadd(T a, T b) { using U = std::make_unsigned_t<T>; return static_cast<T>(static_cast<U>(a) + static_cast<U>(b)); }
template <class T> inline T jsub(T a, T b) { using U = std::make_unsigned_t<T>; return static_cast<T>(static_cast<U>(a) - static_cast<U>(b)); }
template <class T> inline T jmul(T a, T b) { using U = std::make_unsigned_t<T>; return static_cast<T>(static_cast<U>(a) * static_cast<U>(b)); }
template <class T> inline T jneg(T a) { using U = std::make_unsigned_t<T>; return static_cast<T>(U(0) - static_cast<U>(a)); }

template <class T> inline T jdiv(T a, T b) {
    if (b == 0) { jfault("ArithmeticException: / by zero"); return 0; }
    if (a == std::numeric_limits<T>::min() && b == -1) return a;
    return a / b;
}
template <class T> inline T jrem(T a, T b) {
    if (b == 0) { jfault("ArithmeticException: / by zero"); return 0; }
    if (b == -1) return 0;
    return a % b;
}

template <class T> inline T jshl(T a, int32_t n) { using U = std::make_unsigned_t<T>; return static_cast<T>(static_cast<U>(a) << (n & (sizeof(T) * 8 - 1))); }
template <class T> inline T jshr(T a, int32_t n) { return static_cast<T>(a >> (n & (sizeof(T) * 8 - 1))); }
template <class T> inline T jushr(T a, int32_t n) { using U = std::make_unsigned_t<T>; return static_cast<T>(static_cast<U>(a) >> (n & (sizeof(T) * 8 - 1))); }

template <class T, class F> inline T jf2i(F v) {
    if (v != v) return 0;
    if (v >= static_cast<F>(std::numeric_limits<T>::max())) return std::numeric_limits<T>::max();
    if (v <= static_cast<F>(std::numeric_limits<T>::min())) return std::numeric_limits<T>::min();
    return static_cast<T>(v);
}
inline int32_t jl2i(int64_t v) { return static_cast<int32_t>(static_cast<uint32_t>(static_cast<uint64_t>(v))); }

inline int32_t jcmp(int64_t a, int64_t b) { return a < b ? -1 : (a > b ? 1 : 0); }
template <class F> inline int32_t jfcmpl(F a, F b) { if (a != a || b != b) return -1; return a < b ? -1 : (a > b ? 1 : 0); }
template <class F> inline int32_t jfcmpg(F a, F b) { if (a != a || b != b) return 1; return a < b ? -1 : (a > b ? 1 : 0); }

// java.lang.Math subset
template <class T> inline T jabs(T a) {
    if constexpr (std::is_floating_point_v<T>) return std::fabs(a);
    else return a < 0 ? jneg(a) : a;
}
template <class T> inline T jmax(T a, T b) {
    if constexpr (std::is_floating_point_v<T>) { if (a != a || b != b) return std::numeric_limits<T>::quiet_NaN(); }
    return a > b ? a : b;
}
template <class T> inline T jmin(T a, T b) {
    if constexpr (std::is_floating_point_v<T>) { if (a != a || b != b) return std::numeric_limits<T>::quiet_NaN(); }
    return a < b ? a : b;
}
inline int64_t jround(double x) { return jf2i<int64_t, double>(std::floor(x + 0.5)); }
inline int32_t jroundf(float x) { return jf2i<int32_t, float>(std::floor(x + 0.5f)); }

}  // namespace levicrate
