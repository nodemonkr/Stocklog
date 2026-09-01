import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const projectRoot = path.resolve(__dirname, '..')
const rootEnvPath = path.join(projectRoot, '.env')
const stocklogEnvPath = path.join(projectRoot, 'stocklog.env')
const versionPath = path.join(projectRoot, 'VERSION')
const stocklogVersion = fs.existsSync(versionPath)
  ? fs.readFileSync(versionPath, 'utf8').trim()
  : '0.0.0-dev'

function parseSimpleEnvFile(filePath) {
  const result = {}

  if (!fs.existsSync(filePath)) return result

  const raw = fs.readFileSync(filePath, 'utf8')

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim()

    if (!trimmed || trimmed.startsWith('#')) continue

    const index = trimmed.indexOf('=')

    if (index <= 0) continue

    const key = trimmed.slice(0, index).trim()
    let value = trimmed.slice(index + 1).trim()

    if (
      (value.startsWith('"') && value.endsWith('"'))
      || (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }

    result[key] = value
  }

  return result
}

function normalizeHost(value) {
  const raw = String(value || '').trim()

  if (!raw) return ''

  try {
    const withScheme = raw.includes('://')
      ? raw
      : `http://${raw}`

    return new URL(withScheme).hostname
  } catch {
    return raw
      .replace(/^https?:\/\//i, '')
      .replace(/\/.*$/, '')
      .replace(/:\d+$/, '')
      .trim()
  }
}

function splitHosts(value) {
  return String(value || '')
    .split(',')
    .map(normalizeHost)
    .filter(Boolean)
}

function normalizeProxyIp(value) {
  const raw = String(value || '').trim().replace(/^\[|\]$/g, '')
  if (raw.startsWith('::ffff:')) return raw.slice(7)
  return raw
}

function isLoopbackIp(value) {
  const ip = normalizeProxyIp(value)
  return ip === '127.0.0.1' || ip === '::1'
}

export function trustedProxyClientIp(req) {
  const peer = normalizeProxyIp(req?.socket?.remoteAddress)
  const forwarded = String(req?.headers?.['x-forwarded-for'] || '')
    .split(',')
    .map(normalizeProxyIp)
    .filter(Boolean)
  // Only a local reverse proxy (for example Caddy) may provide the original
  // client chain. Direct remote callers cannot override their socket address
  // with a forged X-Forwarded-For header.
  // The nearest proxy appends the address it actually accepted. Reading the
  // last hop prevents a caller-provided first X-Forwarded-For value from being
  // mistaken for the real client address.
  return isLoopbackIp(peer) && forwarded.length
    ? forwarded[forwarded.length - 1]
    : peer
}

function secureProxyHeaders(proxy) {
  const apply = (proxyReq, req) => {
    const clientIp = trustedProxyClientIp(req)
    proxyReq.removeHeader('Forwarded')
    proxyReq.setHeader('X-Forwarded-For', clientIp)
    proxyReq.setHeader('X-Real-IP', clientIp)
  }
  proxy.on('proxyReq', apply)
  proxy.on('proxyReqWs', apply)
}

export function isHtmlDocumentRequest(req) {
  const method = String(req?.method || 'GET').toUpperCase()

  if (method !== 'GET' && method !== 'HEAD') return false

  let pathname = '/'

  try {
    pathname = new URL(String(req?.url || '/'), 'http://stocklog.local').pathname
  } catch {
    return false
  }

  if (
    pathname === '/health'
    || pathname.startsWith('/api/')
    || pathname.startsWith('/ws')
    || pathname.startsWith('/assets/')
    || pathname.startsWith('/@')
    || pathname.startsWith('/src/')
    || pathname.startsWith('/node_modules/')
  ) return false

  const lastSegment = pathname.split('/').filter(Boolean).at(-1) || ''
  const acceptsHtml = String(req?.headers?.accept || '').includes('text/html')
  const isNavigation = String(req?.headers?.['sec-fetch-mode'] || '') === 'navigate'

  // Root, explicit HTML, and extensionless SPA routes are documents even when
  // a client omits the Accept header.
  return acceptsHtml
    || isNavigation
    || pathname === '/'
    || pathname.endsWith('.html')
    || !lastSegment.includes('.')
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

export function stocklogAccessBlockHtml({ clientIp, unavailable = false } = {}) {
  const title = unavailable ? '접속 정책을 확인할 수 없습니다' : '접속이 허용되지 않았습니다'
  const description = unavailable
    ? '보안을 위해 로그인 화면을 열지 않았습니다. 잠시 후 다시 시도해주세요.'
    : '관리자가 허용한 IP에서만 StockLog를 사용할 수 있습니다.'
  const safeIp = escapeHtml(clientIp || '확인 불가')

  return `<!doctype html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockLog 접속 제한</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:24px;background:#f4f7fb;color:#172033;font-family:Inter,Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.card{width:min(100%,520px);padding:34px;border:1px solid #dce4ef;border-radius:22px;background:#fff;box-shadow:0 18px 55px rgba(28,48,84,.1)}.brand{margin:0 0 22px;color:#4b65d8;font-size:12px;font-weight:800;letter-spacing:.16em}.icon{display:grid;place-items:center;width:46px;height:46px;margin-bottom:18px;border-radius:14px;background:#fff0f1;color:#e23d4d;font-size:23px;font-weight:900}h1{margin:0 0 10px;font-size:25px;line-height:1.25}p{margin:0;color:#65738c;font-size:15px;line-height:1.7}.ip{display:flex;justify-content:space-between;gap:18px;margin-top:24px;padding:14px 16px;border-radius:13px;background:#f6f8fc;color:#526078;font-size:13px}.ip b{color:#1f2a40;overflow-wrap:anywhere}button{width:100%;margin-top:22px;padding:13px;border:0;border-radius:12px;background:#263b78;color:#fff;font:inherit;font-weight:750;cursor:pointer}
</style></head><body><main class="card"><div class="brand">STOCKLOG SECURITY</div><div class="icon">!</div><h1>${title}</h1><p>${description}</p><div class="ip"><span>현재 접속 IP</span><b>${safeIp}</b></div><button type="button" onclick="location.reload()">다시 확인</button></main></body></html>`
}

async function probeSiteAccess(backendHttp, clientIp) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 4000)

  try {
    const response = await fetch(`${backendHttp}/api/access/status`, {
      headers: {
        'X-Forwarded-For': clientIp,
        'X-Real-IP': clientIp,
      },
      cache: 'no-store',
      signal: controller.signal,
    })

    if (!response.ok) throw new Error(`access status ${response.status}`)

    return await response.json()
  } finally {
    clearTimeout(timeout)
  }
}

export function createStocklogHtmlAccessGate(backendHttp, accessProbe = probeSiteAccess) {
  return {
    name: 'stocklog-html-access-gate',
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        if (!isHtmlDocumentRequest(req)) {
          next()
          return
        }

        const clientIp = trustedProxyClientIp(req)

        try {
          const status = await accessProbe(backendHttp, clientIp)

          if (status?.allowed === true) {
            next()
            return
          }

          res.statusCode = 403
          res.setHeader('X-StockLog-Access', 'denied')
          res.setHeader('Cache-Control', 'no-store')
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
          res.end(req.method === 'HEAD' ? '' : stocklogAccessBlockHtml({ clientIp: status?.client_ip || clientIp }))
        } catch {
          // Policy verification is a security boundary. If the backend cannot
          // answer, do not fall through to the React login document.
          res.statusCode = 503
          res.setHeader('X-StockLog-Access', 'unavailable')
          res.setHeader('Cache-Control', 'no-store')
          res.setHeader('Retry-After', '5')
          res.setHeader('Content-Type', 'text/html; charset=utf-8')
          res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
          res.end(req.method === 'HEAD' ? '' : stocklogAccessBlockHtml({ clientIp, unavailable: true }))
        }
      })
    },
  }
}

export default defineConfig(() => {
  // Root .env is primary. stocklog.env remains a compatibility fallback.
  const legacyEnv = parseSimpleEnvFile(stocklogEnvPath)
  const rootEnv = parseSimpleEnvFile(rootEnvPath)
  const fileEnv = {
    ...legacyEnv,
    ...rootEnv,
  }

  const publicHost = normalizeHost(
    process.env.STOCKLOG_PUBLIC_HOST
    || fileEnv.STOCKLOG_PUBLIC_HOST
  )

  const configuredHosts = [
    ...splitHosts(
      process.env.STOCKLOG_ALLOWED_HOSTS
      || fileEnv.STOCKLOG_ALLOWED_HOSTS
    ),
    ...splitHosts(
      process.env.__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS
    ),
    publicHost,
  ].filter(Boolean)

  const allowedHosts = [
    ...new Set(configuredHosts),
  ]

  const frontendPort = Number(
    process.env.STOCKLOG_FRONTEND_PORT
    || fileEnv.STOCKLOG_FRONTEND_PORT
    || 5174
  )

  const backendPort = Number(
    process.env.STOCKLOG_BACKEND_PORT
    || fileEnv.STOCKLOG_BACKEND_PORT
    || 8100
  )

  const backendHttp = `http://127.0.0.1:${backendPort}`
  const backendWs = `ws://127.0.0.1:${backendPort}`

  console.log(
    '[VITE] allowedHosts:',
    allowedHosts.length
      ? allowedHosts.join(', ')
      : '(DDNS 미설정)'
  )
  console.log(
    `[VITE] same-origin proxy: /api,/ws -> backend ${backendPort}`
  )

  return {
    plugins: [createStocklogHtmlAccessGate(backendHttp), react()],
    define: {
      __STOCKLOG_VERSION__: JSON.stringify(stocklogVersion),
    },

    // Production bundles intentionally omit source maps so internal
    // implementation details are not exposed through browser devtools.
    build: {
      sourcemap: false,
    },

    server: {
      host: '0.0.0.0',
      port: frontendPort,
      strictPort: true,
      allowedHosts,

      // The browser only talks to the Vite port.
      // Router example:
      // external :3000 -> 192.168.0.200:5174
      //
      // API and WebSocket are forwarded internally to :8100, therefore
      // the backend port does NOT need to be exposed to the internet.
      proxy: {
        '/api': {
          target: backendHttp,
          changeOrigin: false,
          secure: false,
          configure: secureProxyHeaders,
        },

        '/health': {
          target: backendHttp,
          changeOrigin: false,
          secure: false,
          configure: secureProxyHeaders,
        },

        '/ws': {
          target: backendWs,
          ws: true,
          changeOrigin: false,
          configure: secureProxyHeaders,
        },
      },

      headers: {
        'Cache-Control':
          'no-store, no-cache, must-revalidate, proxy-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    },
  }
})
