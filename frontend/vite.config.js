import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src'),
      },
    },
    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern-compiler',
          silenceDeprecations: ['legacy-js-api'],
        }
      }
    },
    optimizeDeps: {
      esbuildOptions: {
        target: 'es2022'
      },
      force: true,
      exclude: ['tree-sitter'],
    },
    build: {
      target: 'es2022',
    },
    server: {
      port: parseInt(env.VITE_FRONTEND_PORT) || 3000,
      host: '0.0.0.0',
      headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
      proxy: {
        '^/api/': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '^/media/': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '^/app-automation-templates/': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '^/api-testing-reports/': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '^/app-automation-reports/': {
          target: env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
          changeOrigin: true,
          secure: false,
        },
        '^/ws/': {
          target: env.VITE_API_BASE_URL ? env.VITE_API_BASE_URL.replace('http', 'ws') : 'ws://127.0.0.1:8000',
          ws: true,
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('error', () => {})
            proxy.on('proxyReqWs', (proxyReq, req, socket) => {
              socket.on('error', () => {})
            })
          },
        },
      },
    },
    assetsInclude: ['**/*.wasm'],
  }
})
