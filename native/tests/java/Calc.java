public class Calc {
  static int counter = 5;
  static final int K = 7;
  static long big;
  static { big = 123456789012L; counter += 1; }
  public static int add(int a, int b) { return a + b; }
  public static int fact(int n) { int r = 1; for (int i = 2; i <= n; i++) r *= i; return r; }
  public static int fib(int n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }
  public static long lmix(long a, int b) { return (a << b) ^ (a >>> 3) + b; }
  public static double hyp(double x, double y) { return Math.sqrt(x * x + y * y); }
  public static int clampI(int v, int lo, int hi) { return Math.max(lo, Math.min(hi, v)); }
  public static int div(int a, int b) { return a / b; }
  public static int rem(int a, int b) { return a % b; }
  public static int toInt(double d) { return (int) d; }
  public static long toLong(float f) { return (long) f; }
  public static int cmp(double a, double b) { if (a < b) return -1; if (a > b) return 1; return 0; }
  public static int bump() { counter += K; return counter; }
  public static float fmix(float a, int b) { return a * b - 1.5f; }
  public static int bits(int x) { return (x << 31) >> 1 | (x >>> 7) & 0xff; }
  public static int shortc(int x) { return (byte) x + (short) x + (char) x; }
  public static int loops(int n) { int s = 0; for (int i = 0; i < n; i++) { if (i % 3 == 0) continue; s += i; } return s; }
  public static int ovf(int a) { return a * a * a + Integer.MAX_VALUE; }
  public static boolean even(int x) { return x % 2 == 0; }
  public static long lsum(long a, long b, long c) { return a + b * c; }
  public static double dmix(double a, long b, float c) { return a / b + c % 3; }
  public static int abs(int x) { return Math.abs(x); }
  public static long rnd(double x) { return Math.round(x); }
  public static int callsGlobal() { return counter + (int) big; }
  public static void tick() { counter++; }
  public static int getCounter() { return counter; }
  // must become explicit stubs:
  public static int sw(int x) { switch (x) { case 1: return 10; case 2: return 20; default: return 0; } }
  public static int sarr(int n) { int[] a = new int[n]; return a.length; }
  public static String name() { return "x"; }
  public static int usesStr(int n) { return Integer.toString(n).length(); }
  public static int tc(int x) { try { return 10 / x; } catch (Exception e) { return -1; } }
  public static int callsStub(int x) { return sw(x) + 1; }
  public int inst(int a) { return a * 2; }

  static String hx(long v) { return Long.toHexString(v); }
  public static void main(String[] a) {
    int[] vs = {0, 1, -1, 7, 100, Integer.MAX_VALUE, Integer.MIN_VALUE, 12345};
    StringBuilder o = new StringBuilder();
    for (int x : vs) for (int y : vs) {
      o.append(add(x, y)).append(' ').append(clampI(x, -5, y > -5 ? y : -5)).append(' ').append(bits(x ^ y)).append(' ');
      if (y != 0) o.append(div(x, y)).append(' ').append(rem(x, y)).append(' ');
      o.append(lmix(x * 31L, y)).append(' ').append(lsum(x, y, 3)).append(' ').append(ovf(x)).append(' ').append(even(x)?1:0).append('\n');
    }
    for (int n = 0; n < 20; n++) o.append(fact(n)).append(' ').append(fib(n % 15)).append(' ').append(loops(n)).append('\n');
    double[] ds = {0.0, -0.0, 1.5, -2.5, 1e30, -1e30, Double.NaN, Double.POSITIVE_INFINITY, 3.0e9, 0.5, -0.5, 2.5};
    for (double d : ds) {
      o.append(toInt(d)).append(' ').append(toLong((float) d)).append(' ').append(rnd(d)).append(' ')
       .append(hx(Double.doubleToLongBits(hyp(d, 3.0)))).append(' ').append(cmp(d, 1.5)).append(' ')
       .append(hx(Double.doubleToLongBits(dmix(d, 7, 5.5f)))).append(' ')
       .append(Integer.toHexString(Float.floatToIntBits(fmix((float) d, 3)))).append(' ')
       .append(shortc((int) d)).append('\n');
    }
    o.append(abs(Integer.MIN_VALUE)).append(' ').append(abs(-5)).append('\n');
    o.append(bump()).append(' ').append(bump()).append(' '); tick(); o.append(getCounter()).append(' ').append(callsGlobal()).append('\n');
    System.out.print(o);
  }
}
