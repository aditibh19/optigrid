// The browser talks only to this Next.js server; /api/* is proxied to the
// FastAPI backend, so no CORS setup is needed. Point BACKEND_URL elsewhere
// (e.g. a deployed API) with:  BACKEND_URL=https://api.example.com npm run dev
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // The policy simulator can take a while on a cold policy cache; the default
  // proxy timeout (30 s) would cut it off with a 500.
  experimental: { proxyTimeout: 300_000 },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` },
      { source: "/backend-health", destination: `${BACKEND_URL}/health` },
    ];
  },
};

export default nextConfig;
