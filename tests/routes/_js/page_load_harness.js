const fs = require('fs');
const [, , htmlPath] = process.argv;
const html = fs.readFileSync(htmlPath, 'utf8');
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map((m) => m[1]));

const el = () => new Proxy(function () {}, {
  get(t, k) {
    if (k === 'style' || k === 'classList' || k === 'dataset' || k === 'cookies') return el();
    if (k === 'options' || k === 'selectedOptions' || k === 'children') return [];
    if (k === 'value' || k === 'textContent' || k === 'innerHTML' || k === 'title') return '';
    if (k === Symbol.toPrimitive || k === 'toString') return () => '';
    if (k === 'then') return undefined;
    return el();
  },
  set: () => true,
  apply: () => el(),
  has: () => true,
});

const doc = {
  getElementById: (id) => (ids.has(id) ? el() : null),
  querySelector: () => el(),
  querySelectorAll: () => [],
  createElement: () => el(),
  addEventListener: () => {},
  dispatchEvent: () => {},
  documentElement: el(),
  body: el(),
  head: el(),
  cookie: '',
};
globalThis.document = doc;
globalThis.window = globalThis;
globalThis.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
globalThis.fetch = () => new Promise(() => {});
globalThis.location = { search: '', hash: '', href: '', pathname: '/' };
globalThis.history = { replaceState: () => {}, pushState: () => {} };
globalThis.matchMedia = () => ({ matches: false, addEventListener: () => {} });
globalThis.navigator = { clipboard: { writeText: () => Promise.resolve() } };
globalThis.CustomEvent = class {};
globalThis.alert = () => {};
globalThis.confirm = () => false;
globalThis.prompt = () => null;
globalThis.requestAnimationFrame = () => 0;
globalThis.setInterval = () => 0;
globalThis.setTimeout = () => 0;

const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
for (const src of scripts) {
  try {
    new Function(src)();
  } catch (err) {
    if (err instanceof TypeError && /null|undefined/.test(err.message)) {
      console.log('LOAD-ERROR ' + err.message);
      const m = /<anonymous>:(\d+):/.exec(err.stack || '');
      if (m) console.log('SRC: ' + (src.split(String.fromCharCode(10))[Number(m[1]) - 3] || '').trim());
      process.exit(1);
    }
  }
}
console.log('OK');
