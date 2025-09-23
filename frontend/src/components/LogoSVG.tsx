"use client";

import { useEffect, useState } from "react";

interface LogoSVGProps {
  className?: string;
  color?: string;
}

export function LogoSVG({ className = "h-8 w-8" }: LogoSVGProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // For now, let's just use the img tag with CSS filters
    setIsLoading(false);
  }, []);

  if (error) {
    console.error("Logo error:", error);
    return null;
  }

  // Simple approach: use img tag with CSS filters to make it white
  return (
    <img
      src="/logo.png"
      alt="Autoform Logo"
      className={className}
      style={{
        //filter: 'brightness(0) invert(1)',
        display: isLoading ? "none" : "block",
      }}
      onError={() => setError("Failed to load logo")}
      onLoad={() => setIsLoading(false)}
    />
  );
}
