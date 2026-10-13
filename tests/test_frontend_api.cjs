const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../app/static/app.js'), 'utf8');
const apiSource = source.slice(source.indexOf('async function api('), source.indexOf('\nfunction showAuth('));
function client(response) {
  const context = vm.createContext({
    FormData, user: { csrf: 'test' }, fetch: async () => response,
    showAuth: () => { context.loggedOut = true; },
  });
  vm.runInContext(apiSource, context);
  return context;
}
test('plain-text server errors produce a readable message', async () => {
  const context = client(new Response('Internal Server Error', { status: 500 }));
  await assert.rejects(context.api('/auth/me'), /could not be completed \(HTTP 500\)/);
});
test('field validation messages remain visible', async () => {
  const context = client(Response.json({ details: [{ field: 'timezone', message: 'Enter a full time zone' }] }, { status: 422 }));
  await assert.rejects(context.api('/auth/me'), /timezone: Enter a full time zone/);
});
test('expired sessions are handled even when the response is not JSON', async () => {
  const context = client(new Response('Unauthorized', { status: 401 }));
  await assert.rejects(context.api('/auth/me'), /HTTP 401/);
  assert.equal(context.loggedOut, true);
});
test('successful empty responses do not require JSON', async () => {
  assert.equal(await client(new Response(null, { status: 204 })).api('/auth/logout'), null);
});

test('HTTP status is retained for choosing the recovery screen', async () => {
  const context = client(Response.json({ error: 'Record not found' }, { status: 404 }));
  await assert.rejects(context.api('/applications/99'), (error) => error.status === 404);
});
test('network failures are distinguished from server errors', async () => {
  const context = client(null);
  context.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(context.api('/dashboard'), (error) => error.status === 0 && /connect/.test(error.message));
});
const routeContext = vm.createContext({});
vm.runInContext(source.slice(source.indexOf('function errorPage('), source.indexOf('async function route()')), routeContext);
test('unknown and malformed routes do not fall back to the dashboard', () => {
  for (const route of ['missing', 'toString', '__proto__', 'application', 'application/0', 'application/nope', 'application/1/extra', 'settings/extra']) {
    assert.equal(routeContext.validRoute(route), false, route);
  }
  for (const route of ['dashboard', 'applications', 'application/1', 'settings', 'resumes']) {
    assert.equal(routeContext.validRoute(route), true, route);
  }
});
test('recovery screens offer appropriate actions', () => {
  assert.match(routeContext.errorPage(404, true), /RECORD NOT FOUND/);
  assert.doesNotMatch(routeContext.errorPage(404), /data-retry/);
  assert.match(routeContext.errorPage(0), /CONNECTION INTERRUPTED/);
  assert.match(routeContext.errorPage(500), /data-retry/);
  assert.match(routeContext.errorPage(403), /ACCESS RESTRICTED/);
});
