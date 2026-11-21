/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: __dirname,
  },
  async rewrites() {
    const target = process.env.API_INTERNAL_BASE_URL;
    return target
      ? [{ source: "/api/v1/:path*", destination: `${target}/api/v1/:path*` }]
      : [];
  },
};

module.exports = nextConfig;
