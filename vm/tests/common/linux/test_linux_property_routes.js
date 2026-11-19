/* Compact native activations with multiple property sites and global cells. */
"use strict";
var propertyRouteSymbol = Symbol("route");
var propertyRouteChecks = 0;
function routeEqual(a, b) {
  if (a !== b) throw Error(a + " != " + b);
  ++propertyRouteChecks;
}
function symbolRoute(v) {
  if (v === propertyRouteSymbol) return 1;
  return 0;
}
function ownRoute(o) {
  return o.value;
}
function capturedRoute(o) {
  return function () {
    return o.value;
  };
}
var routeObject = { value: 19 };
var captured = capturedRoute(routeObject);
for (var i = 0; i < 64; ++i) {
  routeEqual(ownRoute(routeObject), 19);
  routeEqual(captured(), 19);
  routeEqual(symbolRoute(propertyRouteSymbol), 1);
  routeEqual(symbolRoute(Symbol("other")), 0);
}
var oldRouteDescriptor = Object.getOwnPropertyDescriptor(String.prototype, "routeMethod");
try {
  Object.defineProperty(String.prototype, "routeMethod", {
    configurable: true,
    writable: true,
    value: function (v) {
      "use strict";
      return this.length + v;
    },
  });
  var body = "var sum=0;for(var round=0;round<8;++round){";
  for (var k = 0; k < 24; ++k) body += "sum+=v.routeMethod(" + k + ");";
  var crowded = Function("v", body + "}return sum;");
  routeEqual(crowded("abc"), 2784);
  routeEqual(crowded("abc"), 2784);
} finally {
  if (oldRouteDescriptor)
    Object.defineProperty(String.prototype, "routeMethod", oldRouteDescriptor);
  else delete String.prototype.routeMethod;
}
function inheritedRoute(o, n) {
  return o.routeMethod(n);
}
for (var k = 0; k < 32; ++k) {
  var root = {
    value: k,
    routeMethod: function (n) {
      return this.value + n;
    },
  };
  var receiver = Object.create(Object.create(Object.create(root)));
  routeEqual(inheritedRoute(receiver, 5), k + 5);
}
gc();
print("LINUX_PROPERTY_ROUTES_OK checks=" + propertyRouteChecks);
