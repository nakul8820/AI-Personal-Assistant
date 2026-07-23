/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const backendUrl = process.env.BACKEND_API_URL || 'http://backend:8000';
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
