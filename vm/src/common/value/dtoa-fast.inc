/* Fast Schubfach binary64 dtoa, Clinger/Eisel-Lemire flat-ASCII parser,
 * lazy 10..99 string cache, and 1..8-limb BigInt freelist pool.
 * Pure ISO C11, zero per-runtime heap growth when unused. */

#include <fenv.h>

#if defined(_MSC_VER) && !defined(__clang__) && defined(_M_X64)
unsigned __int64 _umul128(unsigned __int64, unsigned __int64, unsigned __int64 *);
unsigned char _addcarry_u64(unsigned char, unsigned __int64, unsigned __int64, unsigned __int64 *);
#pragma intrinsic(_umul128)
#pragma intrinsic(_addcarry_u64)
#endif

#if defined(_MSC_VER) && !defined(__clang__)
#define QJS_BIGINT_COLD_CODE __declspec(noinline) __declspec(code_seg(".text$zz_qjs_bigint"))
#elif defined(__GNUC__) && (defined(_WIN32) || defined(__MINGW32__))
#define QJS_BIGINT_COLD_CODE __attribute__((section(".text$zz_qjs_bigint"), noinline))
#elif defined(__GNUC__) && !defined(__APPLE__)
#define QJS_BIGINT_COLD_CODE __attribute__((section(".text.qjs_bigint"), noinline))
#else
#define QJS_BIGINT_COLD_CODE no_inline
#endif

static inline int32_t qjs_ashr64(int64_t x, int shift)
{
    if (x >= 0)
        return (int32_t)(x >> shift);
    return -(int32_t)(((-x) + ((INT64_C(1) << shift) - 1)) >> shift);
}

static inline uint64_t qjs_umul128(uint64_t a, uint64_t b, uint64_t *lo)
{
#if defined(__SIZEOF_INT128__)
    __uint128_t p = (__uint128_t)a * (__uint128_t)b;
    *lo = (uint64_t)p;
    return (uint64_t)(p >> 64);
#elif defined(_MSC_VER) && !defined(__clang__) && defined(_M_X64)
    unsigned __int64 hi = 0;
    *lo = (uint64_t)_umul128(a, b, &hi);
    return (uint64_t)hi;
#else
    uint64_t a0 = (uint32_t)a, a1 = a >> 32;
    uint64_t b0 = (uint32_t)b, b1 = b >> 32;
    uint64_t p00 = a0 * b0;
    uint64_t p01 = a0 * b1;
    uint64_t p10 = a1 * b0;
    uint64_t p11 = a1 * b1;
    uint64_t mid = (p00 >> 32) + (uint32_t)p01 + (uint32_t)p10;
    *lo = (p00 & UINT64_C(0xffffffff)) | (mid << 32);
    return p11 + (p01 >> 32) + (p10 >> 32) + (mid >> 32);
#endif
}

static inline uint64_t qjs_umul128_hi(uint64_t a, uint64_t b)
{
    uint64_t lo;
    return qjs_umul128(a, b, &lo);
}

typedef struct QJSSchubPow10 {
    uint64_t g1;
    uint64_t g0;
} QJSSchubPow10;

static const QJSSchubPow10 qjs_schub_pow10[617] = {
    {UINT64_C(0x4f0cedc95a718dd4), UINT64_C(0xb603d1613541a369)}, /* k=-324 */
    {UINT64_C(0x7e7b160ef71c1621), UINT64_C(0x23394f01eecf6bdb)}, /* k=-323 */
    {UINT64_C(0x652f44d8c5b011b4), UINT64_C(0x1c2dd8ce58a5efe3)}, /* k=-322 */
    {UINT64_C(0x50f29d7a37c00e29), UINT64_C(0xb024ad71e084bfe9)}, /* k=-321 */
    {UINT64_C(0x40c21794f96671ba), UINT64_C(0xf3508ac1806a3321)}, /* k=-320 */
    {UINT64_C(0x679cf287f570b5f7), UINT64_C(0xebb411359a438501)}, /* k=-319 */
    {UINT64_C(0x52e3f5399126f7f9), UINT64_C(0x895cda9148360401)}, /* k=-318 */
    {UINT64_C(0x424ff76140ebf994), UINT64_C(0x6de3e20dd35e699a)}, /* k=-317 */
    {UINT64_C(0x6a198bcece465c20), UINT64_C(0xafd303495230a8f6)}, /* k=-316 */
    {UINT64_C(0x54e13ca571d1e34d), UINT64_C(0x59759c3aa826ed92)}, /* k=-315 */
    {UINT64_C(0x43e763b78e4182a4), UINT64_C(0x479149c886858adb)}, /* k=-314 */
    {UINT64_C(0x6ca56c58e39c043a), UINT64_C(0x0c1ba940d73c115f)}, /* k=-313 */
    {UINT64_C(0x56eabd13e9499cfb), UINT64_C(0x3ce2edcd78fcdab2)}, /* k=-312 */
    {UINT64_C(0x458897432107b0c8), UINT64_C(0xfd8257d793fd7bc2)}, /* k=-311 */
    {UINT64_C(0x6f40f20501a5e7a7), UINT64_C(0xfc03bfbf532f2c69)}, /* k=-310 */
    {UINT64_C(0x5900c19d9aeb1fb9), UINT64_C(0x96696632a8f289ee)}, /* k=-309 */
    {UINT64_C(0x4733ce17af227fc7), UINT64_C(0xab8784f553f53b25)}, /* k=-308 */
    {UINT64_C(0x71ec7cf2b1d0cc72), UINT64_C(0xac0c07eeecbb91d4)}, /* k=-307 */
    {UINT64_C(0x5b2397288e40a38e), UINT64_C(0xf0099ff256fc74aa)}, /* k=-306 */
    {UINT64_C(0x48e945ba0b66e93f), UINT64_C(0x266e198eabfd2a21)}, /* k=-305 */
    {UINT64_C(0x74a86f90123e41fe), UINT64_C(0xa3e35c1779951035)}, /* k=-304 */
    {UINT64_C(0x5d538c7341cb67fe), UINT64_C(0xe982b012c7aa735e)}, /* k=-303 */
    {UINT64_C(0x4aa93d29016f8665), UINT64_C(0x879bc00f0621f5e5)}, /* k=-302 */
    {UINT64_C(0x77752ea8024c0a3c), UINT64_C(0x0c2c667e7036563b)}, /* k=-301 */
    {UINT64_C(0x5f90f22001d66e96), UINT64_C(0x70238531f35eab62)}, /* k=-300 */
    {UINT64_C(0x4c73f4e667debede), UINT64_C(0xc01c6a8e5c4bbc4f)}, /* k=-299 */
    {UINT64_C(0x7a532170a6313164), UINT64_C(0x6693ddb093ac607e)}, /* k=-298 */
    {UINT64_C(0x61dc1ac084f42783), UINT64_C(0x854317c076238065)}, /* k=-297 */
    {UINT64_C(0x4e49af006a5cec69), UINT64_C(0x3768dfcd2b4f99ea)}, /* k=-296 */
    {UINT64_C(0x7d42b19a43c7e0a8), UINT64_C(0x58a7cc7b787f5ca9)}, /* k=-295 */
    {UINT64_C(0x64355ae1cfd31a20), UINT64_C(0x46eca395f9ff7d54)}, /* k=-294 */
    {UINT64_C(0x502aaf1b0ca8e1b3), UINT64_C(0x6bf082de61993110)}, /* k=-293 */
    {UINT64_C(0x402225af3d53e7c2), UINT64_C(0xbcc068b1e7adc0da)}, /* k=-292 */
    {UINT64_C(0x669d0918621fd937), UINT64_C(0x94670de972af9af6)}, /* k=-291 */
    {UINT64_C(0x52173a79e8197a92), UINT64_C(0xdd1f3e545bbfaf2b)}, /* k=-290 */
    {UINT64_C(0x41ac2ec7ece12edb), UINT64_C(0xe418fea9e2ffbf56)}, /* k=-289 */
    {UINT64_C(0x69137e0cae3517c6), UINT64_C(0x39c1977637ff9889)}, /* k=-288 */
    {UINT64_C(0x540f980a24f74638), UINT64_C(0x2e34792b5fffad3b)}, /* k=-287 */
    {UINT64_C(0x433facd4ea5f6b60), UINT64_C(0x24f6c755e666242f)}, /* k=-286 */
    {UINT64_C(0x6b991487dd657899), UINT64_C(0xd4be0bbca3d6a04b)}, /* k=-285 */
    {UINT64_C(0x5614106cb11dfa14), UINT64_C(0xaa31a2fd4fdee6a3)}, /* k=-284 */
    {UINT64_C(0x44dcd9f08db194dd), UINT64_C(0x54f482643fe5854f)}, /* k=-283 */
    {UINT64_C(0x6e2e2980e2b5bafb), UINT64_C(0xbb20d0a0663c087e)}, /* k=-282 */
    {UINT64_C(0x5824ee00b55e2f2f), UINT64_C(0xc8e70d4d1e966d32)}, /* k=-281 */
    {UINT64_C(0x4683f19a2ab1bf59), UINT64_C(0x6d85a43db211f0f5)}, /* k=-280 */
    {UINT64_C(0x70d31c29dde93228), UINT64_C(0xaf3c39fc501cb4ba)}, /* k=-279 */
    {UINT64_C(0x5a427cee4b20f4ed), UINT64_C(0x58fcfb304016f6fc)}, /* k=-278 */
    {UINT64_C(0x483530bea280c3f1), UINT64_C(0x13fd95c033459263)}, /* k=-277 */
    {UINT64_C(0x73884dfdd0ce064e), UINT64_C(0x86628933853c1d6b)}, /* k=-276 */
    {UINT64_C(0x5c6d0b3173d8050b), UINT64_C(0x9eb53a8f9dc9b122)}, /* k=-275 */
    {UINT64_C(0x49f0d5c129799da2), UINT64_C(0xe55dc872e4a15a82)}, /* k=-274 */
    {UINT64_C(0x764e22cea8c295d1), UINT64_C(0x6efc73eb076890d0)}, /* k=-273 */
    {UINT64_C(0x5ea4e8a553cede41), UINT64_C(0x2596c3226c53a70d)}, /* k=-272 */
    {UINT64_C(0x4bb72084430be500), UINT64_C(0xeadf0281f042ec0a)}, /* k=-271 */
    {UINT64_C(0x792500d39e796e67), UINT64_C(0xde319d9cb39e4677)}, /* k=-270 */
    {UINT64_C(0x60ea670fb1fabeb9), UINT64_C(0x7e8e17b08fb1d1f9)}, /* k=-269 */
    {UINT64_C(0x4d885272f4c89894), UINT64_C(0x653e795a0c8e4194)}, /* k=-268 */
    {UINT64_C(0x7c0d50b7ee0dc0ed), UINT64_C(0x6eca5bc3474a0286)}, /* k=-267 */
    {UINT64_C(0x633dda2cbe716724), UINT64_C(0x58a1e3029f6e686b)}, /* k=-266 */
    {UINT64_C(0x4f64ae8a31f45283), UINT64_C(0x7a1b1c0219252056)}, /* k=-265 */
    {UINT64_C(0x7f077da9e986ea6b), UINT64_C(0xf691c669c1d50089)}, /* k=-264 */
    {UINT64_C(0x659f97bb2138bb89), UINT64_C(0x920e38549b10cd3a)}, /* k=-263 */
    {UINT64_C(0x514c796280fa2fa1), UINT64_C(0x41a4f9dd48da3dc8)}, /* k=-262 */
    {UINT64_C(0x4109fab533fb594d), UINT64_C(0xce1d94b10714fe3a)}, /* k=-261 */
    {UINT64_C(0x680ff788532bc216), UINT64_C(0x1695bab4d82196c3)}, /* k=-260 */
    {UINT64_C(0x533ff939dc2301ab), UINT64_C(0x4544955d79b4789c)}, /* k=-259 */
    {UINT64_C(0x4299942e49b59aef), UINT64_C(0x6a9d444ac7c393b0)}, /* k=-258 */
    {UINT64_C(0x6a8f537d42bc2b18), UINT64_C(0xaa953a113f9f52b3)}, /* k=-257 */
    {UINT64_C(0x553f75fdcefcef46), UINT64_C(0xeeddc80dcc7f755c)}, /* k=-256 */
    {UINT64_C(0x4432c4cb0bfd8c38), UINT64_C(0xbf17d33e3d32c44a)}, /* k=-255 */
    {UINT64_C(0x6d1e07ab466279f4), UINT64_C(0x64f2eb96c8513a10)}, /* k=-254 */
    {UINT64_C(0x574b3955d1e86190), UINT64_C(0x50c2561239da94d9)}, /* k=-253 */
    {UINT64_C(0x45d5c777db204e0d), UINT64_C(0x0d6844db617baa48)}, /* k=-252 */
    {UINT64_C(0x6fbc72595e9a167b), UINT64_C(0x48a6d4923592aa0c)}, /* k=-251 */
    {UINT64_C(0x59638eade54811fc), UINT64_C(0x3a1f1074f7a8880a)}, /* k=-250 */
    {UINT64_C(0x4782d88b1dd34196), UINT64_C(0x94e5a6c3f953a008)}, /* k=-249 */
    {UINT64_C(0x726af411c952028a), UINT64_C(0x87d5d79ff55299a6)}, /* k=-248 */
    {UINT64_C(0x5b88c3416ddb353b), UINT64_C(0x9fde4619910ee151)}, /* k=-247 */
    {UINT64_C(0x493a35cdf17c2a96), UINT64_C(0x197e9e7ada724ddb)}, /* k=-246 */
    {UINT64_C(0x7529efafe8c6aa89), UINT64_C(0xc26430c490b6e2f7)}, /* k=-245 */
    {UINT64_C(0x5dbb262653d22207), UINT64_C(0xceb68d6a0d5f1bf9)}, /* k=-244 */
    {UINT64_C(0x4afc1e850fdb4e6c), UINT64_C(0xa55ed7880ab27cc8)}, /* k=-243 */
    {UINT64_C(0x77f9ca6e7fc54a47), UINT64_C(0x6efe25a67783fad9)}, /* k=-242 */
    {UINT64_C(0x5ffb085866376e9f), UINT64_C(0x8bfe84852c69957a)}, /* k=-241 */
    {UINT64_C(0x4cc8d379eb5f8bb2), UINT64_C(0xd66536d0f0547795)}, /* k=-240 */
    {UINT64_C(0x7adaebf64565ac51), UINT64_C(0x570857b4b3ba58ee)}, /* k=-239 */
    {UINT64_C(0x6248bcc5045156a7), UINT64_C(0x78d3795d5c9513f2)}, /* k=-238 */
    {UINT64_C(0x4ea0970403744552), UINT64_C(0xc70f944ab0774328)}, /* k=-237 */
    {UINT64_C(0x7dcdbe6cd253a21e), UINT64_C(0x0b4c207780bed1d9)}, /* k=-236 */
    {UINT64_C(0x64a498570ea94e7e), UINT64_C(0x6f7019f933cbdb14)}, /* k=-235 */
    {UINT64_C(0x5083ad1272210b98), UINT64_C(0x59267b2dc3097c10)}, /* k=-234 */
    {UINT64_C(0x40695741f4e73c79), UINT64_C(0xe0eb95be35a1300d)}, /* k=-233 */
    {UINT64_C(0x670ef2032171fa5c), UINT64_C(0x9b12893055ceb348)}, /* k=-232 */
    {UINT64_C(0x52725b35b45b2eb0), UINT64_C(0x7c0ed426ab0bc2a0)}, /* k=-231 */
    {UINT64_C(0x41f515c49048f226), UINT64_C(0xc9a5768555a3021a)}, /* k=-230 */
    {UINT64_C(0x698822d41a0e503e), UINT64_C(0x0f6f24088904d029)}, /* k=-229 */
    {UINT64_C(0x546ce8a9ae71d9cb), UINT64_C(0x3f8c1cd3a0d0a687)}, /* k=-228 */
    {UINT64_C(0x438a53baf1f4ae3c), UINT64_C(0x32d67d761a408539)}, /* k=-227 */
    {UINT64_C(0x6c1085f7e9877d2d), UINT64_C(0x1e23fbf02a00d528)}, /* k=-226 */
    {UINT64_C(0x56739e5fee05fdbd), UINT64_C(0xb1b663268800aa86)}, /* k=-225 */
    {UINT64_C(0x45294b7ff19e6497), UINT64_C(0xc15eb5b86ccd5538)}, /* k=-224 */
    {UINT64_C(0x6ea878ccb5ca3a8c), UINT64_C(0x68978927147bbb8d)}, /* k=-223 */
    {UINT64_C(0x5886c70a2b082ed6), UINT64_C(0xba12d41f43962fa4)}, /* k=-222 */
    {UINT64_C(0x46d238d4ef39bf12), UINT64_C(0x2e75767f6944f2ea)}, /* k=-221 */
    {UINT64_C(0x71505aee4b8f981d), UINT64_C(0x172257324207eb0f)}, /* k=-220 */
    {UINT64_C(0x5aa6af25093face4), UINT64_C(0x1281df5b680655a6)}, /* k=-219 */
    {UINT64_C(0x488558ea6dcc8a50), UINT64_C(0x0ece4c4920051152)}, /* k=-218 */
    {UINT64_C(0x74088e43e2e0dd4c), UINT64_C(0xe47d46db666e821c)}, /* k=-217 */
    {UINT64_C(0x5cd3a5031be71770), UINT64_C(0xb6ca9f15eb8b9b4a)}, /* k=-216 */
    {UINT64_C(0x4a42ea68e31f45f3), UINT64_C(0xc56ee5ab22d615d5)}, /* k=-215 */
    {UINT64_C(0x76d1770e38320986), UINT64_C(0x08b16f7837bcefba)}, /* k=-214 */
    {UINT64_C(0x5f0df8d82cf4d46b), UINT64_C(0x3a278c602c97262f)}, /* k=-213 */
    {UINT64_C(0x4c0b2d79bd90a9ef), UINT64_C(0x61b93d19bd45b826)}, /* k=-212 */
    {UINT64_C(0x79ab7bf5fc1aa97f), UINT64_C(0x02c1fb5c620926a2)}, /* k=-211 */
    {UINT64_C(0x6155fcc4c9aeedff), UINT64_C(0x3567fc49e807521b)}, /* k=-210 */
    {UINT64_C(0x4dde63d0a158be65), UINT64_C(0xc453303b2005db49)}, /* k=-209 */
    {UINT64_C(0x7c97061a9bc130a2), UINT64_C(0xd3b84d2b666fc542)}, /* k=-208 */
    {UINT64_C(0x63ac04e2163426e8), UINT64_C(0xa9603dbc51f30435)}, /* k=-207 */
    {UINT64_C(0x4fbcd0b4de901f20), UINT64_C(0x8780316374c269c4)}, /* k=-206 */
    {UINT64_C(0x7f9481216419cb67), UINT64_C(0x3f338238bad0a939)}, /* k=-205 */
    {UINT64_C(0x6610674de9ae3c52), UINT64_C(0x98f601c6fbda20fb)}, /* k=-204 */
    {UINT64_C(0x51a6b90b21583042), UINT64_C(0x13f8016bfcae80c9)}, /* k=-203 */
    {UINT64_C(0x41522da2811359ce), UINT64_C(0x76600123308b9a3a)}, /* k=-202 */
    {UINT64_C(0x68837c3734ebc2e3), UINT64_C(0xf0999b6b80df5d2a)}, /* k=-201 */
    {UINT64_C(0x539c635f5d8968b6), UINT64_C(0x5a147c5600b2b0ee)}, /* k=-200 */
    {UINT64_C(0x42e382b2b13aba2b), UINT64_C(0x7b4396ab33c22725)}, /* k=-199 */
    {UINT64_C(0x6b059deab52ac378), UINT64_C(0xc538f111ec69d83b)}, /* k=-198 */
    {UINT64_C(0x559e17eef755692d), UINT64_C(0x6a93f40e56bb1362)}, /* k=-197 */
    {UINT64_C(0x447e798bf91120f1), UINT64_C(0x220ff671defc0f82)}, /* k=-196 */
    {UINT64_C(0x6d9728dff4e834b5), UINT64_C(0x034cbd82fe6018d0)}, /* k=-195 */
    {UINT64_C(0x57ac20b32a535d5d), UINT64_C(0x9c3d6468cb8013da)}, /* k=-194 */
    {UINT64_C(0x46234d5c21dc4ab1), UINT64_C(0x49cab6ba3c667648)}, /* k=-193 */
    {UINT64_C(0x70387bc69c93aab5), UINT64_C(0x42ddf129fa3d8a0c)}, /* k=-192 */
    {UINT64_C(0x59c6c96bb076222a), UINT64_C(0x9be4c0ee61cad4d7)}, /* k=-191 */
    {UINT64_C(0x47d23abc8d2b4e88), UINT64_C(0x7cb700beb4a243df)}, /* k=-190 */
    {UINT64_C(0x72e9f79415121740), UINT64_C(0xc78b34645436d2fe)}, /* k=-189 */
    {UINT64_C(0x5bee5fa9aa74df67), UINT64_C(0x0608f6b6a9c57598)}, /* k=-188 */
    {UINT64_C(0x498b7fbaeec3e5ec), UINT64_C(0x04d3f892216ac47a)}, /* k=-187 */
    {UINT64_C(0x75abff917e063cac), UINT64_C(0xd4865a8368aad3f6)}, /* k=-186 */
    {UINT64_C(0x5e2332dacb38308a), UINT64_C(0x439eaecf86ef0ff8)}, /* k=-185 */
    {UINT64_C(0x4b4f5be23c2cf3a1), UINT64_C(0xcfb22572d258d993)}, /* k=-184 */
    {UINT64_C(0x787ef969f9e185cf), UINT64_C(0xb2b6a251508e28eb)}, /* k=-183 */
    {UINT64_C(0x60659454c7e79e3f), UINT64_C(0xc22bb50dda0b53ef)}, /* k=-182 */
    {UINT64_C(0x4d1e1043d31fb1cc), UINT64_C(0x9b562a717b3c4326)}, /* k=-181 */
    {UINT64_C(0x7b634d3951cc4fad), UINT64_C(0xc556aa4f2b939ea3)}, /* k=-180 */
    {UINT64_C(0x62b5d7610e3d0c8b), UINT64_C(0x0445550c22dc7ee9)}, /* k=-179 */
    {UINT64_C(0x4ef7df80d830d6d5), UINT64_C(0x9d044409b57d3254)}, /* k=-178 */
    {UINT64_C(0x7e59659af38157bc), UINT64_C(0x2e6d39a92261ea20)}, /* k=-177 */
    {UINT64_C(0x65145148c2cddfc9), UINT64_C(0xbebdc7ba81e7ee80)}, /* k=-176 */
    {UINT64_C(0x50dd0dd3cf0b196e), UINT64_C(0x32316c9534b98b9a)}, /* k=-175 */
    {UINT64_C(0x40b0d7dca5a27abe), UINT64_C(0x8e8df0775d613c7b)}, /* k=-174 */
    {UINT64_C(0x678159610903f797), UINT64_C(0x4a7cb3f22f01fa5e)}, /* k=-173 */
    {UINT64_C(0x52cde11a6d9cc612), UINT64_C(0xa1fd5cc1bf34c84b)}, /* k=-172 */
    {UINT64_C(0x423e4daebe1704db), UINT64_C(0xb4cab09aff5d6d09)}, /* k=-171 */
    {UINT64_C(0x69fd4917968b3af9), UINT64_C(0x21444dc4cbc8ae75)}, /* k=-170 */
    {UINT64_C(0x54caa0dfaba29594), UINT64_C(0x1a9d0b03d63a252a)}, /* k=-169 */
    {UINT64_C(0x43d54d7fbc821143), UINT64_C(0x487da269782e8422)}, /* k=-168 */
    {UINT64_C(0x6c887bff94034ed2), UINT64_C(0x0d95d0a8c04a6d03)}, /* k=-167 */
    {UINT64_C(0x56d396661002a574), UINT64_C(0xd7ab0d53cd085736)}, /* k=-166 */
    {UINT64_C(0x457611eb40021df7), UINT64_C(0x12ef3ddca406ac2b)}, /* k=-165 */
    {UINT64_C(0x6f234fdeccd02ff1), UINT64_C(0xb7e52fc76cd779de)}, /* k=-164 */
    {UINT64_C(0x58e90cb23d73598e), UINT64_C(0x2cb7596c5712c7e5)}, /* k=-163 */
    {UINT64_C(0x4720d6f4fdf5e13e), UINT64_C(0x8a2c4789df423984)}, /* k=-162 */
    {UINT64_C(0x71ce24bb2fefceca), UINT64_C(0x76ad3f42fed05c06)}, /* k=-161 */
    {UINT64_C(0x5b0b5095bff30bd5), UINT64_C(0x2bbdcc3598a6b005)}, /* k=-160 */
    {UINT64_C(0x48d5da11665c0977), UINT64_C(0x5631702ae085599e)}, /* k=-159 */
    {UINT64_C(0x74895ce8a3c6758b), UINT64_C(0xbd1be6ab00d55c2f)}, /* k=-158 */
    {UINT64_C(0x5d3ab0ba1c9ec46f), UINT64_C(0xca7cb888cd777cf3)}, /* k=-157 */
    {UINT64_C(0x4a955a2e7d4bd059), UINT64_C(0x6eca2d3a3df930c2)}, /* k=-156 */
    {UINT64_C(0x77555d172edfb3c2), UINT64_C(0x4add1529fcc1e79d)}, /* k=-155 */
    {UINT64_C(0x5f777dac257fc301), UINT64_C(0xd57daa87fd67ec7e)}, /* k=-154 */
    {UINT64_C(0x4c5f97bceacc9c01), UINT64_C(0x7797bb9ffdecbd31)}, /* k=-153 */
    {UINT64_C(0x7a328c6177adc668), UINT64_C(0xbf592c332fe12eb5)}, /* k=-152 */
    {UINT64_C(0x61c209e792f16b86), UINT64_C(0xff7a89c28cb4255e)}, /* k=-151 */
    {UINT64_C(0x4e34d4b9425abc6b), UINT64_C(0xff953b020a29b77e)}, /* k=-150 */
    {UINT64_C(0x7d21545b9d5dfa46), UINT64_C(0x65bb919cdd0f8bfd)}, /* k=-149 */
    {UINT64_C(0x641aa9e2e44b2e9e), UINT64_C(0xb7c9414a4a72d664)}, /* k=-148 */
    {UINT64_C(0x501554b5836f587e), UINT64_C(0xf96dcdd5085bdeb7)}, /* k=-147 */
    {UINT64_C(0x4011109135f2ad32), UINT64_C(0x6124a4aa6d164bc5)}, /* k=-146 */
    {UINT64_C(0x6681b41b89844850), UINT64_C(0x9b6dd443e1bd4608)}, /* k=-145 */
    {UINT64_C(0x52015ce2d469d373), UINT64_C(0xaf8b10364e3104d4)}, /* k=-144 */
    {UINT64_C(0x419ab0b576bb0f8f), UINT64_C(0xbfa2735ea4f403dd)}, /* k=-143 */
    {UINT64_C(0x68f781225791b27f), UINT64_C(0x9903ebcaa1866c94)}, /* k=-142 */
    {UINT64_C(0x53f9341b79415b99), UINT64_C(0x4736563bb46b8a10)}, /* k=-141 */
    {UINT64_C(0x432dc3492dcde2e1), UINT64_C(0x05c511c95d22d4da)}, /* k=-140 */
    {UINT64_C(0x6b7c6ba849496b01), UINT64_C(0xa2d4e9422e9e215c)}, /* k=-139 */
    {UINT64_C(0x55fd22ed076def34), UINT64_C(0x8243edce8bb1b44a)}, /* k=-138 */
    {UINT64_C(0x44ca82573924bf5d), UINT64_C(0x350324a53c8e29d5)}, /* k=-137 */
    {UINT64_C(0x6e10d08b8ea1322e), UINT64_C(0xbb383aa1fa7d0fba)}, /* k=-136 */
    {UINT64_C(0x580d73a2d880f4f2), UINT64_C(0x2f602ee7fb973fc8)}, /* k=-135 */
    {UINT64_C(0x4671294f139a5d8e), UINT64_C(0x8c4cf2532fac3307)}, /* k=-134 */
    {UINT64_C(0x70b50ee4ec2a2f4a), UINT64_C(0x7a14b6eb7f79eb3e)}, /* k=-133 */
    {UINT64_C(0x5a2a7250bcee8c3b), UINT64_C(0x94dd5f22cc6188fe)}, /* k=-132 */
    {UINT64_C(0x4821f50d63f209c9), UINT64_C(0x43e44c1bd6b46d98)}, /* k=-131 */
    {UINT64_C(0x736988156cb6760e), UINT64_C(0xd306e02c8aba48f3)}, /* k=-130 */
    {UINT64_C(0x5c546cddf091f80b), UINT64_C(0xdc058023a22ea0c3)}, /* k=-129 */
    {UINT64_C(0x49dd23e4c074c66f), UINT64_C(0xe33799b61b58809c)}, /* k=-128 */
    {UINT64_C(0x762e9fd467213d7f), UINT64_C(0xd1f28f89c55a6760)}, /* k=-127 */
    {UINT64_C(0x5e8bb3105280fdff), UINT64_C(0xdb2872d49de1ec4d)}, /* k=-126 */
    {UINT64_C(0x4ba2f5a6a8673199), UINT64_C(0x7c205bdd4b1b2371)}, /* k=-125 */
    {UINT64_C(0x7904bc3dda3eb5c2), UINT64_C(0x6033c62ede91d24e)}, /* k=-124 */
    {UINT64_C(0x60d09697e1cbc49b), UINT64_C(0x80296b58b20e41d8)}, /* k=-123 */
    {UINT64_C(0x4d73abacb4a303af), UINT64_C(0x99babc46f4d834ad)}, /* k=-122 */
    {UINT64_C(0x7bec45e12104d2b2), UINT64_C(0x8f912d3e548d2114)}, /* k=-121 */
    {UINT64_C(0x63236b1a80d0a88e), UINT64_C(0xd940f0feaa0a80dd)}, /* k=-120 */
    {UINT64_C(0x4f4f88e200a6ed3f), UINT64_C(0x1433f3feee6ecd7e)}, /* k=-119 */
    {UINT64_C(0x7ee5a7d0010b1531), UINT64_C(0xb9ecb997e3e47bfc)}, /* k=-118 */
    {UINT64_C(0x6584864000d5aa8e), UINT64_C(0x2e56fadfe9839663)}, /* k=-117 */
    {UINT64_C(0x5136d1cccd77bba4), UINT64_C(0xf1df2f19879c784f)}, /* k=-116 */
    {UINT64_C(0x40f8a7d70ac62fb7), UINT64_C(0x27e5bf479fb06040)}, /* k=-115 */
    {UINT64_C(0x67f43fbe77a37f8b), UINT64_C(0x7309320c32b3cd32)}, /* k=-114 */
    {UINT64_C(0x5329cc985fb5ffa2), UINT64_C(0xc26dc1a35bc30a8f)}, /* k=-113 */
    {UINT64_C(0x4287d6e04c91994f), UINT64_C(0x01f167b5e3026ed9)}, /* k=-112 */
    {UINT64_C(0x6a72f166e0e8f54b), UINT64_C(0x364f0c563803e48e)}, /* k=-111 */
    {UINT64_C(0x5528c11f1a53f76f), UINT64_C(0x5ea5a3782ccfea0b)}, /* k=-110 */
    {UINT64_C(0x44209a7f48432c59), UINT64_C(0x188482c68a3fee6f)}, /* k=-109 */
    {UINT64_C(0x6d00f7320d3846f4), UINT64_C(0xf40737a410664a4b)}, /* k=-108 */
    {UINT64_C(0x5733f8f4d76038c3), UINT64_C(0xf66c2c834051d509)}, /* k=-107 */
    {UINT64_C(0x45c32d90ac4cfa36), UINT64_C(0x5ebcf0690041773b)}, /* k=-106 */
    {UINT64_C(0x6f9eaf4de07b29f0), UINT64_C(0x9794b3db339bf1f7)}, /* k=-105 */
    {UINT64_C(0x594bbf71806287f3), UINT64_C(0xac76f648f6165b2c)}, /* k=-104 */
    {UINT64_C(0x476fcc5acd1b9ff6), UINT64_C(0x23925ea0c4deaf57)}, /* k=-103 */
    {UINT64_C(0x724c7a2ae1c5ccbd), UINT64_C(0x05b6fdce07cab224)}, /* k=-102 */
    {UINT64_C(0x5b7061bbe7d17097), UINT64_C(0x37c597d8063bc1b7)}, /* k=-101 */
    {UINT64_C(0x4926b496530df3ac), UINT64_C(0x2c9e1313382fce2c)}, /* k=-100 */
    {UINT64_C(0x750aba8a1e7cb913), UINT64_C(0x7a9684eb8d1949df)}, /* k=-99 */
    {UINT64_C(0x5da22ed4e530940f), UINT64_C(0x95453722d7476e4c)}, /* k=-98 */
    {UINT64_C(0x4ae825771dc07672), UINT64_C(0xddd0f8e8ac39250a)}, /* k=-97 */
    {UINT64_C(0x77d9d58b62cd8a51), UINT64_C(0x62e7f4a779f50810)}, /* k=-96 */
    {UINT64_C(0x5fe177a2b5713b74), UINT64_C(0x4f1ff6ec6190d340)}, /* k=-95 */
    {UINT64_C(0x4cb45fb55df42f90), UINT64_C(0x3f4cc589e7a70f66)}, /* k=-94 */
    {UINT64_C(0x7aba32bbc986b280), UINT64_C(0x6547a2763f71b23d)}, /* k=-93 */
    {UINT64_C(0x622e8efca1388ecd), UINT64_C(0x1dd2e85e9927c1cb)}, /* k=-92 */
    {UINT64_C(0x4e8ba596e760723d), UINT64_C(0xb17586b2141fce3c)}, /* k=-91 */
    {UINT64_C(0x7dac3c24a5671d2f), UINT64_C(0x8255a4502032e392)}, /* k=-90 */
    {UINT64_C(0x6489c9b6eab8e426), UINT64_C(0x01de1d0ce68f1c75)}, /* k=-89 */
    {UINT64_C(0x506e3af8bbc71ceb), UINT64_C(0x34b1b0d71ed8e391)}, /* k=-88 */
    {UINT64_C(0x40582f2d6305b0bc), UINT64_C(0x2a27c0ac18ad82db)}, /* k=-87 */
    {UINT64_C(0x66f37eaf04d5e793), UINT64_C(0x76a601135aaf37c4)}, /* k=-86 */
    {UINT64_C(0x525c6558d0ab1fa9), UINT64_C(0x2bb800dc488c2c9d)}, /* k=-85 */
    {UINT64_C(0x41e384470d55b2ed), UINT64_C(0xbc9333e36d3cf07e)}, /* k=-84 */
    {UINT64_C(0x696c06d81555eb15), UINT64_C(0xfa851fd2486180c9)}, /* k=-83 */
    {UINT64_C(0x54566be0111188de), UINT64_C(0x6204197506b46707)}, /* k=-82 */
    {UINT64_C(0x4378564cda746d7e), UINT64_C(0xb4d0145d9ef6b8d2)}, /* k=-81 */
    {UINT64_C(0x6bf3bd47c3ed7bfd), UINT64_C(0xee19ba2f64bdf484)}, /* k=-80 */
    {UINT64_C(0x565c976c9cbdfccb), UINT64_C(0x24e161bf83cb2a03)}, /* k=-79 */
    {UINT64_C(0x4516df8a16fe63d5), UINT64_C(0xb71ab499363c219c)}, /* k=-78 */
    {UINT64_C(0x6e8aff4357fd6c89), UINT64_C(0x24f7875b89f9cf60)}, /* k=-77 */
    {UINT64_C(0x586f329c466456d4), UINT64_C(0x1d92d2afa194a5e6)}, /* k=-76 */
    {UINT64_C(0x46bf5bb038504576), UINT64_C(0x7e0f0ef2e7aa1e52)}, /* k=-75 */
    {UINT64_C(0x71322c4d26e6d58a), UINT64_C(0x634b4b1e3f7696e9)}, /* k=-74 */
    {UINT64_C(0x5a8e89d75252446e), UINT64_C(0xb5d5d5b1cc5edf21)}, /* k=-73 */
    {UINT64_C(0x487207df750e9d25), UINT64_C(0x5e44aaf4a37f18e7)}, /* k=-72 */
    {UINT64_C(0x73e9a63254e42ea2), UINT64_C(0x306dde5438cb5b0c)}, /* k=-71 */
    {UINT64_C(0x5cbaeb5b771cf21b), UINT64_C(0x59f17ea9c70915a3)}, /* k=-70 */
    {UINT64_C(0x4a2f22af927d8e7c), UINT64_C(0x47f465549f3a77b6)}, /* k=-69 */
    {UINT64_C(0x76b1d118ea627d93), UINT64_C(0xa653d55431f725ef)}, /* k=-68 */
    {UINT64_C(0x5ef4a74721e86476), UINT64_C(0x1ea977768e5f518c)}, /* k=-67 */
    {UINT64_C(0x4bf6ec38e7ed1d2b), UINT64_C(0x4bbac5f871e5dad7)}, /* k=-66 */
    {UINT64_C(0x798b138e3fe1c845), UINT64_C(0x45f7a3271ca2f7be)}, /* k=-65 */
    {UINT64_C(0x613c0fa4ffe7d36a), UINT64_C(0x9e5fb5b8e3b592fe)}, /* k=-64 */
    {UINT64_C(0x4dc9a61d998642bb), UINT64_C(0xb1e62afa4fc47598)}, /* k=-63 */
    {UINT64_C(0x7c75d695c2706ac5), UINT64_C(0xe97044c3b2d3ef5a)}, /* k=-62 */
    {UINT64_C(0x63917877cec0556b), UINT64_C(0x21269d695bdcbf7b)}, /* k=-61 */
    {UINT64_C(0x4fa793930bcd1122), UINT64_C(0x80ebb121164a32c9)}, /* k=-60 */
    {UINT64_C(0x7f7285b812e1b504), UINT64_C(0x01791b6823a9eadb)}, /* k=-59 */
    {UINT64_C(0x65f537c675815d9c), UINT64_C(0xcdfa7c534fbb2249)}, /* k=-58 */
    {UINT64_C(0x5190f96b91344ae3), UINT64_C(0xd7fb96a90c95b507)}, /* k=-57 */
    {UINT64_C(0x4140c78940f6a24f), UINT64_C(0xdffc78873d4490d3)}, /* k=-56 */
    {UINT64_C(0x6867a5a867f103b2), UINT64_C(0xfffa5a71fba0e7b7)}, /* k=-55 */
    {UINT64_C(0x53861e2053273628), UINT64_C(0xccc8485b2fb3ec93)}, /* k=-54 */
    {UINT64_C(0x42d1b1b375b8f820), UINT64_C(0xa3d36d15bfc323a9)}, /* k=-53 */
    {UINT64_C(0x6ae91c5255f4c034), UINT64_C(0x39524822cc6b6c41)}, /* k=-52 */
    {UINT64_C(0x558749db77f70029), UINT64_C(0xc77506823d22bd01)}, /* k=-51 */
    {UINT64_C(0x446c3b15f9926687), UINT64_C(0xd2c40534fdb56401)}, /* k=-50 */
    {UINT64_C(0x6d79f82328ea3da6), UINT64_C(0x1e066ebb2f88a001)}, /* k=-49 */
    {UINT64_C(0x5794c6828721caeb), UINT64_C(0x4b385895bfa08001)}, /* k=-48 */
    {UINT64_C(0x46109eced2816f22), UINT64_C(0xa2937a11661a0001)}, /* k=-47 */
    {UINT64_C(0x701a97b150cf1837), UINT64_C(0x6a85901bd6900001)}, /* k=-46 */
    {UINT64_C(0x59aedfc10d7279c5), UINT64_C(0xeed1401645400001)}, /* k=-45 */
    {UINT64_C(0x47bf19673df52e37), UINT64_C(0xf2410011d1000001)}, /* k=-44 */
    {UINT64_C(0x72cb5bd86321e38c), UINT64_C(0xb6ce6682e8000001)}, /* k=-43 */
    {UINT64_C(0x5bd5e313828182d6), UINT64_C(0xf8a51ecf20000001)}, /* k=-42 */
    {UINT64_C(0x4977e8dc68679bdf), UINT64_C(0x2d50e57280000001)}, /* k=-41 */
    {UINT64_C(0x758ca7c70d7292fe), UINT64_C(0xaee7d58400000001)}, /* k=-40 */
    {UINT64_C(0x5e0a1fd271287598), UINT64_C(0x8becaad000000001)}, /* k=-39 */
    {UINT64_C(0x4b3b4ca85a86c47a), UINT64_C(0x098a224000000001)}, /* k=-38 */
    {UINT64_C(0x785ee10d5da46d90), UINT64_C(0x0f436a0000000001)}, /* k=-37 */
    {UINT64_C(0x604be73de4838ad9), UINT64_C(0xa5cf880000000001)}, /* k=-36 */
    {UINT64_C(0x4d0985cb1d3608ae), UINT64_C(0x1e3fa00000000001)}, /* k=-35 */
    {UINT64_C(0x7b426fab61f00de3), UINT64_C(0x6399000000000001)}, /* k=-34 */
    {UINT64_C(0x629b8c891b267182), UINT64_C(0xb614000000000001)}, /* k=-33 */
    {UINT64_C(0x4ee2d6d415b85ace), UINT64_C(0xf810000000000001)}, /* k=-32 */
    {UINT64_C(0x7e37be2022c0914b), UINT64_C(0x2680000000000001)}, /* k=-31 */
    {UINT64_C(0x64f964e68233a76f), UINT64_C(0x5200000000000001)}, /* k=-30 */
    {UINT64_C(0x50c783eb9b5c85f2), UINT64_C(0xa800000000000001)}, /* k=-29 */
    {UINT64_C(0x409f9cbc7c4a04c2), UINT64_C(0x2000000000000001)}, /* k=-28 */
    {UINT64_C(0x6765c793fa10079d), UINT64_C(0x0000000000000001)}, /* k=-27 */
    {UINT64_C(0x52b7d2dcc80cd2e4), UINT64_C(0x0000000000000001)}, /* k=-26 */
    {UINT64_C(0x422ca8b0a00a4250), UINT64_C(0x0000000000000001)}, /* k=-25 */
    {UINT64_C(0x69e10de76676d080), UINT64_C(0x0000000000000001)}, /* k=-24 */
    {UINT64_C(0x54b40b1f852bda00), UINT64_C(0x0000000000000001)}, /* k=-23 */
    {UINT64_C(0x43c33c1937564800), UINT64_C(0x0000000000000001)}, /* k=-22 */
    {UINT64_C(0x6c6b935b8bbd4000), UINT64_C(0x0000000000000001)}, /* k=-21 */
    {UINT64_C(0x56bc75e2d6310000), UINT64_C(0x0000000000000001)}, /* k=-20 */
    {UINT64_C(0x4563918244f40000), UINT64_C(0x0000000000000001)}, /* k=-19 */
    {UINT64_C(0x6f05b59d3b200000), UINT64_C(0x0000000000000001)}, /* k=-18 */
    {UINT64_C(0x58d15e1762800000), UINT64_C(0x0000000000000001)}, /* k=-17 */
    {UINT64_C(0x470de4df82000000), UINT64_C(0x0000000000000001)}, /* k=-16 */
    {UINT64_C(0x71afd498d0000000), UINT64_C(0x0000000000000001)}, /* k=-15 */
    {UINT64_C(0x5af3107a40000000), UINT64_C(0x0000000000000001)}, /* k=-14 */
    {UINT64_C(0x48c2739500000000), UINT64_C(0x0000000000000001)}, /* k=-13 */
    {UINT64_C(0x746a528800000000), UINT64_C(0x0000000000000001)}, /* k=-12 */
    {UINT64_C(0x5d21dba000000000), UINT64_C(0x0000000000000001)}, /* k=-11 */
    {UINT64_C(0x4a817c8000000000), UINT64_C(0x0000000000000001)}, /* k=-10 */
    {UINT64_C(0x7735940000000000), UINT64_C(0x0000000000000001)}, /* k=-9 */
    {UINT64_C(0x5f5e100000000000), UINT64_C(0x0000000000000001)}, /* k=-8 */
    {UINT64_C(0x4c4b400000000000), UINT64_C(0x0000000000000001)}, /* k=-7 */
    {UINT64_C(0x7a12000000000000), UINT64_C(0x0000000000000001)}, /* k=-6 */
    {UINT64_C(0x61a8000000000000), UINT64_C(0x0000000000000001)}, /* k=-5 */
    {UINT64_C(0x4e20000000000000), UINT64_C(0x0000000000000001)}, /* k=-4 */
    {UINT64_C(0x7d00000000000000), UINT64_C(0x0000000000000001)}, /* k=-3 */
    {UINT64_C(0x6400000000000000), UINT64_C(0x0000000000000001)}, /* k=-2 */
    {UINT64_C(0x5000000000000000), UINT64_C(0x0000000000000001)}, /* k=-1 */
    {UINT64_C(0x4000000000000000), UINT64_C(0x0000000000000001)}, /* k=0 */
    {UINT64_C(0x6666666666666666), UINT64_C(0x6666666666666667)}, /* k=1 */
    {UINT64_C(0x51eb851eb851eb85), UINT64_C(0x1eb851eb851eb852)}, /* k=2 */
    {UINT64_C(0x4189374bc6a7ef9d), UINT64_C(0xb22d0e5604189375)}, /* k=3 */
    {UINT64_C(0x68db8bac710cb295), UINT64_C(0xe9e1b089a0275255)}, /* k=4 */
    {UINT64_C(0x53e2d6238da3c211), UINT64_C(0x87e7c06e19b90eaa)}, /* k=5 */
    {UINT64_C(0x431bde82d7b634da), UINT64_C(0xd31fcd24e160d888)}, /* k=6 */
    {UINT64_C(0x6b5fca6af2bd215e), UINT64_C(0x1e99483b02348da7)}, /* k=7 */
    {UINT64_C(0x55e63b88c230e77e), UINT64_C(0x7ee106959b5d3e1f)}, /* k=8 */
    {UINT64_C(0x44b82fa09b5a52cb), UINT64_C(0x98b405447c4a9819)}, /* k=9 */
    {UINT64_C(0x6df37f675ef6eadf), UINT64_C(0x5ab9a2072d44268e)}, /* k=10 */
    {UINT64_C(0x57f5ff85e592557f), UINT64_C(0x7bc7b4d28a9ceba5)}, /* k=11 */
    {UINT64_C(0x465e6604b7a84465), UINT64_C(0xfc9fc3dba21722ea)}, /* k=12 */
    {UINT64_C(0x709709a125da0709), UINT64_C(0x9432d2f9035837dd)}, /* k=13 */
    {UINT64_C(0x5a126e1a84ae6c07), UINT64_C(0xa9c24260cf79c64b)}, /* k=14 */
    {UINT64_C(0x480ebe7b9d58566c), UINT64_C(0x87ce9b80a5fb0509)}, /* k=15 */
    {UINT64_C(0x734aca5f6226f0ad), UINT64_C(0xa6175f343cc4d4da)}, /* k=16 */
    {UINT64_C(0x5c3bd5191b525a24), UINT64_C(0x84df7f5cfd6a43e2)}, /* k=17 */
    {UINT64_C(0x49c97747490eae83), UINT64_C(0x9d7f99173121cfe8)}, /* k=18 */
    {UINT64_C(0x760f253edb4ab0d2), UINT64_C(0x9598f4f1e8361973)}, /* k=19 */
    {UINT64_C(0x5e72843249088d75), UINT64_C(0x447a5d8e535e7ac3)}, /* k=20 */
    {UINT64_C(0x4b8ed0283a6d3df7), UINT64_C(0x69fb7e0b75e52f02)}, /* k=21 */
    {UINT64_C(0x78e480405d7b9658), UINT64_C(0xa9926345896eb19d)}, /* k=22 */
    {UINT64_C(0x60b6cd004ac94513), UINT64_C(0xbadb829e078bc14a)}, /* k=23 */
    {UINT64_C(0x4d5f0a66a23a9da9), UINT64_C(0x6249354b393c9aa2)}, /* k=24 */
    {UINT64_C(0x7bcb43d769f762a8), UINT64_C(0x9d41eedec1fa9103)}, /* k=25 */
    {UINT64_C(0x63090312bb2c4eed), UINT64_C(0x4a9b257f019540cf)}, /* k=26 */
    {UINT64_C(0x4f3a68dbc8f03f24), UINT64_C(0x3baf513267aa9a3f)}, /* k=27 */
    {UINT64_C(0x7ec3daf941806506), UINT64_C(0xc5e54eb70c4429ff)}, /* k=28 */
    {UINT64_C(0x65697bfa9acd1d9f), UINT64_C(0x04b7722c09d02199)}, /* k=29 */
    {UINT64_C(0x51212ffbaf0a7e18), UINT64_C(0xd092c1bcd4a68147)}, /* k=30 */
    {UINT64_C(0x40e7599625a1fe7a), UINT64_C(0x407567ca43b8676c)}, /* k=31 */
    {UINT64_C(0x67d88f56a29cca5d), UINT64_C(0x33ef0c76d2c0a57a)}, /* k=32 */
    {UINT64_C(0x5313a5dee87d6eb0), UINT64_C(0xf658d6c57566eac8)}, /* k=33 */
    {UINT64_C(0x42761e4bed31255a), UINT64_C(0x5ead789df78588a0)}, /* k=34 */
    {UINT64_C(0x6a5696dfe1e83bc3), UINT64_C(0xcaaf276325a27433)}, /* k=35 */
    {UINT64_C(0x5512124cb4b9c969), UINT64_C(0x6ef285e8eae85cf5)}, /* k=36 */
    {UINT64_C(0x440e750a2a2e3aba), UINT64_C(0xbf286b20bbed172b)}, /* k=37 */
    {UINT64_C(0x6ce3ee76a9e3912a), UINT64_C(0xcb73de9ac6482511)}, /* k=38 */
    {UINT64_C(0x571cbec554b60dbb), UINT64_C(0xd5f64baf0506840e)}, /* k=39 */
    {UINT64_C(0x45b0989ddd5e7163), UINT64_C(0x1191d6259d9ed00b)}, /* k=40 */
    {UINT64_C(0x6f80f42fc8971bd1), UINT64_C(0xb5b6236f6297b345)}, /* k=41 */
    {UINT64_C(0x5933f68ca078e30e), UINT64_C(0x2af81c591bac8f6a)}, /* k=42 */
    {UINT64_C(0x475cc53d4d2d8271), UINT64_C(0xbbf9b0474956d922)}, /* k=43 */
    {UINT64_C(0x722e086215159d82), UINT64_C(0xc65c4d3edbbe2836)}, /* k=44 */
    {UINT64_C(0x5b5806b4ddaae468), UINT64_C(0x9eb03dcbe2fe8692)}, /* k=45 */
    {UINT64_C(0x49133890b1558386), UINT64_C(0xe559cb0982653875)}, /* k=46 */
    {UINT64_C(0x74eb8db44eef38d7), UINT64_C(0xd55c780f37085a54)}, /* k=47 */
    {UINT64_C(0x5d893e29d8bf60ac), UINT64_C(0xaab0600c2c06aeaa)}, /* k=48 */
    {UINT64_C(0x4ad431bb13cc4d56), UINT64_C(0xeef38009bcd22555)}, /* k=49 */
    {UINT64_C(0x77b9e92b52e07bbe), UINT64_C(0x4b1f3342c7b6a221)}, /* k=50 */
    {UINT64_C(0x5fc7edbc424d2fcb), UINT64_C(0x6f4c2902395ee81a)}, /* k=51 */
    {UINT64_C(0x4c9ff163683dbfd5), UINT64_C(0xf2a35401c77f2015)}, /* k=52 */
    {UINT64_C(0x7a998238a6c932ef), UINT64_C(0xea9eeccfa5983355)}, /* k=53 */
    {UINT64_C(0x6214682d523a8f26), UINT64_C(0x554bf0a61e135c44)}, /* k=54 */
    {UINT64_C(0x4e76b9bddb620c1e), UINT64_C(0xaaa326eb4b42b036)}, /* k=55 */
    {UINT64_C(0x7d8ac2c95f034697), UINT64_C(0x776b7178786ab38a)}, /* k=56 */
    {UINT64_C(0x646f023ab2690545), UINT64_C(0xf922c12d2d22293b)}, /* k=57 */
    {UINT64_C(0x5058ce955b87376b), UINT64_C(0x2db56757574e8763)}, /* k=58 */
    {UINT64_C(0x40470baaaf9f5f88), UINT64_C(0xf15dec45df7205e9)}, /* k=59 */
    {UINT64_C(0x66d812aab29898db), UINT64_C(0x1bc97a0965833ca7)}, /* k=60 */
    {UINT64_C(0x524675555bad4715), UINT64_C(0xafd461a11e0296ec)}, /* k=61 */
    {UINT64_C(0x41d1f7777c8a9f44), UINT64_C(0x8ca9e7b418021257)}, /* k=62 */
    {UINT64_C(0x694ff258c7443207), UINT64_C(0x47763f868cd01d57)}, /* k=63 */
    {UINT64_C(0x543ff513d29cf4d2), UINT64_C(0x9f91cc6ba3d9b113)}, /* k=64 */
    {UINT64_C(0x43665da9754a5d75), UINT64_C(0x4c74a3894fe15a75)}, /* k=65 */
    {UINT64_C(0x6bd6fc425543c8bb), UINT64_C(0xad876c0ee6355d88)}, /* k=66 */
    {UINT64_C(0x5645969b77696d62), UINT64_C(0xf139233f1e9117a0)}, /* k=67 */
    {UINT64_C(0x4504787c5f878ab5), UINT64_C(0x8dc74f65b20dac80)}, /* k=68 */
    {UINT64_C(0x6e6d8d93cc0c1122), UINT64_C(0x7c7218a2b67c4733)}, /* k=69 */
    {UINT64_C(0x5857a4763cd6741b), UINT64_C(0x96c1ad4ef8636c29)}, /* k=70 */
    {UINT64_C(0x46ac8391ca4529af), UINT64_C(0xabce243f2d1c5688)}, /* k=71 */
    {UINT64_C(0x711405b6106ea919), UINT64_C(0x12e36d31e1c6f0d9)}, /* k=72 */
    {UINT64_C(0x5a766af80d255414), UINT64_C(0x0f1c575b1b058d7a)}, /* k=73 */
    {UINT64_C(0x485ebbf9a41ddcdc), UINT64_C(0xd8e37915af37a462)}, /* k=74 */
    {UINT64_C(0x73cac65c39c96161), UINT64_C(0x5b058e8918590703)}, /* k=75 */
    {UINT64_C(0x5ca23849c7d44de7), UINT64_C(0x7c04720746ad9f35)}, /* k=76 */
    {UINT64_C(0x4a1b603b06437185), UINT64_C(0xfcd05b390557b291)}, /* k=77 */
    {UINT64_C(0x76923391a39f1c09), UINT64_C(0x948091f4d5591db5)}, /* k=78 */
    {UINT64_C(0x5edb5c7482e5b007), UINT64_C(0xaa0074c3dde0e491)}, /* k=79 */
    {UINT64_C(0x4be2b05d35848cd2), UINT64_C(0xee66c3cfe4b3ea0e)}, /* k=80 */
    {UINT64_C(0x796ab3c855a0e151), UINT64_C(0x7d71394ca11fdce2)}, /* k=81 */
    {UINT64_C(0x6122296d114d810d), UINT64_C(0xfdf42dd6e74cb0b5)}, /* k=82 */
    {UINT64_C(0x4db4edf0daa4673e), UINT64_C(0x64c357df1f708d5e)}, /* k=83 */
    {UINT64_C(0x7c54afe7c43a3eca), UINT64_C(0x3ad22631cbe74896)}, /* k=84 */
    {UINT64_C(0x6376f31fd02e98a1), UINT64_C(0xc8a81e8e3cb906de)}, /* k=85 */
    {UINT64_C(0x4f925c1973587a1b), UINT64_C(0x06ece53e96fa6be5)}, /* k=86 */
    {UINT64_C(0x7f50935bebc0c35e), UINT64_C(0x717b086424c3dfd5)}, /* k=87 */
    {UINT64_C(0x65da0f7cbc9a35e5), UINT64_C(0x2795a0501d697fdd)}, /* k=88 */
    {UINT64_C(0x517b3f96fd482b1d), UINT64_C(0xb94480401787997e)}, /* k=89 */
    {UINT64_C(0x412f66126439bc17), UINT64_C(0xc76a003346061465)}, /* k=90 */
    {UINT64_C(0x684bd683d38f9359), UINT64_C(0x3f10005209a353d4)}, /* k=91 */
    {UINT64_C(0x536fdecfdc72dc47), UINT64_C(0x65a666a807b5dcaa)}, /* k=92 */
    {UINT64_C(0x42bfe57316c249d2), UINT64_C(0xb7b85220062b16ee)}, /* k=93 */
    {UINT64_C(0x6acca251be03a951), UINT64_C(0x25f3b699a37824b0)}, /* k=94 */
    {UINT64_C(0x557081dafe695440), UINT64_C(0xeb295ee14f93508d)}, /* k=95 */
    {UINT64_C(0x445a017bfebaa9cd), UINT64_C(0x88ede5810c75da0b)}, /* k=96 */
    {UINT64_C(0x6d5ccf2ccac442e2), UINT64_C(0x74afd59b4722f677)}, /* k=97 */
    {UINT64_C(0x577d728a3bd03581), UINT64_C(0xf6f3114905b591f9)}, /* k=98 */
    {UINT64_C(0x45fdf53b630cf79b), UINT64_C(0x2bf5a76d9e2adb2e)}, /* k=99 */
    {UINT64_C(0x6ffcbb923814bf5e), UINT64_C(0xacbc3f15c9de2b7c)}, /* k=100 */
    {UINT64_C(0x5996fc74f9aa32b2), UINT64_C(0x23c9cc116e4b55fd)}, /* k=101 */
    {UINT64_C(0x47abfd2a6154f55b), UINT64_C(0x4fd4a34125091197)}, /* k=102 */
    {UINT64_C(0x72acc843ceee555e), UINT64_C(0xe6210535080e828b)}, /* k=103 */
    {UINT64_C(0x5bbd6d030bf1dde5), UINT64_C(0x84e7375da00b9ba3)}, /* k=104 */
    {UINT64_C(0x49645735a327e4b7), UINT64_C(0x9d85c5e48009494f)}, /* k=105 */
    {UINT64_C(0x756d5855d1d96df2), UINT64_C(0x95a2d63a66754218)}, /* k=106 */
    {UINT64_C(0x5df11377db1457f5), UINT64_C(0x448244fb852a9b46)}, /* k=107 */
    {UINT64_C(0x4b2742c648dd132a), UINT64_C(0x9d3503fc6a887c38)}, /* k=108 */
    {UINT64_C(0x783ed13d4161b844), UINT64_C(0x2ebb3993dda72d27)}, /* k=109 */
    {UINT64_C(0x603240fdcde7c69c), UINT64_C(0xf22f614317b8f0ec)}, /* k=110 */
    {UINT64_C(0x4cf500cb0b1fd217), UINT64_C(0x2825e768dfc72723)}, /* k=111 */
    {UINT64_C(0x7b219ade7832e9be), UINT64_C(0xa6a30bdaffa50b6b)}, /* k=112 */
    {UINT64_C(0x628148b1f9c25498), UINT64_C(0x854f3caf32ea6f89)}, /* k=113 */
    {UINT64_C(0x4ecdd3c1949b76e0), UINT64_C(0x6aa5ca25c2552607)}, /* k=114 */
    {UINT64_C(0x7e161f9c20f8be33), UINT64_C(0xddd6103c6a21d672)}, /* k=115 */
    {UINT64_C(0x64de7fb01a609829), UINT64_C(0x7e44d9c9ee81785b)}, /* k=116 */
    {UINT64_C(0x50b1ffc0151a1354), UINT64_C(0x6503e16e5867937c)}, /* k=117 */
    {UINT64_C(0x408e66334414dc43), UINT64_C(0x84031abead1fa930)}, /* k=118 */
    {UINT64_C(0x674a3d1ed354939f), UINT64_C(0x399e913114ff751a)}, /* k=119 */
    {UINT64_C(0x52a1ca7f0f76dc7f), UINT64_C(0x614ba75a7732c415)}, /* k=120 */
    {UINT64_C(0x421b0865a5f8b065), UINT64_C(0xe76fb9152c289cde)}, /* k=121 */
    {UINT64_C(0x69c4da3c3cc11a3c), UINT64_C(0xa57f8e8846a76162)}, /* k=122 */
    {UINT64_C(0x549d7b6363cdae96), UINT64_C(0xeacc72069eec4de8)}, /* k=123 */
    {UINT64_C(0x43b12f82b63e2545), UINT64_C(0x88a38e6bb256a4ba)}, /* k=124 */
    {UINT64_C(0x6c4eb26abd303ba2), UINT64_C(0x7438e3df83bdd45c)}, /* k=125 */
    {UINT64_C(0x56a55b889759c94e), UINT64_C(0xc360b64c6964a9e4)}, /* k=126 */
    {UINT64_C(0x45511606df7b0772), UINT64_C(0x35e6f83d211d54b6)}, /* k=127 */
    {UINT64_C(0x6ee8233e325e7250), UINT64_C(0x563e59fb682eedf0)}, /* k=128 */
    {UINT64_C(0x58b9b5cb5b7ec1d9), UINT64_C(0xde9847fc5358be5a)}, /* k=129 */
    {UINT64_C(0x46faf7d5e2cbce47), UINT64_C(0xe5469ffd0f7a31e1)}, /* k=130 */
    {UINT64_C(0x71918c896adfb073), UINT64_C(0x0870fffb4bf6b635)}, /* k=131 */
    {UINT64_C(0x5adad6d4557fc05c), UINT64_C(0x06c0ccc909922b5e)}, /* k=132 */
    {UINT64_C(0x48af1243779966b0), UINT64_C(0x05670a3a6e0e8918)}, /* k=133 */
    {UINT64_C(0x744b506bf28f0ab3), UINT64_C(0x3bd8105d7ce40e8c)}, /* k=134 */
    {UINT64_C(0x5d090d2328726ef5), UINT64_C(0xc979a6b130b6720a)}, /* k=135 */
    {UINT64_C(0x4a6da41c205b8bf7), UINT64_C(0xd46152275a2b8e6f)}, /* k=136 */
    {UINT64_C(0x7715d36033c5acbf), UINT64_C(0xba35503ef6ac1717)}, /* k=137 */
    {UINT64_C(0x5f44a919c3048a32), UINT64_C(0xfb5dd9cbf889ac12)}, /* k=138 */
    {UINT64_C(0x4c36edae359d3b5b), UINT64_C(0xfc4b14a32d3af00f)}, /* k=139 */
    {UINT64_C(0x79f17c49ef61f893), UINT64_C(0x2d44edd1e1f7e67e)}, /* k=140 */
    {UINT64_C(0x618dfd07f2b4c6dc), UINT64_C(0x243724a7e7f98532)}, /* k=141 */
    {UINT64_C(0x4e0b30d328909f16), UINT64_C(0x835f5086532e0428)}, /* k=142 */
    {UINT64_C(0x7cdeb4850db431bd), UINT64_C(0x9efee73d51e339d9)}, /* k=143 */
    {UINT64_C(0x63e55d373e29c164), UINT64_C(0x7f32529774b5c7e1)}, /* k=144 */
    {UINT64_C(0x4feab0f8fe87cde9), UINT64_C(0xff5b7545f6f7d31a)}, /* k=145 */
    {UINT64_C(0x7fdde7f4ca72e30f), UINT64_C(0xfef8bba324bfb82a)}, /* k=146 */
    {UINT64_C(0x664b1ff7085be8d9), UINT64_C(0x98c6fc8283cc9355)}, /* k=147 */
    {UINT64_C(0x51d5b32c06afed7a), UINT64_C(0xe09f3068697075de)}, /* k=148 */
    {UINT64_C(0x4177c2899ef32462), UINT64_C(0x4d4c26b9edf3917e)}, /* k=149 */
    {UINT64_C(0x68bf9da8fe51d3d0), UINT64_C(0x7bad0ac316528263)}, /* k=150 */
    {UINT64_C(0x53cc7e20cb74a973), UINT64_C(0x9624089c11db9b83)}, /* k=151 */
    {UINT64_C(0x4309fe80a2c3bac2), UINT64_C(0xde833a1674afaf9c)}, /* k=152 */
    {UINT64_C(0x6b4330cdd1392ad1), UINT64_C(0x640529bd877f7f5f)}, /* k=153 */
    {UINT64_C(0x55cf5a3e40fa88a7), UINT64_C(0x833754979f9932b3)}, /* k=154 */
    {UINT64_C(0x44a5e1cb672ed3b9), UINT64_C(0x35c5dd4619475bc2)}, /* k=155 */
    {UINT64_C(0x6dd636123eb152c1), UINT64_C(0xefa2fba35ba55f9d)}, /* k=156 */
    {UINT64_C(0x57de91a832277567), UINT64_C(0xf2e8c94f7c844c7e)}, /* k=157 */
    {UINT64_C(0x464ba7b9c1b92ab9), UINT64_C(0x8f20a10c639d09fe)}, /* k=158 */
    {UINT64_C(0x70790c5c6928445c), UINT64_C(0x183434e09f61a997)}, /* k=159 */
    {UINT64_C(0x59fa7049edb9d049), UINT64_C(0xacf690b3b2b487ac)}, /* k=160 */
    {UINT64_C(0x47fb8d07f161736e), UINT64_C(0x23f873c2f55d3956)}, /* k=161 */
    {UINT64_C(0x732c14d98235857d), UINT64_C(0x065a52d18895288a)}, /* k=162 */
    {UINT64_C(0x5c2343e134f79dfd), UINT64_C(0x9eaea8a7a07753a2)}, /* k=163 */
    {UINT64_C(0x49b5cfe75d92e4ca), UINT64_C(0xe55886ec805f761b)}, /* k=164 */
    {UINT64_C(0x75efb30bc8eb07ab), UINT64_C(0x088da4ad9a325691)}, /* k=165 */
    {UINT64_C(0x5e595c096d88d2ef), UINT64_C(0x3a0aea247b5b7874)}, /* k=166 */
    {UINT64_C(0x4b7ab0078ad3dbf2), UINT64_C(0x94d5881d2f7c605d)}, /* k=167 */
    {UINT64_C(0x78c44cd8de1fc650), UINT64_C(0xee227361e593cd61)}, /* k=168 */
    {UINT64_C(0x609d0a4718196b73), UINT64_C(0xf1b5291b1e0fd781)}, /* k=169 */
    {UINT64_C(0x4d4a6e9f467abc5c), UINT64_C(0xc15dba7c180cac68)}, /* k=170 */
    {UINT64_C(0x7baa4a9870c46094), UINT64_C(0x6895f72cf3477a3f)}, /* k=171 */
    {UINT64_C(0x62eea2138d69e6dd), UINT64_C(0x2077f8f0c29f94ff)}, /* k=172 */
    {UINT64_C(0x4f254e760abb1f17), UINT64_C(0x4d2cc72702194400)}, /* k=173 */
    {UINT64_C(0x7ea21723445e9825), UINT64_C(0x4847a50b368ed332)}, /* k=174 */
    {UINT64_C(0x654e78e9037ee01d), UINT64_C(0xd36c8408f872428f)}, /* k=175 */
    {UINT64_C(0x510b93ed9c658017), UINT64_C(0xdc56d0072d28353f)}, /* k=176 */
    {UINT64_C(0x40d60ff149eaccdf), UINT64_C(0xe378a66c24202a99)}, /* k=177 */
    {UINT64_C(0x67bce64edcaae166), UINT64_C(0x38c10a46a033775b)}, /* k=178 */
    {UINT64_C(0x52fd850be3bbe784), UINT64_C(0xfa34083880292c49)}, /* k=179 */
    {UINT64_C(0x42646a6fe9631f9d), UINT64_C(0x94f66cfa0020f03a)}, /* k=180 */
    {UINT64_C(0x6a3a43e642383295), UINT64_C(0xbb23e1900034b390)}, /* k=181 */
    {UINT64_C(0x54fb698501c68ede), UINT64_C(0x2f4fe7a666908fa7)}, /* k=182 */
    {UINT64_C(0x43fc546a67d20be4), UINT64_C(0xf2a652eb854072ec)}, /* k=183 */
    {UINT64_C(0x6cc6ed770c83463b), UINT64_C(0x1dd6eb126ecd84ac)}, /* k=184 */
    {UINT64_C(0x57058ac5a39c382f), UINT64_C(0x4b1255a858a46a23)}, /* k=185 */
    {UINT64_C(0x459e089e1c7cf9bf), UINT64_C(0x6f41de2046e9ee83)}, /* k=186 */
    {UINT64_C(0x6f6340fcfa618f98), UINT64_C(0xb202fd0071764a6b)}, /* k=187 */
    {UINT64_C(0x591c33fd951ad946), UINT64_C(0xf4cf30cd2791d522)}, /* k=188 */
    {UINT64_C(0x4749c33144157a9f), UINT64_C(0x2a3f5a3db941774f)}, /* k=189 */
    {UINT64_C(0x720f9eb539bbf765), UINT64_C(0x10655d2f8ecf254a)}, /* k=190 */
    {UINT64_C(0x5b3fb22a94965f84), UINT64_C(0x0d1de4260bd8eaa2)}, /* k=191 */
    {UINT64_C(0x48ffc1bbaa11e603), UINT64_C(0x3db18351a313eee8)}, /* k=192 */
    {UINT64_C(0x74cc692c434fd66b), UINT64_C(0x95e8d21c381fe4a6)}, /* k=193 */
    {UINT64_C(0x5d705423690cab89), UINT64_C(0x44ba41b02ce65085)}, /* k=194 */
    {UINT64_C(0x4ac0434f873d5607), UINT64_C(0x6a2e9af3571ea6d1)}, /* k=195 */
    {UINT64_C(0x779a054c0b955672), UINT64_C(0x437dc4b88b643e1b)}, /* k=196 */
    {UINT64_C(0x5fae6aa33c77785b), UINT64_C(0x69316a2d3c5031af)}, /* k=197 */
    {UINT64_C(0x4c8b888296c5f9e2), UINT64_C(0xba8dee8a96a68e26)}, /* k=198 */
    {UINT64_C(0x7a78da6a8ad65c9d), UINT64_C(0xf7497daa8aa416a3)}, /* k=199 */
    {UINT64_C(0x61fa48553bdeb07e), UINT64_C(0x5f6dfe220883454f)}, /* k=200 */
    {UINT64_C(0x4e61d37763188d31), UINT64_C(0xe5f1981b3a029dd9)}, /* k=201 */
    {UINT64_C(0x7d6952589e8daeb6), UINT64_C(0x3cb5c02b90042fc1)}, /* k=202 */
    {UINT64_C(0x645441e07ed7bef8), UINT64_C(0x3091668940035967)}, /* k=203 */
    {UINT64_C(0x504367e6cbdfcbf9), UINT64_C(0xc074520766691453)}, /* k=204 */
    {UINT64_C(0x4035ecb8a3196ffb), UINT64_C(0x005d0e6c51eda9dc)}, /* k=205 */
    {UINT64_C(0x66bcadf43828b32b), UINT64_C(0x33c81713b6490fc6)}, /* k=206 */
    {UINT64_C(0x52308b29c686f5bc), UINT64_C(0x296cdf42f83a7305)}, /* k=207 */
    {UINT64_C(0x41c06f549ed25e30), UINT64_C(0x2123e5cf2cfb8f37)}, /* k=208 */
    {UINT64_C(0x6933e554315096b3), UINT64_C(0x68396fb1e1927ebe)}, /* k=209 */
    {UINT64_C(0x542984435aa6def5), UINT64_C(0xecfabfc18141feff)}, /* k=210 */
    {UINT64_C(0x435469cf7bb8b25e), UINT64_C(0x572effce010198cc)}, /* k=211 */
    {UINT64_C(0x6bba42e592c11d63), UINT64_C(0xbeb199499b35c146)}, /* k=212 */
    {UINT64_C(0x562e9beadbcdb11c), UINT64_C(0x988e143ae291676b)}, /* k=213 */
    {UINT64_C(0x44f216557ca48db0), UINT64_C(0x7a0b43624edab923)}, /* k=214 */
    {UINT64_C(0x6e5023bbfaa0e2b3), UINT64_C(0xf6786bd07e2ac1d1)}, /* k=215 */
    {UINT64_C(0x58401c96621a4ef6), UINT64_C(0x5ec6bca6cb5567da)}, /* k=216 */
    {UINT64_C(0x4699b0784e7b725e), UINT64_C(0xb23896ebd5ddecaf)}, /* k=217 */
    {UINT64_C(0x70f5e726e3f8b6fd), UINT64_C(0xe9f424ac8963144b)}, /* k=218 */
    {UINT64_C(0x5a5e5285832d5f31), UINT64_C(0x87f683bd3ab5a9d5)}, /* k=219 */
    {UINT64_C(0x484b75379c244c27), UINT64_C(0x9ff869642ef7bb11)}, /* k=220 */
    {UINT64_C(0x73abeebf603a1372), UINT64_C(0x998d756d17f2c4e8)}, /* k=221 */
    {UINT64_C(0x5c898bcc4cfb42c2), UINT64_C(0x14712abdacc23720)}, /* k=222 */
    {UINT64_C(0x4a07a309d72f689b), UINT64_C(0x438dbbcaf09b5f4d)}, /* k=223 */
    {UINT64_C(0x76729e762518a75e), UINT64_C(0xd27c5fab1a923215)}, /* k=224 */
    {UINT64_C(0x5ec2185e8413b918), UINT64_C(0xa8637fbc1541c1aa)}, /* k=225 */
    {UINT64_C(0x4bce79e536762dad), UINT64_C(0x5382cc967767ce22)}, /* k=226 */
    {UINT64_C(0x794a5ca1f0bd15e2), UINT64_C(0x1f37adbd8bd949cf)}, /* k=227 */
    {UINT64_C(0x61084a1b26fdab1b), UINT64_C(0x4c2c8afe097aa173)}, /* k=228 */
    {UINT64_C(0x4da03b48ebfe227c), UINT64_C(0x3cf06f31a12ee78f)}, /* k=229 */
    {UINT64_C(0x7c33920e46636a60), UINT64_C(0x6180b1e901e4a5b2)}, /* k=230 */
    {UINT64_C(0x635c74d8384f884d), UINT64_C(0x1acd5b20ce50848e)}, /* k=231 */
    {UINT64_C(0x4f7d2a469372d370), UINT64_C(0xe23de280a50d36d8)}, /* k=232 */
    {UINT64_C(0x7f2eaa0a85848581), UINT64_C(0x69fc9d9aa1aebe27)}, /* k=233 */
    {UINT64_C(0x65beee6ed136d134), UINT64_C(0x54ca17aee7befe85)}, /* k=234 */
    {UINT64_C(0x51658b8bda9240f6), UINT64_C(0xaa3b462586326538)}, /* k=235 */
    {UINT64_C(0x411e093caedb672b), UINT64_C(0xbb629e846b5b842d)}, /* k=236 */
    {UINT64_C(0x68300ec77e2bd845), UINT64_C(0xf89dca6d78926d14)}, /* k=237 */
    {UINT64_C(0x5359a56c64efe037), UINT64_C(0xfa17d52460752410)}, /* k=238 */
    {UINT64_C(0x42ae1df050bfe693), UINT64_C(0x2e7977504d2a8340)}, /* k=239 */
    {UINT64_C(0x6ab02fe6e79970eb), UINT64_C(0x7d8f254d48440533)}, /* k=240 */
    {UINT64_C(0x5559bfebec7ac0bc), UINT64_C(0x6472843dd3699dc2)}, /* k=241 */
    {UINT64_C(0x4447ccbcbd2f0096), UINT64_C(0xb6c20364a9214b02)}, /* k=242 */
    {UINT64_C(0x6d3fadfac84b3424), UINT64_C(0x579cd23aa83544d0)}, /* k=243 */
    {UINT64_C(0x576624c8a03c29b6), UINT64_C(0xac7d74fbb9c4370d)}, /* k=244 */
    {UINT64_C(0x45eb50a08030215e), UINT64_C(0xf0645d962e369271)}, /* k=245 */
    {UINT64_C(0x6fdee76733803564), UINT64_C(0xb3d3c8f049f0ea4e)}, /* k=246 */
    {UINT64_C(0x597f1f85c2ccf783), UINT64_C(0xc30fd3f36e5a550b)}, /* k=247 */
    {UINT64_C(0x4798e6049bd72c69), UINT64_C(0x68d9765c58484409)}, /* k=248 */
    {UINT64_C(0x728e3cd42c8b7a42), UINT64_C(0x415bf093c073a00e)}, /* k=249 */
    {UINT64_C(0x5ba4fd768a092e9b), UINT64_C(0x677cc076338fb33e)}, /* k=250 */
    {UINT64_C(0x4950cac53b3a8baf), UINT64_C(0x85fd66c4f60c8f65)}, /* k=251 */
    {UINT64_C(0x754e113b91f745e5), UINT64_C(0xa32f0ad4bce0e56f)}, /* k=252 */
    {UINT64_C(0x5dd80dc941929e51), UINT64_C(0x4f58d576fd80b78c)}, /* k=253 */
    {UINT64_C(0x4b133e3a9adbb1da), UINT64_C(0xa5e0aac5979a2c70)}, /* k=254 */
    {UINT64_C(0x781ec9f75e2c4fc4), UINT64_C(0x3c9aaad5bf5d13e6)}, /* k=255 */
    {UINT64_C(0x6018a192b1bd0c9c), UINT64_C(0xfd4888aaff7da985)}, /* k=256 */
    {UINT64_C(0x4ce0814227ca707d), UINT64_C(0x976d3a2265fe2137)}, /* k=257 */
    {UINT64_C(0x7b00ced03faa4d95), UINT64_C(0xbf1529d0a3303525)}, /* k=258 */
    {UINT64_C(0x62670bd9cc883e11), UINT64_C(0x65aa87da1c2690ea)}, /* k=259 */
    {UINT64_C(0x4eb8d647d6d364da), UINT64_C(0xb7bb9fe1b01eda55)}, /* k=260 */
    {UINT64_C(0x7df48a0c8aebd491), UINT64_C(0x25f8ffcf80315d55)}, /* k=261 */
    {UINT64_C(0x64c3a1a3a25643a7), UINT64_C(0x5193ffd9335ab111)}, /* k=262 */
    {UINT64_C(0x509c814fb511cfb9), UINT64_C(0x0e0fffe0f5e22741)}, /* k=263 */
    {UINT64_C(0x407d343fc40e3fc7), UINT64_C(0x3e73331a5e4e85cd)}, /* k=264 */
    {UINT64_C(0x672eb9ffa016cc71), UINT64_C(0xfd851e9096e40948)}, /* k=265 */
    {UINT64_C(0x528bc7ffb345705b), UINT64_C(0x31374ba6df1cd43a)}, /* k=266 */
    {UINT64_C(0x42096ccc8f6ac048), UINT64_C(0xf42c3c857f4a4362)}, /* k=267 */
    {UINT64_C(0x69a8ae1418aacd41), UINT64_C(0x86ad2da265439f02)}, /* k=268 */
    {UINT64_C(0x5486f1a9ad557101), UINT64_C(0x388a8ae85102e59c)}, /* k=269 */
    {UINT64_C(0x439f27baf1112734), UINT64_C(0x2d3ba25374025149)}, /* k=270 */
    {UINT64_C(0x6c31d92b1b4ea520), UINT64_C(0x485f6a1f2003b542)}, /* k=271 */
    {UINT64_C(0x568e4755af721db3), UINT64_C(0x6d1921b28002f768)}, /* k=272 */
    {UINT64_C(0x453e9f77bf8e7e29), UINT64_C(0x24141af5333592ba)}, /* k=273 */
    {UINT64_C(0x6eca98bf98e3fd0e), UINT64_C(0xa0202b21eb88eac2)}, /* k=274 */
    {UINT64_C(0x58a213cc7a4ffda5), UINT64_C(0x4ce688e7efa0bbcf)}, /* k=275 */
    {UINT64_C(0x46e80fd6c83ffe1d), UINT64_C(0xd71ed3ecbfb3c972)}, /* k=276 */
    {UINT64_C(0x71734c8ad9fffcfc), UINT64_C(0x8b648647991fa8b7)}, /* k=277 */
    {UINT64_C(0x5ac2a3a247fffd96), UINT64_C(0xd5ea0506141953c6)}, /* k=278 */
    {UINT64_C(0x489bb61b6ccccadf), UINT64_C(0x11880404dce10fd1)}, /* k=279 */
    {UINT64_C(0x742c569247ae1164), UINT64_C(0xe8d9a007c7ce7fb5)}, /* k=280 */
    {UINT64_C(0x5cf04541d2f1a783), UINT64_C(0xed7ae66c9fd8662a)}, /* k=281 */
    {UINT64_C(0x4a59d101758e1f9c), UINT64_C(0xbdfbeb8a1979eb55)}, /* k=282 */
    {UINT64_C(0x76f61b3588e365c7), UINT64_C(0x965fdf435bf64555)}, /* k=283 */
    {UINT64_C(0x5f2b48f7a0b5eb06), UINT64_C(0x11e64c35e32b6aaa)}, /* k=284 */
    {UINT64_C(0x4c22a0c61a2b226b), UINT64_C(0x418509c4b5bc5555)}, /* k=285 */
    {UINT64_C(0x79d1013cf6ab6a45), UINT64_C(0x35a1a93abc608888)}, /* k=286 */
    {UINT64_C(0x617400fd9222bb6a), UINT64_C(0x914e20fbc9e6d3a0)}, /* k=287 */
    {UINT64_C(0x4df6673141b562bb), UINT64_C(0xa771b3fca185761a)}, /* k=288 */
    {UINT64_C(0x7cbd71e869223792), UINT64_C(0xa582b99435a2568f)}, /* k=289 */
    {UINT64_C(0x63cac186ba81c60e), UINT64_C(0xeacefadcf7b5120c)}, /* k=290 */
    {UINT64_C(0x4fd5679efb9b04d8), UINT64_C(0xbbd8c8b0c62a74d7)}, /* k=291 */
    {UINT64_C(0x7fbbd8fe5f5e6e27), UINT64_C(0x92f4744e09dd87be)}, /* k=292 */
};

static const char qjs_digit_pairs[201] = "0001020304050607080910111213141516171819"
                                         "2021222324252627282930313233343536373839"
                                         "4041424344454647484950515253545556575859"
                                         "6061626364656667686970717273747576777879"
                                         "8081828384858687888990919293949596979899";

static inline int qjs_u64_to_digits(char *digits, uint64_t v)
{
    char tmp[24];
    int pos = 24;
    while (v >= 100u) {
        uint64_t q = v / 100u;
        uint32_t r = (uint32_t)(v - q * 100u);
        pos -= 2;
        memcpy(tmp + pos, qjs_digit_pairs + r * 2u, 2);
        v = q;
    }
    if (v >= 10u) {
        pos -= 2;
        memcpy(tmp + pos, qjs_digit_pairs + (uint32_t)v * 2u, 2);
    } else {
        tmp[--pos] = (char)('0' + (uint32_t)v);
    }
    int len = 24 - pos;
    memcpy(digits, tmp + pos, (size_t)len);
    return len;
}

static inline uint64_t qjs_schub_rop(uint64_t g1, uint64_t g0, uint64_t cp)
{
    uint64_t x1 = qjs_umul128_hi(g0, cp);
    uint64_t z0;
    uint64_t z1 = qjs_umul128(g1, cp, &z0);
    z0 += x1;
    z1 += (z0 < x1);
    return (z1 << 1) | (z0 >> 63) | ((z0 & UINT64_C(0x7fffffffffffffff)) != 0u);
}

static int qjs_dtoa_fast_free10(char *buf, double d)
{
    uint64_t bits;
    memcpy(&bits, &d, sizeof(bits));
    uint32_t sign = (uint32_t)(bits >> 63);
    uint32_t b_exp = (uint32_t)((bits >> 52) & 0x7ffu);
    uint64_t mant = bits & ((UINT64_C(1) << 52) - 1u);

    if (unlikely(b_exp == 0x7ffu)) {
        if (mant != 0) {
            memcpy(buf, "NaN", 4);
            return 3;
        }
        if (sign) {
            memcpy(buf, "-Infinity", 10);
            return 9;
        }
        memcpy(buf, "Infinity", 9);
        return 8;
    }
    if (unlikely(b_exp == 0u && mant == 0u)) {
        buf[0] = '0';
        buf[1] = '\0';
        return 1;
    }

    char *q = buf;
    if (sign)
        *q++ = '-';

    /* Exact IEEE-754 integers in [1, 2^53 - 1] */
    if (likely(b_exp >= 1023u && b_exp <= 1075u)) {
        uint64_t c = mant | (UINT64_C(1) << 52);
        uint32_t shift = 1075u - b_exp;
        uint64_t mask = shift ? ((UINT64_C(1) << shift) - 1u) : 0u;
        if ((c & mask) == 0u) {
            int n = qjs_u64_to_digits(q, c >> shift);
            q += n;
            *q = '\0';
            return (int)(q - buf);
        }
    }

    uint64_t c;
    int32_t q_exp, k;
    bool regular;
    if (likely(b_exp != 0u)) {
        c = mant | (UINT64_C(1) << 52);
        q_exp = (int32_t)b_exp - 1075;
        regular = (mant != 0u) || (b_exp == 1u);
    } else {
        c = mant;
        q_exp = -1074;
        regular = true;
    }

    uint64_t out = c & 1u;
    uint64_t cb = c << 2;
    uint64_t cbr = cb + 2u;
    uint64_t cbl;
    if (likely(regular)) {
        cbl = cb - 2u;
        k = qjs_ashr64((int64_t)q_exp * 315653, 20);
    } else {
        cbl = cb - 1u;
        k = qjs_ashr64((int64_t)q_exp * 1262611 - 524031, 22);
    }

    int32_t h = q_exp + qjs_ashr64((int64_t)(-k) * 217706, 16) + 1;
    const QJSSchubPow10 *pow10 = &qjs_schub_pow10[k + 324];
    uint64_t vb = qjs_schub_rop(pow10->g1, pow10->g0, cb << h);
    uint64_t vbl = qjs_schub_rop(pow10->g1, pow10->g0, cbl << h);
    uint64_t vbr = qjs_schub_rop(pow10->g1, pow10->g0, cbr << h);

    uint64_t s = vb >> 2;
    uint64_t sig_dec;
    if (s >= 10u) {
        uint64_t sp10 = s - (s % 10u);
        bool upin = (vbl + out) <= (sp10 << 2);
        bool wpout = ((sp10 + 10u) << 2) + out <= vbr;
        if (upin != wpout) {
            sig_dec = (sp10 / 10u) + (upin ? 0u : 1u);
            k += 1;
            goto format_dec;
        }
    }
    {
        uint64_t u = s;
        bool uin = (vbl + out) <= (u << 2);
        bool wout = ((u + 1u) << 2) + out <= vbr;
        if (uin != wout) {
            sig_dec = u + (uin ? 0u : 1u);
        } else {
            int64_t cmp = (int64_t)vb - (int64_t)((u << 2) + 2u);
            sig_dec = (cmp < 0 || (cmp == 0 && (u & 1u) == 0u)) ? u : (u + 1u);
        }
    }

format_dec:
    while (sig_dec >= 100u && (sig_dec % 100u) == 0u) {
        sig_dec /= 100u;
        k += 2;
    }
    while (sig_dec >= 10u && (sig_dec % 10u) == 0u) {
        sig_dec /= 10u;
        k += 1;
    }

    char digits[24];
    int P = qjs_u64_to_digits(digits, sig_dec);
    int E = P + k;
    if (E <= -6 || E > 21) {
        *q++ = digits[0];
        if (P > 1) {
            *q++ = '.';
            memcpy(q, digits + 1, (size_t)(P - 1));
            q += P - 1;
        }
        *q++ = 'e';
        int exp = E - 1;
        if (exp < 0) {
            *q++ = '-';
            exp = -exp;
        } else {
            *q++ = '+';
        }
        q += u32toa(q, (uint32_t)exp);
    } else if (E <= 0) {
        *q++ = '0';
        *q++ = '.';
        if (E < 0) {
            memset(q, '0', (size_t)(-E));
            q += -E;
        }
        memcpy(q, digits, (size_t)P);
        q += P;
    } else if (E < P) {
        memcpy(q, digits, (size_t)E);
        q += E;
        *q++ = '.';
        memcpy(q, digits + E, (size_t)(P - E));
        q += P - E;
    } else {
        memcpy(q, digits, (size_t)P);
        q += P;
        if (E > P) {
            memset(q, '0', (size_t)(E - P));
            q += E - P;
        }
    }
    *q = '\0';
    return (int)(q - buf);
}

static inline bool qjs_nearest_rounding_ok(void)
{
#ifdef FE_TONEAREST
    return fegetround() == FE_TONEAREST;
#else
    return true;
#endif
}

static bool qjs_fast_atod_str8(const uint8_t *s, uint32_t len, bool is_parse_float, double *out)
{
    static const double pow10_exact[23] = {
        1e0,  1e1,  1e2,  1e3,  1e4,  1e5,  1e6,  1e7,  1e8,  1e9,  1e10, 1e11,
        1e12, 1e13, 1e14, 1e15, 1e16, 1e17, 1e18, 1e19, 1e20, 1e21, 1e22,
    };
    uint32_t i = 0;
    while (i < len) {
        uint8_t c = s[i];
        if (c == ' ' || (uint32_t)(c - '\t') <= 4u) {
            i++;
        } else {
            if (unlikely(c >= 0x80u))
                return false;
            break;
        }
    }
    if (i == len) {
        if (is_parse_float)
            return false;
        *out = 0.0;
        return true;
    }
    bool neg = false;
    if (s[i] == '-') {
        neg = true;
        i++;
    } else if (s[i] == '+') {
        i++;
    }
    if (i < len && s[i] == '0' && i + 1u < len) {
        uint8_t c1 = s[i + 1u] | 0x20u;
        if (c1 == 'x' || c1 == 'o' || c1 == 'b')
            return false;
    }
    if (i < len && (s[i] == 'I' || s[i] == 'N'))
        return false;

    bool any_digit = false;
    uint32_t sig_digits = 0;
    uint64_t mant = 0;
    int32_t exp10 = 0;

    while (i < len) {
        uint32_t d = (uint32_t)(s[i] - '0');
        if (d > 9u)
            break;
        any_digit = true;
        if (mant != 0u || d != 0u) {
            if (unlikely(sig_digits >= 19u))
                return false;
            mant = mant * 10u + d;
            sig_digits++;
        }
        i++;
    }
    if (i < len && s[i] == '.') {
        i++;
        while (i < len) {
            uint32_t d = (uint32_t)(s[i] - '0');
            if (d > 9u)
                break;
            any_digit = true;
            if (mant != 0u || d != 0u) {
                if (unlikely(sig_digits >= 19u))
                    return false;
                mant = mant * 10u + d;
                sig_digits++;
            }
            if (unlikely(exp10 < -100000))
                return false;
            exp10--;
            i++;
        }
    }
    if (unlikely(!any_digit))
        return false;

    if (i < len && (s[i] == 'e' || s[i] == 'E')) {
        i++;
        bool exp_neg = false;
        if (i < len && (s[i] == '-' || s[i] == '+')) {
            exp_neg = (s[i] == '-');
            i++;
        }
        if (i >= len || (uint32_t)(s[i] - '0') > 9u)
            return false;
        int32_t eacc = 0;
        while (i < len) {
            uint32_t ed = (uint32_t)(s[i] - '0');
            if (ed > 9u)
                break;
            if (unlikely(eacc >= 10000))
                return false;
            eacc = eacc * 10 + (int32_t)ed;
            i++;
        }
        exp10 += exp_neg ? -eacc : eacc;
    }

    while (i < len) {
        uint8_t c = s[i];
        if (c == ' ' || (uint32_t)(c - '\t') <= 4u)
            i++;
        else
            return false;
    }

    if (mant == 0u) {
        *out = neg ? -0.0 : 0.0;
        return true;
    }
    if (exp10 == 0 && mant < (UINT64_C(1) << 53)) {
        double d = (double)mant;
        *out = neg ? -d : d;
        return true;
    }
    if (unlikely(!qjs_nearest_rounding_ok()))
        return false;

    if (mant < (UINT64_C(1) << 53) && exp10 >= -22 && exp10 <= 22) {
        double d = (double)mant;
        if (exp10 > 0)
            d *= pow10_exact[exp10];
        else
            d /= pow10_exact[-exp10];
        *out = neg ? -d : d;
        return true;
    }

    if (unlikely(exp10 < -292 || exp10 > 308))
        return false;

    int lz = clz64(mant);
    uint64_t w = mant << lz;
    const QJSSchubPow10 *p10 = &qjs_schub_pow10[324 - exp10];
    uint64_t p_hi = (p10->g1 << 1) | (p10->g0 >> 63);
    uint64_t p_lo = p10->g0 << 1;
    int32_t e2 = qjs_ashr64((int64_t)exp10 * 217706, 16);
    uint64_t z_lo;
    uint64_t z_hi = qjs_umul128(w, p_hi, &z_lo);
    uint64_t mid = qjs_umul128_hi(w, p_lo);
    z_lo += mid;
    z_hi += (z_lo < mid);

    uint32_t upper = (uint32_t)(z_hi >> 63);
    int32_t biased_exp = (63 - lz) + e2 + (int32_t)upper + 1023;
    if (unlikely(biased_exp <= 0 || biased_exp >= 2047))
        return false;

    uint32_t shift = upper + 9u;
    uint64_t tail_mask = (UINT64_C(1) << shift) - 1u;
    uint64_t tail = z_hi & tail_mask;
    if (unlikely(tail < 4u || tail > tail_mask - 4u))
        return false;

    uint64_t mant54 = z_hi >> shift;
    uint64_t mant53 = (mant54 >> 1) + (mant54 & 1u);
    if (unlikely(mant53 >= (UINT64_C(1) << 53))) {
        mant53 >>= 1;
        biased_exp++;
        if (unlikely(biased_exp >= 2047))
            return false;
    }

    uint64_t bits = ((uint64_t)neg << 63) | ((uint64_t)(uint32_t)biased_exp << 52) |
                    (mant53 & ((UINT64_C(1) << 52) - 1u));
    double d;
    memcpy(&d, &bits, sizeof(d));
    *out = d;
    return true;
}

static inline bool qjs_try_flat_str_to_int32(const JSString *p, int32_t *out, bool allow_neg_zero)
{
    if (unlikely(p->is_wide_char))
        return false;
    uint32_t len = p->len;
    if (unlikely(len == 0u || len > 10u))
        return false;
    const uint8_t *s = (const uint8_t *)str8((JSString *)p);
    uint32_t i = 0;
    bool neg = false;
    if (s[0] == '-') {
        neg = true;
        i = 1;
    } else if (s[0] == '+') {
        i = 1;
    }
    uint32_t ndigits = len - i;
    if (unlikely(ndigits == 0u || ndigits > 9u))
        return false;
    uint32_t acc = 0;
    for (; i < len; i++) {
        uint32_t d = (uint32_t)(s[i] - '0');
        if (unlikely(d > 9u))
            return false;
        acc = acc * 10u + d;
    }
    if (unlikely(neg && acc == 0u)) {
        if (!allow_neg_zero)
            return false;
        *out = 0;
        return true;
    }
    *out = neg ? -(int32_t)acc : (int32_t)acc;
    return true;
}

static inline bool qjs_try_flat_str_to_number(JSContext *ctx, const JSString *p, JSValue *out)
{
    if (unlikely(p->is_wide_char))
        return false;
    int32_t fast_i32;
    if (qjs_try_flat_str_to_int32(p, &fast_i32, false)) {
        *out = JS_NewInt32(ctx, fast_i32);
        return true;
    }
    double d;
    if (qjs_fast_atod_str8((const uint8_t *)str8((JSString *)p), p->len, false, &d)) {
        *out = js_number(d);
        return true;
    }
    return false;
}

static JSBigInt *js_bigint_new(JSContext *ctx, int len);

static inline JSBigInt *qjs_bigint_pool_get(JSContext *ctx, int len)
{
#ifndef FORCE_GC_AT_MALLOC
    if (((uint32_t)len - 1u) < 18u && ctx->rt->fast_pools &&
        ctx->rt->fast_pools->bigint_count[len] > 0u) {
        JSBigInt *r =
            ctx->rt->fast_pools->bigint_pool[len][--ctx->rt->fast_pools->bigint_count[len]];
        JS_REF_COUNT(r) = 1;
        r->len = (uint32_t)len;
        return r;
    }
#else
    (void)ctx;
    (void)len;
#endif
    return NULL;
}

static inline JSBigInt *qjs_bigint_alloc_fast(JSContext *ctx, int len)
{
    JSBigInt *r = qjs_bigint_pool_get(ctx, len);
    return likely(r != NULL) ? r : js_bigint_new(ctx, len);
}

static QJS_BIGINT_COLD_CODE void qjs_bigint_pool_put_slow(JSRuntime *rt, JSBigInt *p)
{
#ifndef FORCE_GC_AT_MALLOC
    uint32_t l = (uint32_t)p->len;
    if ((l - 1u) < 18u && rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit) {
        QJSFastValuePools *fp = rt->fast_pools;
        if (!fp)
            fp = rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools));
        if (likely(fp != NULL) && fp->bigint_count[l] < 8u) {
            fp->bigint_pool[l][fp->bigint_count[l]++] = p;
            return;
        }
    }
#endif
    js_free_rt(rt, p);
}

static inline void qjs_bigint_pool_put(JSRuntime *rt, JSBigInt *p)
{
#ifndef FORCE_GC_AT_MALLOC
    uint32_t l = (uint32_t)p->len;
    QJSFastValuePools *fp = rt->fast_pools;
    if (likely((l - 1u) < 18u && fp != NULL && rt->fast_pool_ok && !rt->in_free &&
               !rt->malloc_state.malloc_limit && fp->bigint_count[l] < 8u)) {
        fp->bigint_pool[l][fp->bigint_count[l]++] = p;
        return;
    }
#endif
    qjs_bigint_pool_put_slow(rt, p);
}

static inline uint32_t qjs_bigint_limbs_to_u64_abs(uint64_t *dst, const js_limb_t *src, uint32_t n,
                                                   int is_neg)
{
    uint32_t w = (n + 1u) >> 1;
    if (!is_neg) {
        for (uint32_t i = 0; i < w; i++) {
            uint64_t lo = src[2u * i];
            uint64_t hi = (2u * i + 1u < n) ? (uint64_t)src[2u * i + 1u] : 0u;
            dst[i] = lo | (hi << 32);
        }
    } else {
        uint64_t borrow = 0;
        for (uint32_t i = 0; i < w; i++) {
            uint64_t lo = src[2u * i];
            uint64_t hi = (2u * i + 1u < n) ? (uint64_t)src[2u * i + 1u] : UINT64_C(0xffffffff);
            uint64_t v = lo | (hi << 32);
            uint64_t neg = (uint64_t)0 - v - borrow;
            borrow = (v | borrow) != 0u ? 1u : 0u;
            dst[i] = neg;
        }
    }
    while (w > 1u && dst[w - 1u] == 0u)
        w--;
    return w;
}

static inline uint32_t qjs_bigint_u64_pos_len(const uint64_t *w, uint32_t nw)
{
    while (nw > 1u && w[nw - 1u] == 0u)
        nw--;
    uint64_t top = w[nw - 1u];
    uint32_t l;
    if (top >> 32) {
        l = nw * 2u;
        if (top >> 63)
            l++;
    } else {
        l = nw * 2u - 1u;
        if ((uint32_t)top >> 31)
            l++;
    }
    return l;
}

static inline void qjs_bigint_store_u64_pos(js_limb_t *dst, const uint64_t *w, uint32_t l)
{
    uint32_t i = 0;
    for (; i + 1u < l; i += 2u) {
        uint64_t v = w[i >> 1];
        dst[i] = (js_limb_t)v;
        dst[i + 1u] = (js_limb_t)(v >> 32);
    }
    if (i < l)
        dst[i] = (js_limb_t)w[i >> 1];
}

static QJS_BIGINT_COLD_CODE int qjs_bigint_mul_u256(JSContext *ctx, const JSBigInt *a,
                                                    const JSBigInt *b, JSBigInt **out)
{
    uint32_t na = (uint32_t)a->len, nb = (uint32_t)b->len;
    int a_neg = (int)(a->tab[na - 1u] >> 31);
    int b_neg = (int)(b->tab[nb - 1u] >> 31);
    uint32_t aext = a_neg ? UINT32_MAX : 0u;
    uint64_t a0 = (uint64_t)a->tab[0] | ((uint64_t)(na > 1u ? a->tab[1] : aext) << 32);
    uint64_t a1 =
        (uint64_t)(na > 2u ? a->tab[2] : aext) | ((uint64_t)(na > 3u ? a->tab[3] : aext) << 32);
    uint64_t a2 =
        (uint64_t)(na > 4u ? a->tab[4] : aext) | ((uint64_t)(na > 5u ? a->tab[5] : aext) << 32);
    uint64_t a3 =
        (uint64_t)(na > 6u ? a->tab[6] : aext) | ((uint64_t)(na > 7u ? a->tab[7] : aext) << 32);
    if (a_neg) {
        a0 = ~a0 + 1u;
        uint64_t c = (a0 == 0u);
        a1 = ~a1 + c;
        c &= (a1 == 0u);
        a2 = ~a2 + c;
        c &= (a2 == 0u);
        a3 = ~a3 + c;
        if (unlikely(c && a3 == 0u))
            return 0;
    }
    uint64_t r[9];
#if defined(__SIZEOF_INT128__)
    if (a == b) {
        __uint128_t t;
        t = (__uint128_t)a0 * a1;
        uint64_t x1 = (uint64_t)t;
        t = (__uint128_t)a0 * a2 + (uint64_t)(t >> 64);
        uint64_t x2 = (uint64_t)t;
        t = (__uint128_t)a0 * a3 + (uint64_t)(t >> 64);
        uint64_t x3 = (uint64_t)t;
        uint64_t x4 = (uint64_t)(t >> 64);

        t = (__uint128_t)a1 * a2 + x3;
        x3 = (uint64_t)t;
        t = (__uint128_t)a1 * a3 + x4 + (uint64_t)(t >> 64);
        x4 = (uint64_t)t;
        uint64_t x5 = (uint64_t)(t >> 64);

        t = (__uint128_t)a2 * a3 + x5;
        x5 = (uint64_t)t;
        uint64_t x6 = (uint64_t)(t >> 64);

        uint64_t x7 = x6 >> 63;
        x6 = (x6 << 1) | (x5 >> 63);
        x5 = (x5 << 1) | (x4 >> 63);
        x4 = (x4 << 1) | (x3 >> 63);
        x3 = (x3 << 1) | (x2 >> 63);
        x2 = (x2 << 1) | (x1 >> 63);
        x1 = x1 << 1;

        t = (__uint128_t)a0 * a0;
        r[0] = (uint64_t)t;
        t = (__uint128_t)x1 + (uint64_t)(t >> 64);
        r[1] = (uint64_t)t;
        t = (__uint128_t)a1 * a1 + x2 + (uint64_t)(t >> 64);
        r[2] = (uint64_t)t;
        t = (__uint128_t)x3 + (uint64_t)(t >> 64);
        r[3] = (uint64_t)t;
        t = (__uint128_t)a2 * a2 + x4 + (uint64_t)(t >> 64);
        r[4] = (uint64_t)t;
        t = (__uint128_t)x5 + (uint64_t)(t >> 64);
        r[5] = (uint64_t)t;
        t = (__uint128_t)a3 * a3 + x6 + (uint64_t)(t >> 64);
        r[6] = (uint64_t)t;
        r[7] = x7 + (uint64_t)(t >> 64);
    } else {
        uint32_t bext = b_neg ? UINT32_MAX : 0u;
        uint64_t b0 = (uint64_t)b->tab[0] | ((uint64_t)(nb > 1u ? b->tab[1] : bext) << 32);
        uint64_t b1 =
            (uint64_t)(nb > 2u ? b->tab[2] : bext) | ((uint64_t)(nb > 3u ? b->tab[3] : bext) << 32);
        uint64_t b2 =
            (uint64_t)(nb > 4u ? b->tab[4] : bext) | ((uint64_t)(nb > 5u ? b->tab[5] : bext) << 32);
        uint64_t b3 =
            (uint64_t)(nb > 6u ? b->tab[6] : bext) | ((uint64_t)(nb > 7u ? b->tab[7] : bext) << 32);
        if (b_neg) {
            b0 = ~b0 + 1u;
            uint64_t c = (b0 == 0u);
            b1 = ~b1 + c;
            c &= (b1 == 0u);
            b2 = ~b2 + c;
            c &= (b2 == 0u);
            b3 = ~b3 + c;
            if (unlikely(c && b3 == 0u))
                return 0;
        }
        __uint128_t t;
        t = (__uint128_t)a0 * b0;
        r[0] = (uint64_t)t;
        t = (__uint128_t)a0 * b1 + (uint64_t)(t >> 64);
        r[1] = (uint64_t)t;
        t = (__uint128_t)a0 * b2 + (uint64_t)(t >> 64);
        r[2] = (uint64_t)t;
        t = (__uint128_t)a0 * b3 + (uint64_t)(t >> 64);
        r[3] = (uint64_t)t;
        r[4] = (uint64_t)(t >> 64);

        t = (__uint128_t)a1 * b0 + r[1];
        r[1] = (uint64_t)t;
        t = (__uint128_t)a1 * b1 + r[2] + (uint64_t)(t >> 64);
        r[2] = (uint64_t)t;
        t = (__uint128_t)a1 * b2 + r[3] + (uint64_t)(t >> 64);
        r[3] = (uint64_t)t;
        t = (__uint128_t)a1 * b3 + r[4] + (uint64_t)(t >> 64);
        r[4] = (uint64_t)t;
        r[5] = (uint64_t)(t >> 64);

        t = (__uint128_t)a2 * b0 + r[2];
        r[2] = (uint64_t)t;
        t = (__uint128_t)a2 * b1 + r[3] + (uint64_t)(t >> 64);
        r[3] = (uint64_t)t;
        t = (__uint128_t)a2 * b2 + r[4] + (uint64_t)(t >> 64);
        r[4] = (uint64_t)t;
        t = (__uint128_t)a2 * b3 + r[5] + (uint64_t)(t >> 64);
        r[5] = (uint64_t)t;
        r[6] = (uint64_t)(t >> 64);

        t = (__uint128_t)a3 * b0 + r[3];
        r[3] = (uint64_t)t;
        t = (__uint128_t)a3 * b1 + r[4] + (uint64_t)(t >> 64);
        r[4] = (uint64_t)t;
        t = (__uint128_t)a3 * b2 + r[5] + (uint64_t)(t >> 64);
        r[5] = (uint64_t)t;
        t = (__uint128_t)a3 * b3 + r[6] + (uint64_t)(t >> 64);
        r[6] = (uint64_t)t;
        r[7] = (uint64_t)(t >> 64);
    }
#elif defined(_MSC_VER) && defined(_M_X64)
    {
        uint32_t bext = b_neg ? UINT32_MAX : 0u;
        uint64_t b0 = (uint64_t)b->tab[0] | ((uint64_t)(nb > 1u ? b->tab[1] : bext) << 32);
        uint64_t b1 =
            (uint64_t)(nb > 2u ? b->tab[2] : bext) | ((uint64_t)(nb > 3u ? b->tab[3] : bext) << 32);
        uint64_t b2 =
            (uint64_t)(nb > 4u ? b->tab[4] : bext) | ((uint64_t)(nb > 5u ? b->tab[5] : bext) << 32);
        uint64_t b3 =
            (uint64_t)(nb > 6u ? b->tab[6] : bext) | ((uint64_t)(nb > 7u ? b->tab[7] : bext) << 32);
        if (b_neg) {
            b0 = ~b0 + 1u;
            uint64_t c = (b0 == 0u);
            b1 = ~b1 + c;
            c &= (b1 == 0u);
            b2 = ~b2 + c;
            c &= (b2 == 0u);
            b3 = ~b3 + c;
            if (unlikely(c && b3 == 0u))
                return 0;
        }
        uint64_t ua[4] = {a0, a1, a2, a3};
        uint64_t ub[4] = {b0, b1, b2, b3};
        r[0] = r[1] = r[2] = r[3] = r[4] = r[5] = r[6] = r[7] = 0;
        for (uint32_t i = 0; i < 4u; i++) {
            uint64_t ai = ua[i], carry = 0;
            for (uint32_t j = 0; j < 4u; j++) {
                uint64_t hi, lo = _umul128(ai, ub[j], &hi);
                unsigned char c1 = _addcarry_u64(0, lo, r[i + j], &lo);
                unsigned char c2 = _addcarry_u64(0, lo, carry, &lo);
                r[i + j] = lo;
                carry = hi + (uint64_t)c1 + (uint64_t)c2;
            }
            r[i + 4u] = carry;
        }
    }
#else
    (void)a0;
    (void)a1;
    (void)a2;
    (void)a3;
    return 0;
#endif
    if (unlikely(a_neg ^ b_neg)) {
        uint64_t borrow = 0;
        for (uint32_t k = 0; k < 8u; k++) {
            uint64_t v = r[k];
            r[k] = (uint64_t)0 - v - borrow;
            borrow = (v | borrow) != 0u ? 1u : 0u;
        }
        if (unlikely(!borrow)) {
            JSBigInt *res = qjs_bigint_alloc_fast(ctx, 1);
            if (res)
                res->tab[0] = 0;
            *out = res;
            return 1;
        }
        r[8] = UINT64_MAX;
        uint32_t nw = 8u;
        while (nw > 1u && r[nw - 1u] == UINT64_MAX)
            nw--;
        uint64_t top = r[nw - 1u];
        uint32_t l;
        if ((uint32_t)(top >> 32) != UINT32_MAX) {
            l = nw * 2u + ((top >> 63) == 0u ? 1u : 0u);
        } else {
            l = nw * 2u - 1u + (((uint32_t)top >> 31) == 0u ? 1u : 0u);
        }
        JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
        if (likely(res != NULL))
            qjs_bigint_store_u64_pos(res->tab, r, l);
        *out = res;
        return 1;
    }
    r[8] = 0;
    uint32_t l = qjs_bigint_u64_pos_len(r, 8u);
    JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
    if (likely(res != NULL))
        qjs_bigint_store_u64_pos(res->tab, r, l);
    *out = res;
    return 1;
}

static QJS_BIGINT_COLD_CODE JSBigInt *qjs_bigint_add_sub_u256(JSContext *ctx, const JSBigInt *a,
                                                              const JSBigInt *b, int is_sub)
{
    uint32_t na = (uint32_t)a->len, nb = (uint32_t)b->len;
    uint32_t aext = (a->tab[na - 1u] >> 31) ? UINT32_MAX : 0u;
    uint32_t bext = (b->tab[nb - 1u] >> 31) ? UINT32_MAX : 0u;
    uint64_t a0 = (uint64_t)a->tab[0] | ((uint64_t)(na > 1u ? a->tab[1] : aext) << 32);
    uint64_t a1 =
        (uint64_t)(na > 2u ? a->tab[2] : aext) | ((uint64_t)(na > 3u ? a->tab[3] : aext) << 32);
    uint64_t a2 =
        (uint64_t)(na > 4u ? a->tab[4] : aext) | ((uint64_t)(na > 5u ? a->tab[5] : aext) << 32);
    uint64_t a3 =
        (uint64_t)(na > 6u ? a->tab[6] : aext) | ((uint64_t)(na > 7u ? a->tab[7] : aext) << 32);
    uint64_t a4 = (uint64_t)(na > 8u ? a->tab[8] : aext) | ((uint64_t)aext << 32);
    uint64_t b0 = (uint64_t)b->tab[0] | ((uint64_t)(nb > 1u ? b->tab[1] : bext) << 32);
    uint64_t b1 =
        (uint64_t)(nb > 2u ? b->tab[2] : bext) | ((uint64_t)(nb > 3u ? b->tab[3] : bext) << 32);
    uint64_t b2 =
        (uint64_t)(nb > 4u ? b->tab[4] : bext) | ((uint64_t)(nb > 5u ? b->tab[5] : bext) << 32);
    uint64_t b3 =
        (uint64_t)(nb > 6u ? b->tab[6] : bext) | ((uint64_t)(nb > 7u ? b->tab[7] : bext) << 32);
    uint64_t b4 = (uint64_t)(nb > 8u ? b->tab[8] : bext) | ((uint64_t)bext << 32);
    uint64_t s[5];
    if (!is_sub) {
        uint64_t r0 = a0 + b0, c0 = (r0 < a0);
        uint64_t t1 = a1 + b1, r1 = t1 + c0, c1 = (t1 < a1) | (r1 < t1);
        uint64_t t2 = a2 + b2, r2 = t2 + c1, c2 = (t2 < a2) | (r2 < t2);
        uint64_t t3 = a3 + b3, r3 = t3 + c2, c3 = (t3 < a3) | (r3 < t3);
        s[0] = r0;
        s[1] = r1;
        s[2] = r2;
        s[3] = r3;
        s[4] = a4 + b4 + c3;
    } else {
        uint64_t r0 = a0 - b0, bw0 = (a0 < b0);
        uint64_t t1 = a1 - b1, r1 = t1 - bw0, bw1 = (a1 < b1) | (t1 < bw0);
        uint64_t t2 = a2 - b2, r2 = t2 - bw1, bw2 = (a2 < b2) | (t2 < bw1);
        uint64_t t3 = a3 - b3, r3 = t3 - bw2, bw3 = (a3 < b3) | (t3 < bw2);
        s[0] = r0;
        s[1] = r1;
        s[2] = r2;
        s[3] = r3;
        s[4] = a4 - b4 - bw3;
    }
    uint32_t l;
    if ((s[4] >> 63) == 0u) {
        uint32_t nw = 5u;
        while (nw > 1u && s[nw - 1u] == 0u)
            nw--;
        uint64_t top = s[nw - 1u];
        if (top >> 32)
            l = nw * 2u + (uint32_t)(top >> 63);
        else
            l = nw * 2u - 1u + (uint32_t)((uint32_t)top >> 31);
    } else {
        uint32_t nw = 5u;
        while (nw > 1u && s[nw - 1u] == UINT64_MAX)
            nw--;
        uint64_t top = s[nw - 1u];
        if ((uint32_t)(top >> 32) != UINT32_MAX)
            l = nw * 2u + ((top >> 63) == 0u ? 1u : 0u);
        else
            l = nw * 2u - 1u + (((uint32_t)top >> 31) == 0u ? 1u : 0u);
    }
    JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
    if (likely(res != NULL))
        qjs_bigint_store_u64_pos(res->tab, s, l);
    return res;
}

static QJS_BIGINT_COLD_CODE JSBigInt *qjs_bigint_shr_small(JSContext *ctx, const JSBigInt *a,
                                                           uint32_t shift)
{
    uint32_t na = (uint32_t)a->len;
    uint32_t rshift = 32u - shift;
    uint32_t top = a->tab[na - 1u] >> shift;
    uint32_t l;
    if (na == 1u) {
        l = 1u;
    } else if (top != 0u) {
        l = na;
    } else {
        uint32_t prev = (a->tab[na - 2u] >> shift) | (a->tab[na - 1u] << rshift);
        l = (prev >> 31) ? na : (na - 1u);
    }
    JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
    if (unlikely(!res))
        return NULL;
    for (uint32_t i = 0; i + 1u < na && i < l; i++)
        res->tab[i] = (a->tab[i] >> shift) | (a->tab[i + 1u] << rshift);
    if (l == na)
        res->tab[na - 1u] = top;
    return res;
}

static QJS_BIGINT_COLD_CODE int qjs_bigint_mul_general(JSContext *ctx, const JSBigInt *a,
                                                       const JSBigInt *b, JSBigInt **out)
{
    uint32_t na = (uint32_t)a->len, nb = (uint32_t)b->len;
    int a_neg = (int)(a->tab[na - 1u] >> 31);
    int b_neg = (int)(b->tab[nb - 1u] >> 31);
    uint64_t ua[8], ub[8], prod64[16];
    uint32_t wa = qjs_bigint_limbs_to_u64_abs(ua, a->tab, na, a_neg);
    uint32_t wb = qjs_bigint_limbs_to_u64_abs(ub, b->tab, nb, b_neg);
    uint32_t wp = wa + wb;
    for (uint32_t k = 0; k < wp; k++)
        prod64[k] = 0;
#if defined(__SIZEOF_INT128__)
    for (uint32_t i = 0; i < wa; i++) {
        __uint128_t ai = ua[i];
        uint64_t carry = 0;
        for (uint32_t j = 0; j < wb; j++) {
            __uint128_t t = ai * (__uint128_t)ub[j] + prod64[i + j] + carry;
            prod64[i + j] = (uint64_t)t;
            carry = (uint64_t)(t >> 64);
        }
        prod64[i + wb] = carry;
    }
#elif defined(_MSC_VER) && defined(_M_X64)
    for (uint32_t i = 0; i < wa; i++) {
        uint64_t ai = ua[i];
        uint64_t carry = 0;
        for (uint32_t j = 0; j < wb; j++) {
            uint64_t hi, lo = _umul128(ai, ub[j], &hi);
            unsigned char c1 = _addcarry_u64(0, lo, prod64[i + j], &lo);
            unsigned char c2 = _addcarry_u64(0, lo, carry, &lo);
            prod64[i + j] = lo;
            carry = hi + (uint64_t)c1 + (uint64_t)c2;
        }
        prod64[i + wb] = carry;
    }
#else
    return 0;
#endif
    js_limb_t prod[33];
    uint32_t l = wp * 2u;
    for (uint32_t k = 0; k < wp; k++) {
        prod[2u * k] = (js_limb_t)prod64[k];
        prod[2u * k + 1u] = (js_limb_t)(prod64[k] >> 32);
    }
    prod[l++] = 0;
    if (a_neg ^ b_neg) {
        uint64_t borrow = 0;
        for (uint32_t k = 0; k < l; k++) {
            uint64_t v = (uint64_t)prod[k];
            uint64_t d = (uint64_t)0 - v - borrow;
            prod[k] = (js_limb_t)d;
            borrow = (v | borrow) != 0u ? 1u : 0u;
        }
        while (l > 1u && prod[l - 1u] == (js_limb_t)-1 && (prod[l - 2u] >> 31) == 1u)
            l--;
        while (l > 1u && prod[l - 1u] == 0u && (prod[l - 2u] >> 31) == 0u)
            l--;
    } else {
        while (l > 1u && prod[l - 1u] == 0u && (prod[l - 2u] >> 31) == 0u)
            l--;
    }
    JSBigInt *r = js_bigint_new(ctx, (int)l);
    if (r)
        memcpy(r->tab, prod, (size_t)l * sizeof(js_limb_t));
    *out = r;
    return 1;
}

static QJS_BIGINT_COLD_CODE int qjs_bigint_mul_fast(JSContext *ctx, const JSBigInt *a,
                                                    const JSBigInt *b, JSBigInt **out)
{
#if defined(__SIZEOF_INT128__) || (defined(_MSC_VER) && defined(_M_X64))
    uint32_t na = (uint32_t)a->len, nb = (uint32_t)b->len;
    if (likely(na <= 4u && nb <= 4u && (a->tab[na - 1u] >> 31) == 0u &&
               (b->tab[nb - 1u] >> 31) == 0u)) {
        uint64_t a0 = (uint64_t)a->tab[0] | (na > 1u ? ((uint64_t)a->tab[1] << 32) : 0u);
        uint64_t a1 =
            (na > 2u ? (uint64_t)a->tab[2] : 0u) | (na > 3u ? ((uint64_t)a->tab[3] << 32) : 0u);
        uint64_t r0, r1, r2, r3;
#if defined(__SIZEOF_INT128__)
        if (a == b) {
            __uint128_t p00 = (__uint128_t)a0 * a0;
            __uint128_t p01 = (__uint128_t)a0 * a1;
            __uint128_t p11 = (__uint128_t)a1 * a1;
            r0 = (uint64_t)p00;
            uint64_t x1 = (uint64_t)p01;
            uint64_t x2 = (uint64_t)(p01 >> 64);
            uint64_t x3 = x2 >> 63;
            x2 = (x2 << 1) | (x1 >> 63);
            x1 = x1 << 1;
            __uint128_t t = (__uint128_t)x1 + (uint64_t)(p00 >> 64);
            r1 = (uint64_t)t;
            t = (__uint128_t)(uint64_t)p11 + x2 + (uint64_t)(t >> 64);
            r2 = (uint64_t)t;
            r3 = (uint64_t)(p11 >> 64) + x3 + (uint64_t)(t >> 64);
        } else {
            uint64_t b0 = (uint64_t)b->tab[0] | (nb > 1u ? ((uint64_t)b->tab[1] << 32) : 0u);
            uint64_t b1 =
                (nb > 2u ? (uint64_t)b->tab[2] : 0u) | (nb > 3u ? ((uint64_t)b->tab[3] << 32) : 0u);
            __uint128_t t = (__uint128_t)a0 * b0;
            r0 = (uint64_t)t;
            t = (__uint128_t)a0 * b1 + (uint64_t)(t >> 64);
            uint64_t m1 = (uint64_t)t;
            uint64_t m2 = (uint64_t)(t >> 64);
            t = (__uint128_t)a1 * b0 + m1;
            r1 = (uint64_t)t;
            t = (__uint128_t)a1 * b1 + m2 + (uint64_t)(t >> 64);
            r2 = (uint64_t)t;
            r3 = (uint64_t)(t >> 64);
        }
#else
        uint64_t b0 = (uint64_t)b->tab[0] | (nb > 1u ? ((uint64_t)b->tab[1] << 32) : 0u);
        uint64_t b1 =
            (nb > 2u ? (uint64_t)b->tab[2] : 0u) | (nb > 3u ? ((uint64_t)b->tab[3] << 32) : 0u);
        uint64_t h00, h01, h10, h11, m1, m2;
        r0 = _umul128(a0, b0, &h00);
        uint64_t l01 = _umul128(a0, b1, &h01);
        unsigned char c = _addcarry_u64(0, l01, h00, &m1);
        m2 = h01 + c;
        uint64_t l10 = _umul128(a1, b0, &h10);
        c = _addcarry_u64(0, l10, m1, &r1);
        uint64_t l11 = _umul128(a1, b1, &h11);
        unsigned char c1 = _addcarry_u64(0, l11, m2, &r2);
        unsigned char c2 = _addcarry_u64(0, r2, h10 + c, &r2);
        r3 = h11 + c1 + c2;
#endif
        uint64_t top;
        uint32_t nw;
        if (r3) {
            nw = 4u;
            top = r3;
        } else if (r2) {
            nw = 3u;
            top = r2;
        } else if (r1) {
            nw = 2u;
            top = r1;
        } else {
            nw = 1u;
            top = r0;
        }
        uint32_t l = (top >> 32) ? (nw * 2u + (uint32_t)(top >> 63))
                                 : (nw * 2u - 1u + (uint32_t)((uint32_t)top >> 31));
        JSBigInt *res = qjs_bigint_alloc_fast(ctx, (int)l);
        if (likely(res != NULL)) {
            res->tab[0] = (js_limb_t)r0;
            if (l > 1u)
                res->tab[1] = (js_limb_t)(r0 >> 32);
            if (l > 2u)
                res->tab[2] = (js_limb_t)r1;
            if (l > 3u)
                res->tab[3] = (js_limb_t)(r1 >> 32);
            if (l > 4u)
                res->tab[4] = (js_limb_t)r2;
            if (l > 5u)
                res->tab[5] = (js_limb_t)(r2 >> 32);
            if (l > 6u)
                res->tab[6] = (js_limb_t)r3;
            if (l > 7u)
                res->tab[7] = (js_limb_t)(r3 >> 32);
            if (l > 8u)
                res->tab[8] = 0;
        }
        *out = res;
        return 1;
    }
    if (na <= 9u && nb <= 9u && (na < 9u || a->tab[8] == 0u || a->tab[8] == UINT32_MAX) &&
        (nb < 9u || b->tab[8] == 0u || b->tab[8] == UINT32_MAX)) {
        if (qjs_bigint_mul_u256(ctx, a, b, out))
            return 1;
    }
    if (na >= 1u && na <= 16u && nb >= 1u && nb <= 16u)
        return qjs_bigint_mul_general(ctx, a, b, out);
#else
    (void)ctx;
    (void)a;
    (void)b;
    (void)out;
#endif
    return 0;
}

static no_inline JSValue qjs_int_to_string_populate(JSContext *ctx, int32_t v)
{
#ifndef FORCE_GC_AT_MALLOC
    JSRuntime *rt = ctx->rt;
    if (rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit) {
        if (!rt->fast_pools)
            rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools));
        if (likely(rt->fast_pools != NULL)) {
            uint32_t idx = (uint32_t)v - 10u;
            JSString *cached = rt->fast_pools->small_int_strings[idx];
            if (likely(cached != NULL))
                return js_dup(JS_MKPTR(JS_TAG_STRING, cached));
            JSValue s = js_new_string8_len(ctx, qjs_digit_pairs + (size_t)v * 2u, 2);
            if (unlikely(JS_IsException(s)))
                return JS_EXCEPTION;
            rt->fast_pools->small_int_strings[idx] = JS_VALUE_GET_STRING(s);
            return js_dup(s);
        }
    }
#endif
    return js_new_string8_len(ctx, qjs_digit_pairs + (size_t)v * 2u, 2);
}

#define QJS_INT_TO_STRING_FAST_AVAILABLE 1
static inline JSValue qjs_int_to_string_fast(JSContext *ctx, int32_t v)
{
    if (likely((uint32_t)v < 10u))
        return js_new_string_char(ctx, (uint16_t)('0' + (uint32_t)v));
#ifndef FORCE_GC_AT_MALLOC
    if (((uint32_t)v - 10u) < 90u) {
        QJSFastValuePools *fp = ctx->rt->fast_pools;
        if (likely(fp != NULL)) {
            JSString *cached = fp->small_int_strings[(uint32_t)v - 10u];
            if (likely(cached != NULL)) {
                JS_REF_COUNT(cached)++;
                return JS_MKPTR(JS_TAG_STRING, cached);
            }
        }
        return qjs_int_to_string_populate(ctx, v);
    }
#endif
    char buf[16];
    int len = (int)i32toa(buf, v);
    return js_new_string8_len(ctx, buf, len);
}

static void qjs_runtime_drain_fast_pools(JSRuntime *rt)
{
#ifndef FORCE_GC_AT_MALLOC
    QJSFastValuePools *fp = rt->fast_pools;
    if (fp) {
        uint32_t i, l;
        rt->fast_pools = NULL;
        if (fp->iter_result_shape)
            js_free_shape(rt, fp->iter_result_shape);
        for (i = 0; i < fp->job2_count; i++)
            js_free_rt(rt, fp->job2_pool[i]);
        for (i = 0; i < fp->promise_data_count; i++)
            js_free_rt(rt, fp->promise_data_pool[i]);
        for (i = 0; i < 90u; i++) {
            if (fp->small_int_strings[i])
                JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_STRING, fp->small_int_strings[i]));
        }
        for (l = 1u; l <= 18u; l++) {
            uint8_t cnt = fp->bigint_count[l];
            for (i = 0; i < cnt; i++) {
                js_free_rt(rt, fp->bigint_pool[l][i]);
            }
        }
        js_free_rt(rt, fp);
    }
#else
    (void)rt;
#endif
}
