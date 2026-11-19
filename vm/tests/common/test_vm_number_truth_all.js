// Force every existing short/long true/false branch form plus logical not.
function seedNumberTruthMode() {
  return {};
}
for (let k = 0; k < 20; k++) seedNumberTruthMode();
const work = Array(300).fill("z+=1;").join("");
const forms = [
  new Function("v", "return !v;"),
  new Function("v", "if(v)return 1;return 0;"),
  new Function("v", "let z=0;if(v){" + work + "}return z;"),
  new Function("v", "let n=0;do{n++;if(n===2)break;}while(v);return n;"),
  new Function("v", "let n=0,z=0;do{n++;if(n===2)break;" + work + "}while(v);return n;"),
];
const values = [
  0,
  -0,
  NaN,
  0.25,
  -0.25,
  Infinity,
  -Infinity,
  Number.MIN_VALUE,
  -Number.MIN_VALUE,
  Number.MAX_VALUE,
  2147483648,
  -2147483649,
];
const truth = [false, false, false, true, true, true, true, true, true, true, true, true];
let checks = 0;
for (let pass = 0; pass < 120; pass++)
  for (let i = 0; i < values.length; i++) {
    const expected = [
      !truth[i],
      truth[i] ? 1 : 0,
      truth[i] ? 300 : 0,
      truth[i] ? 2 : 1,
      truth[i] ? 2 : 1,
    ];
    for (let j = 0; j < forms.length; j++) {
      const result = forms[j](values[i]);
      if (result !== expected[j])
        throw Error("Number branch form " + j + " value " + i + " result " + result);
      checks++;
    }
  }
print("NUMBER_TRUTH_ALL_OK", checks);
