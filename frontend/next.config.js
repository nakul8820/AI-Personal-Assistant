/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    let backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || process.env.BACKEND_API_URL || 'http://backend:8000';
    backendUrl = backendUrl.replace(/\/+$/, '');
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
