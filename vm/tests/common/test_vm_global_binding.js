/* Global binding lifecycle checks run in their original script scope. */
import * as std from "qjs:std";
globalThis.std = std;
std.evalScript(String.raw`let bindingChecks = 0;
function equalBinding(actual, expected, label) {
    ++bindingChecks;
    if (actual !== expected) throw Error(label + ': ' + String(actual) + ' != ' + String(expected));
}
function referenceFailure(thunk, label) {
    let error;
    try { thunk(); } catch (e) { error = e; }
    equalBinding(error instanceof ReferenceError, true, label);
}
std.evalScript('let __idxMutable=1; const __idxConstant=Symbol("constant"); class __idxClass {}');
const bindingAnchor = {keep: 7};
const bindingSymbol = std.evalScript('__idxConstant');
const bindingClass = std.evalScript('__idxClass');
function readIndexedBindings(receiver) {
    const keep = receiver.keep;
    return [keep, __idxMutable, __idxConstant, __idxClass];
}
for (let i = 0; i < 96; ++i) {
    std.evalScript('__idxMutable=' + i);
    const values = readIndexedBindings(bindingAnchor);
    equalBinding(values[0], 7, 'by-id shares the slab');
    equalBinding(values[1], i, 'mutable current value');
    equalBinding(values[2], bindingSymbol, 'symbol identity');
    equalBinding(values[3], bindingClass, 'class binding');
}
function readIndexedTDZ(receiver) { const keep = receiver.keep; return __idxTDZ + keep; }
function typeofIndexedTDZ(receiver) { const keep = receiver.keep; return typeof __idxTDZ; }
globalThis.__runIndexedTDZ = function () {
    for (let i = 0; i < 12; ++i) {
        referenceFailure(() => readIndexedTDZ(bindingAnchor), 'TDZ load');
        referenceFailure(() => typeofIndexedTDZ(bindingAnchor), 'TDZ typeof');
    }
};
std.evalScript('__runIndexedTDZ(); let __idxTDZ=41;');
equalBinding(readIndexedTDZ(bindingAnchor), 48, 'initialized after cached TDZ');
equalBinding(typeofIndexedTDZ(bindingAnchor), 'number', 'typeof initialized');
std.evalScript(Array.from({length: 769}, (_, i) => 'let __idxGrowth' + i + '=' + i + ';').join(''));
std.evalScript('__idxMutable={token:"live"}');
let afterGrowth = readIndexedBindings(bindingAnchor);
equalBinding(afterGrowth[1].token, 'live', 'global property array resize');
equalBinding(afterGrowth[2], bindingSymbol, 'symbol after resize');
std.gc();
equalBinding(readIndexedBindings(bindingAnchor)[1], afterGrowth[1], 'GC current object identity');
globalThis.__idxShadow = 13;
function readIndexedShadow(receiver) { const keep = receiver.keep; return __idxShadow + keep; }
for (let i = 0; i < 24; ++i) equalBinding(readIndexedShadow(bindingAnchor), 20, 'unresolved object binding');
std.evalScript('let __idxShadow=21;');
for (let i = 0; i < 24; ++i) equalBinding(readIndexedShadow(bindingAnchor), 28, 'later lexical shadow');
let getterCalls = 0;
Object.defineProperty(globalThis, '__idxGetter', {configurable: true, get() {
    ++getterCalls;
    std.gc();
    std.evalScript('__idxMutable=99');
    return 10;
}});
function readIndexedGetter(receiver) { const keep = receiver.keep; return __idxGetter + keep; }
for (let i = 0; i < 32; ++i) equalBinding(readIndexedGetter(bindingAnchor), 17, 'getter reentry');
equalBinding(getterCalls, 32, 'one getter invocation per read');
equalBinding(readIndexedBindings(bindingAnchor)[1], 99, 'reentrant binding replacement');
function indexedMissingType(receiver) { const keep = receiver.keep; return typeof __idxAbsent; }
equalBinding(indexedMissingType(bindingAnchor), 'undefined', 'get_var_undef miss');
function indexedMissingRead(receiver) { const keep = receiver.keep; return __idxAbsent; }
referenceFailure(() => indexedMissingRead(bindingAnchor), 'missing binding throw');
function noPropertySlab() { return __idxMutable; }
equalBinding(noPropertySlab(), 99, 'no property metadata fallback');
let constError;
try { std.evalScript('__idxConstant=0;'); } catch (e) { constError = e; }
equalBinding(constError instanceof TypeError, true, 'const assignment');
equalBinding(readIndexedBindings(bindingAnchor)[2], bindingSymbol, 'const preserved');
print('BINDING_INDEX_SEMANTICS_OK ' + bindingChecks);

// Appended to the previous 500 guarded-path reference checks.
const cellObject = {version: 'first'};
globalThis.__cellData = cellObject;
function readOwnCell(receiver) { const keep = receiver.keep; return __cellData; }
for (let i=0;i<64;++i) equalBinding(readOwnCell(bindingAnchor),cellObject,'global own cell');
let cellGetterCalls=0;
Object.defineProperty(globalThis,'__cellData',{configurable:true,get(){++cellGetterCalls;std.gc();return 'getter';}});
for (let i=0;i<32;++i) equalBinding(readOwnCell(bindingAnchor),'getter','data to accessor invalidation');
equalBinding(cellGetterCalls,32,'accessor side effects');
Object.defineProperty(globalThis,'__cellData',{configurable:true,writable:true,value:17});
for (let i=0;i<32;++i) equalBinding(readOwnCell(bindingAnchor),17,'accessor to data');
delete globalThis.__cellData;
for (let i=0;i<16;++i) referenceFailure(()=>readOwnCell(bindingAnchor),'deleted own cell');
const cellObject2={version:'second'};
globalThis.__cellData=cellObject2;
for (let i=0;i<32;++i) equalBinding(readOwnCell(bindingAnchor),cellObject2,'recreated own cell');
for (let round=0;round<12;++round) {
    const ownReader=new Function('receiver','const keep=receiver.keep;return __cellData;');
    for (let i=0;i<8;++i) equalBinding(ownReader(bindingAnchor),cellObject2,'fresh global reader before growth');
    for (let i=0;i<64;++i) globalThis['__cellProperty'+round+'_'+i]=i;
    equalBinding(ownReader(bindingAnchor),cellObject2,'global buffer relocation');
    const lexReader=new Function('receiver','const keep=receiver.keep;return __idxMutable;');
    for (let i=0;i<8;++i) equalBinding(lexReader(bindingAnchor),99,'fresh lexical reader before growth');
    std.evalScript(Array.from({length:48},(_,i)=>'let __cellLexical'+round+'_'+i+'='+i+';').join(''));
    equalBinding(lexReader(bindingAnchor),99,'lexical buffer relocation');
    std.gc();
    equalBinding(ownReader(bindingAnchor),cellObject2,'borrowed cell under GC');
}
for (let i=0;i<96;++i) {
    const value=[i,String(i),Symbol.for('cell'+i),{i},globalThis][i%5];
    globalThis.__cellData=value;
    equalBinding(readOwnCell(bindingAnchor),value,'current value type replacement');
    equalBinding(readIndexedBindings(bindingAnchor)[2],bindingSymbol,'lexical identity under global replacement');
}
Object.defineProperty(globalThis,'__cellData',{value:99,writable:false,configurable:false});
equalBinding(readOwnCell(bindingAnchor),99,'descriptor flag change');
let cellReadonlyError;
try { std.evalScript('"use strict";__cellData=100;'); } catch(e) {cellReadonlyError=e;}
equalBinding(cellReadonlyError instanceof TypeError,true,'readonly write');
equalBinding(readOwnCell(bindingAnchor),99,'readonly value unchanged');
globalThis.__cellShadow=13;
function readCellShadow(receiver) { const keep=receiver.keep; return __cellShadow; }
for(let i=0;i<16;++i)equalBinding(readCellShadow(bindingAnchor),13,'global own before lexical shadow');
std.evalScript('let __cellShadow="lexical";');
for(let i=0;i<16;++i)equalBinding(readCellShadow(bindingAnchor),'lexical','lexical shadow invalidation');
equalBinding(std.evalScript('delete __cellShadow;'),false,'lexical binding remains undeletable');
print('BINDING_CELL_SEMANTICS_OK '+bindingChecks);

let relinkChecks = 0;
function checkRelink(actual, expected, label) {
    ++relinkChecks;
    if (actual !== expected) throw Error(label + ': ' + String(actual));
}
const relinkReceiver = {keep: 1};
// The first property access creates the existing IC slab before the lazy
// builtin is read. Its initialization must not change the returned value.
function readLazyRelink(receiver) { const keep=receiver.keep; return WeakSet; }
const lazyRelink = readLazyRelink(relinkReceiver);
for (let i=0;i<40;++i) checkRelink(readLazyRelink(relinkReceiver),lazyRelink,'lazy builtin identity');
globalThis.__relinkValue=11;
function readRelink(receiver) { const keep=receiver.keep; return __relinkValue; }
for (let i=0;i<40;++i) checkRelink(readRelink(relinkReceiver),11,'initial own data');
for (let round=0;round<8;++round) {
    const first={round,phase:'getter'};
    const second={round,phase:'replacement'};
    Object.defineProperty(globalThis,'__relinkValue',{configurable:true,get(){
        // The generic read reenters JS and relocates both global buffers.
        for(let i=0;i<96;++i)globalThis['__relinkGrowth'+round+'_'+i]=i;
        std.evalScript(Array.from({length:32},(_,i)=>'let __relinkLex'+round+'_'+i+'='+i+';').join(''));
        Object.defineProperty(globalThis,'__relinkValue',{configurable:true,writable:true,value:second});
        std.gc();
        return first;
    }});
    checkRelink(readRelink(relinkReceiver),first,'return original getter result');
    for(let i=0;i<32;++i)checkRelink(readRelink(relinkReceiver),second,'relearn replacement after reentry');
    globalThis.__relinkValue=round;
    checkRelink(readRelink(relinkReceiver),round,'current cell after assignment');
}
delete globalThis.__relinkValue;
let relinkException;
try { readRelink(relinkReceiver); } catch(e) { relinkException=e; }
checkRelink(relinkException instanceof ReferenceError,true,'deleted binding exception');
globalThis.__relinkValue=99;
for(let i=0;i<32;++i)checkRelink(readRelink(relinkReceiver),99,'recreated binding after exception');
print('BINDING_RELINK_OK '+relinkChecks);
`);
