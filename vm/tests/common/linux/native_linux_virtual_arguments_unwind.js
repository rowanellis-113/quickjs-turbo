/* Natural forwarding entry for the read-only native unwind proof. */
function Forward() {
  this.work.apply(this, arguments);
}
Forward.prototype.work = function (a, b) {
  this.sum = a + b;
};
function drive() {
  var result;
  for (var i = 0; i < 200; i++) result = new Forward(i, i + 1);
  return result.sum;
}
if (drive() !== 399) throw Error("forwarding result");
print("LINUX_VIRTUAL_ARGUMENTS_UNWIND_OK");
