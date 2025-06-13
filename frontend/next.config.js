/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    // This is required to work with the standalone output
    outputFileTracingRoot: undefined,
  },
}

module.exports = nextConfig