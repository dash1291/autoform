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

async function processDynamicContent(content: string): Promise<string> {
  // Replace {{include-json:path}} with the JSON file content
  const jsonIncludeRegex = /\{\{include-json:(.*?)\}\}/g;
  
  let processedContent = content;
  const matches = content.match(jsonIncludeRegex);
  
  if (matches) {
    for (const match of matches) {
      const pathMatch = match.match(/\{\{include-json:(.*?)\}\}/);
      if (pathMatch) {
        const relativePath = pathMatch[1].trim();
        try {
          // Resolve path relative to project root
          const absolutePath = path.join(process.cwd(), '..', relativePath);
          
          if (fs.existsSync(absolutePath)) {
            const jsonContent = fs.readFileSync(absolutePath, 'utf8');
            // Format JSON for display in markdown
            const formattedJson = '```json\n' + JSON.stringify(JSON.parse(jsonContent), null, 2) + '\n```';
            processedContent = processedContent.replace(match, formattedJson);
          } else {
            console.warn(`JSON file not found: ${absolutePath}`);
            processedContent = processedContent.replace(match, `<!-- Error: File not found: ${relativePath} -->`);
          }
        } catch (error) {
          console.error(`Error processing JSON file ${relativePath}:`, error);
          processedContent = processedContent.replace(match, `<!-- Error processing file: ${relativePath} -->`);
        }
      }
    }
  }
  
  return processedContent;
}

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
    
    // Process dynamic content first (e.g., JSON file inclusions)
    const dynamicContent = await processDynamicContent(content)
    
    // Process markdown content to HTML
    const processedContent = await remark()
      .use(html, { sanitize: false })
      .process(dynamicContent)
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