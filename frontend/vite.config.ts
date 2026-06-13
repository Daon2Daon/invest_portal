import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// 프로덕션 빌드 시 base='/static/ui/' (FastAPI가 /static/ui/로 정적 서빙).
// dev 서버에서는 '/'로 두고 /api 요청을 백엔드(8000)로 프록시한다.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'build' ? '/static/ui/' : '/',
  build: {
    outDir: path.resolve(__dirname, '../app/static/ui'),
    emptyOutDir: true,
  },
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
}))
