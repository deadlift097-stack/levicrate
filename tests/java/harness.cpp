#include <cstdio>
#include <cstring>
#include <cmath>
#include <string>
#include "Translated.hpp"
#include "crate/JavaOps.hpp"
using namespace port;
static std::string o;
static void I(long long v){ o += std::to_string(v); }
static void S(const char* s){ o += s; }
static std::string hx64(double d){ uint64_t b; if (d!=d) b=0x7ff8000000000000ULL; else std::memcpy(&b,&d,8); char t[32]; std::snprintf(t,32,"%llx",(unsigned long long)b); return t; }
static std::string hx32(float f){ uint32_t b; if (f!=f) b=0x7fc00000U; else std::memcpy(&b,&f,4); char t[32]; std::snprintf(t,32,"%x",b); return t; }
int main(){
  levicratePortInit();
  int32_t vs[] = {0,1,-1,7,100,2147483647,(-2147483647-1),12345};
  for (int32_t x: vs) for (int32_t y: vs) {
    I(Calc_add(x,y)); S(" "); I(Calc_clampI(x,-5,y>-5?y:-5)); S(" "); I(Calc_bits(x^y)); S(" ");
    if (y!=0){ I(Calc_div(x,y)); S(" "); I(Calc_rem(x,y)); S(" "); }
    I(Calc_lmix(x*31LL,y)); S(" "); I(Calc_lsum(x,y,3)); S(" "); I(Calc_ovf(x)); S(" "); I(Calc_even(x)?1:0); S("\n");
  }
  for (int n=0;n<20;n++){ I(Calc_fact(n)); S(" "); I(Calc_fib(n%15)); S(" "); I(Calc_loops(n)); S("\n"); }
  double ds[] = {0.0,-0.0,1.5,-2.5,1e30,-1e30,std::nan(""),INFINITY,3.0e9,0.5,-0.5,2.5};
  for (double d: ds){
    I(Calc_toInt(d)); S(" "); I(Calc_toLong((float)d)); S(" "); I(Calc_rnd(d)); S(" ");
    o += hx64(Calc_hyp(d,3.0)); S(" "); I(Calc_cmp(d,1.5)); S(" "); o += hx64(Calc_dmix(d,7,5.5f)); S(" ");
    o += hx32(Calc_fmix((float)d,3)); S(" "); I(Calc_shortc(levicrate::jf2i<int32_t,double>(d))); S("\n");
  }
  I(Calc_abs((-2147483647-1))); S(" "); I(Calc_abs(-5)); S("\n");
  I(Calc_bump()); S(" "); I(Calc_bump()); S(" "); Calc_tick(); I(Calc_getCounter()); S(" "); I(Calc_callsGlobal()); S("\n");
  std::fputs(o.c_str(), stdout);
}
