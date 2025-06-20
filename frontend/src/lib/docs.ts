import fs from 'fs'
import path from 'path'
import matter from 'gray-matter'
import { remark } from 'remark'
import html from 'remark-html'

export interface DocMeta {
  title: string
  description: string
}

export interface DocSection {
  title: string
  slug: string
  items: DocItem[]
}

export interface DocItem {
  title: string
  slug: string
  href: string
}

export const docSections: DocSection[] = [
  {
    title: 'Documentation',
    slug: 'docs',
    items: [
      { title: 'Overview', slug: 'overview', href: '/docs' },
      { title: 'AWS Setup', slug: 'aws-setup', href: '/docs/aws-setup' },
    ]
  }
]

export async function getDocBySlug(slug: string): Promise<{ meta: DocMeta; content: string } | null> {
  try {
    const docsDirectory = path.join(process.cwd(), 'src/content/docs')
    const realSlug = slug === '' ? 'index' : slug
    const fullPath = path.join(docsDirectory, `${realSlug}.md`)
    
    if (!fs.existsSync(fullPath)) {
      return null
    }
    
    const fileContents = fs.readFileSync(fullPath, 'utf8')
    const { data, content } = matter(fileContents)
    
    // Process markdown content to HTML
    const processedContent = await remark()
      .use(html, { sanitize: false })
      .process(content)
    const contentHtml = processedContent.toString()
    
    return {
      meta: data as DocMeta,
      content: contentHtml
    }
  } catch (error) {
    console.error('Error reading doc:', error)
    return null
  }
}