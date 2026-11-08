import type { NextConfig } from 'next';
const config: NextConfig = {
  // Keep the development badge from covering the bottom-left replay button.
  devIndicators: false,
  async rewrites() {
    // Vercel Services owns /api routing in production. Keep the localhost proxy
    // for local development only; cloud requests must not target loopback.
    if (process.env.VERCEL) return [];
    return [{ source: '/api/:path*', destination: `${process.env.BACKEND_URL || 'http://127.0.0.1:8000'}/api/:path*` }];
  }
};
export default config;
