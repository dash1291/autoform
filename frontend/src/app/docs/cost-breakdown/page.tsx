import { getDocBySlug } from "@/lib/docs";
import { notFound } from "next/navigation";
import AuthGuard from "@/components/AuthGuard";
import DocsContentWrapper from "@/components/DocsContentWrapper";

export default async function CostBreakdownPage() {
  const doc = await getDocBySlug("cost-breakdown");

  if (!doc) {
    notFound();
  }

  return (
    <AuthGuard>
      <DocsContentWrapper content={doc.content} />
    </AuthGuard>
  );
}

export const metadata = {
  title: "AWS Cost Breakdown - Autoform Documentation",
  description:
    "Understand the costs of resources created by Autoform deployments",
};
