/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  pageExtensions: ['ts', 'tsx', 'js', 'jsx', 'md', 'mdx'],
  experimental: {
    // This is required to work with the standalone output
    outputFileTracingRoot: undefined,
  },
}

module.exports = nextConfig