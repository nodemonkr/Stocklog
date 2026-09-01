import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createStocklogHtmlAccessGate,
  isHtmlDocumentRequest,
  trustedProxyClientIp,
} from '../vite.config.js'

function request({
  ip = '198.51.100.20',
  url = '/',
  method = 'GET',
  headers = {},
} = {}) {
  return {
    method,
    url,
    headers,
    socket: { remoteAddress: ip },
  }
}

function response() {
  return {
    body: undefined,
    headers: new Map(),
    statusCode: 200,
    setHeader(name, value) {
      this.headers.set(String(name).toLowerCase(), value)
    },
    end(value = '') {
      this.body = value
    },
  }
}

function middlewareFor(accessProbe) {
  let middleware
  const plugin = createStocklogHtmlAccessGate('http://127.0.0.1:8100', accessProbe)
  plugin.configureServer({ middlewares: { use(fn) { middleware = fn } } })
  return middleware
}

test('direct clients cannot forge their IP with X-Forwarded-For', () => {
  const req = request({
    ip: '198.51.100.20',
    headers: { 'x-forwarded-for': '203.0.113.99' },
  })

  assert.equal(trustedProxyClientIp(req), '198.51.100.20')
})

test('a local reverse proxy uses the nearest forwarded client hop', () => {
  const req = request({
    ip: '::ffff:127.0.0.1',
    headers: { 'x-forwarded-for': '203.0.113.99, 198.51.100.42' },
  })

  assert.equal(trustedProxyClientIp(req), '198.51.100.42')
})

test('document requests are gated while API and assets bypass the HTML gate', () => {
  assert.equal(isHtmlDocumentRequest(request({ url: '/' })), true)
  assert.equal(isHtmlDocumentRequest(request({ url: '/?page=smart' })), true)
  assert.equal(isHtmlDocumentRequest(request({ url: '/admin' })), true)
  assert.equal(isHtmlDocumentRequest(request({ url: '/index.html' })), true)
  assert.equal(isHtmlDocumentRequest(request({ url: '/api/auth/login' })), false)
  assert.equal(isHtmlDocumentRequest(request({ url: '/assets/index.js' })), false)
})

test('an unlisted IP receives a server-side 403 document without the React login app', async () => {
  const middleware = middlewareFor(async (_backend, clientIp) => ({
    allowed: false,
    client_ip: clientIp,
  }))
  const req = request({ headers: { accept: 'text/html' } })
  const res = response()
  let nextCalls = 0

  await middleware(req, res, () => { nextCalls += 1 })

  assert.equal(nextCalls, 0)
  assert.equal(res.statusCode, 403)
  assert.equal(res.headers.get('x-stocklog-access'), 'denied')
  assert.match(res.body, /접속이 허용되지 않았습니다/)
  assert.doesNotMatch(res.body, /<input|\/assets\//)
})

test('an allowed IP continues to the StockLog document', async () => {
  const middleware = middlewareFor(async () => ({ allowed: true }))
  const req = request({ headers: { accept: 'text/html' } })
  const res = response()
  let nextCalls = 0

  await middleware(req, res, () => { nextCalls += 1 })

  assert.equal(nextCalls, 1)
  assert.equal(res.statusCode, 200)
  assert.equal(res.body, undefined)
})

test('policy lookup failures fail closed before rendering login', async () => {
  const middleware = middlewareFor(async () => {
    throw new Error('backend unavailable')
  })
  const req = request({ headers: { accept: 'text/html' } })
  const res = response()
  let nextCalls = 0

  await middleware(req, res, () => { nextCalls += 1 })

  assert.equal(nextCalls, 0)
  assert.equal(res.statusCode, 503)
  assert.equal(res.headers.get('x-stocklog-access'), 'unavailable')
  assert.doesNotMatch(res.body, /<input|\/assets\//)
})
