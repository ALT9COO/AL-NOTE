/** @type {import('next').NextConfig} */
const nextConfig = {
  experimental: {
    proxyTimeout: 10 * 60 * 1000,
  },
  async rewrites() {
    const api = process.env.ALNOTE_API_ORIGIN ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${api}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
