const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const { webcrypto } = require('node:crypto');

function setup() {
  const data = {};
  const listeners = {};
  let available = false;
  const nativeEvents = [];
  const event = key => ({ addListener(callback) { listeners[key] = callback; } });
  const chrome = {
    storage: { local: {
      async get(keys) { const list = Array.isArray(keys) ? keys : [keys]; return structuredClone(Object.fromEntries(list.filter(k => k in data).map(k => [k, data[k]]))); },
      async set(update) { Object.assign(data, structuredClone(update)); }
    } },
    runtime: {
      onMessage: event('message'), onStartup: event('startup'),
      async sendNativeMessage(host, payload) { if (!available) throw new Error('Offline PC'); nativeEvents.push(payload); return { saved_locally: true }; }
    },
    tabs: { onRemoved: event('removed'), async sendMessage() {} },
    alarms: { create() {}, onAlarm: event('alarm') }
  };
  const context = vm.createContext({ chrome, URL, TextEncoder, crypto: webcrypto, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../tools/browser-ai-capture/background.js'), 'utf8'), context);
  const call = (message, sender = {}) => new Promise(resolve => listeners.message(message, sender, resolve));
  const drain = () => vm.runInContext('operations', context);
  return { data, listeners, call, drain, nativeEvents, online() { available = true; } };
}

const URL_CHAT = 'https://chatgpt.com/c/mirroried-example';
const sender = { tab: { id: 7 }, frameId: 0, url: URL_CHAT };
const snapshot = { type: 'checkpoint', title: 'Mirroried LED work', snapshot_id: 'a'.repeat(64), part: 0, parts: 1,
  messages: [{ role: 'assistant', text: 'Completed website work', message_index: 0, offset: 0 }] };

test('untracked chats and unrelated sites cannot be forwarded to the PC', async () => {
  const state = setup();
  assert.equal((await state.call(snapshot, sender)).tracking, false);
  assert.equal(state.data.pending, undefined);
  assert.ok((await state.call(snapshot, { ...sender, url: 'https://unrelated.example/chat' })).error);
});

test('an offline native host retains the checkpoint and tab-close event', async () => {
  const state = setup();
  await state.call({ type: 'toggle', url: URL_CHAT, tabId: 7 });
  assert.equal((await state.call(snapshot, sender)).queued, true);
  state.listeners.removed(7);
  await state.drain();
  const queued = Object.values(state.data.pending);
  assert.equal(queued.length, 2);
  assert.ok(queued.some(x => x.event === 'tab_closed'));
  assert.ok(queued.some(x => x.messages[0]?.text === 'Completed website work'));
});

test('restart retries remove only checkpoints acknowledged by the native host', async () => {
  const state = setup();
  await state.call({ type: 'toggle', url: URL_CHAT, tabId: 7 });
  await state.call(snapshot, sender);
  state.online();
  state.listeners.startup();
  await state.drain();
  assert.equal(Object.keys(state.data.pending).length, 0);
  assert.equal(state.nativeEvents.length, 1);
  assert.ok(state.data.lastLocalSave);
});

test('concurrent parts are serialized without losing either checkpoint', async () => {
  const state = setup();
  await state.call({ type: 'toggle', url: URL_CHAT, tabId: 7 });
  await Promise.all([state.call(snapshot, sender), state.call({ ...snapshot, part: 1, parts: 2 }, sender)]);
  assert.equal(Object.keys(state.data.pending).length, 2);
});

test('content scripts cannot change tracking settings or request native status', async () => {
  const state = setup();
  assert.ok((await state.call({ type: 'toggle', url: URL_CHAT, tabId: 7 }, sender)).error);
  assert.ok((await state.call({ type: 'status', url: URL_CHAT }, sender)).error);
});

test('browser queue preserves delta chains and rejects invalid replacements', async () => {
  const state = setup();
  await state.call({ type: 'toggle', url: URL_CHAT, tabId: 7 });
  const delta = { ...snapshot, checkpoint_mode: 'delta', base_snapshot_id: 'b'.repeat(64), message_count: 1,
    messages: [{ role: 'assistant', text: 'new', message_index: 0, offset: 4, replace_from: 4, final_length: 7 }] };
  assert.equal((await state.call(delta, sender)).queued, true);
  const queued = Object.values(state.data.pending)[0];
  assert.equal(queued.checkpoint_mode, 'delta');
  assert.equal(queued.base_snapshot_id, delta.base_snapshot_id);
  assert.equal(queued.messages[0].replace_from, 4);
  assert.ok((await state.call({ ...delta, messages: [{ ...delta.messages[0], final_length: 1 }] }, sender)).error);
  assert.equal(Object.keys(state.data.pending).length, 1);
});

async function contentSetup() {
  const chat = [{ role: 'user', text: 'Earlier website discussion' }, { role: 'assistant', text: 'Answer' }];
  const clock = { value: 100000 };
  const saved = [];
  class Clock extends Date { static now() { return clock.value; } }
  const location = { href: URL_CHAT };
  const document = { documentElement: {}, title: 'Website task', addEventListener() {},
    querySelectorAll() { return chat.map(message => ({ dataset: { messageAuthorRole: message.role }, innerText: message.text, contains() { return false; } })); } };
  const chrome = { runtime: { onMessage: { addListener() {} }, async sendMessage(message) {
    if (message.type === 'trackingState') return { tracking: true };
    saved.push(structuredClone(message)); return { queued: true };
  } } };
  const context = vm.createContext({ chrome, location, document, Date: Clock, TextEncoder, crypto: webcrypto,
    MutationObserver: class { observe() {} }, window: { addEventListener() {} }, setTimeout() {}, clearTimeout() {}, setInterval() {} });
  await vm.runInContext(fs.readFileSync(path.join(__dirname, '../tools/browser-ai-capture/content.js'), 'utf8'), context);
  return { chat, clock, saved, checkpoint: force => context.checkpoint(force), location };
}

test('streaming is throttled and only the changed suffix is queued', async () => {
  const state = await contentSetup();
  const first = state.saved[0];
  assert.equal(first.checkpoint_mode, 'full');
  state.chat[1].text += ' more';
  state.clock.value += 10000;
  await state.checkpoint();
  assert.equal(state.saved.length, 1);
  state.clock.value += 20000;
  await state.checkpoint();
  const delta = state.saved[1];
  assert.equal(delta.checkpoint_mode, 'delta');
  assert.equal(delta.base_snapshot_id, first.snapshot_id);
  assert.equal(delta.messages.length, 1);
  assert.equal(delta.messages[0].text, ' more');
  assert.equal(delta.messages[0].replace_from, 'Answer'.length);
  const reconstructed = first.messages[1].text.slice(0, delta.messages[0].replace_from) + delta.messages[0].text;
  assert.equal(reconstructed, state.chat[1].text);
});

test('forced and periodic full checkpoints refresh the recoverable base', async () => {
  const state = await contentSetup();
  state.chat[1].text = 'Edited final reply';
  await state.checkpoint(true);
  assert.equal(state.saved[1].checkpoint_mode, 'full');
  assert.equal(state.saved[1].base_snapshot_id, null);
  await state.checkpoint(true);
  assert.equal(state.saved.length, 2);
  state.chat[1].text += ' and later update';
  state.clock.value += 10 * 60 * 1000;
  await state.checkpoint();
  assert.equal(state.saved[2].checkpoint_mode, 'full');
});

test('emoji edits and long-message fragments preserve complete Unicode characters', async () => {
  const state = await contentSetup();
  state.chat[1].text = '🙂';
  await state.checkpoint(true);
  state.chat[1].text = '🙃';
  state.clock.value += 30000;
  await state.checkpoint();
  assert.equal(state.saved.at(-1).messages[0].text, '🙃');
  state.chat[1].text = 'x'.repeat(49999) + '🙂end';
  await state.checkpoint(true);
  const fragments = state.saved.at(-1).messages.filter(message => message.message_index === 1);
  assert.equal(fragments.map(message => message.text).join(''), state.chat[1].text);
  for (const fragment of fragments) assert.equal(Buffer.from(fragment.text, 'utf8').toString('utf8'), fragment.text);
});
