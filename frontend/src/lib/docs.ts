import fs from "fs";
import path from "path";
import matter from "gray-matter";
import { remark } from "remark";
import html from "remark-html";
import gfm from "remark-gfm";

export interface DocMeta {
  title: string;
  description: string;
}

export interface DocSection {
  title: string;
  slug: string;
  items: DocItem[];
}

export interface DocItem {
  title: string;
  slug: string;
  href: string;
}

export const docSections: DocSection[] = [
  {
    title: "Documentation",
    slug: "docs",
    items: [
      { title: "Overview", slug: "overview", href: "/docs" },
      { title: "AWS Setup", slug: "aws-setup", href: "/docs/aws-setup" },
    ],
  },
];

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
          // Always read from public directory
          const publicPath = path.join(
            process.cwd(),
            "public",
            "aws-iam-policy.json",
          );

          if (fs.existsSync(publicPath)) {
            const jsonContent = fs.readFileSync(publicPath, "utf8");
            // Format JSON for display in markdown with copy button HTML
            // Escape the JSON content for HTML attributes
            const escapedJsonContent = jsonContent
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#39;");
            const copyButtonHtml = `<div class="copy-button-container mb-4"><button class="copy-policy-btn bg-white border border-gray-300 rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500" data-copy-content="${escapedJsonContent}"><svg class="copy-icon h-4 w-4 mr-2 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"></path></svg>Copy Policy</button></div>`;
            // Create HTML directly to ensure proper formatting is preserved
            const formattedJson =
              copyButtonHtml +
              '\n\n<pre><code class="language-json">' +
              jsonContent.trim() +
              "</code></pre>\n\n";
            processedContent = processedContent.replace(match, formattedJson);
          } else {
            console.warn(`JSON file not found: ${publicPath}`);
            processedContent = processedContent.replace(
              match,
              `<!-- Error: File not found: aws-iam-policy.json -->`,
            );
          }
        } catch (error) {
          console.error(`Error processing JSON file ${relativePath}:`, error);
          processedContent = processedContent.replace(
            match,
            `<!-- Error processing file: ${relativePath} -->`,
          );
        }
      }
    }
  }

  return processedContent;
}

export async function getDocBySlug(
  slug: string,
): Promise<{ meta: DocMeta; content: string } | null> {
  try {
    const docsDirectory = path.join(process.cwd(), "src/content/docs");
    const realSlug = slug === "" ? "index" : slug;
    const fullPath = path.join(docsDirectory, `${realSlug}.md`);

    if (!fs.existsSync(fullPath)) {
      return null;
    }

    const fileContents = fs.readFileSync(fullPath, "utf8");
    const { data, content } = matter(fileContents);

    // Process dynamic content first (e.g., JSON file inclusions)
    const dynamicContent = await processDynamicContent(content);

    // Process markdown content to HTML
    const processedContent = await remark()
      .use(gfm)
      .use(html, { sanitize: false })
      .process(dynamicContent);
    const contentHtml = processedContent.toString();

    return {
      meta: data as DocMeta,
      content: contentHtml,
    };
  } catch (error) {
    console.error("Error reading doc:", error);
    return null;
  }
}
