import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { Providers } from '@/components/Providers'
import Navbar from '@/components/Navbar'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'Autoform - Deploy applications to your cloud with ease',
  description: 'An easy-to-use platform to deploy and manage applications on your AWS account with minimal infrastructure knowledge.',
  icons: {
    icon: '/logo.png',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>
          <Navbar />
          <div className="inset-0 pt-16 overflow-y-auto">
            {children}
          </div>
        </Providers>
      </body>
    </html>
  )
}
