/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const rawUrl = process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_API_URL;
    if (!rawUrl) return [];
    const backendUrl = rawUrl.replace(/\/+$/, '');
    return [
      {
        source: '/auth/:path*',
        destination: `${backendUrl}/auth/:path*`,
      },
      {
        source: '/chat/:path*',
        destination: `${backendUrl}/chat/:path*`,
      },
      {
        source: '/voice/:path*',
        destination: `${backendUrl}/voice/:path*`,
      },
    ];
  },
};
