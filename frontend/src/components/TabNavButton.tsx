import React from "react";
import { Button } from "./ui/button";

interface TabNavButtonProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}

export default function TabNavButton({
  active,
  onClick,
  children,
  className = "",
}: TabNavButtonProps) {
  return (
    <Button
      variant="ghost"
      onClick={onClick}
      className={`py-2 px-1 border-b-2 font-medium text-sm rounded-none ${
        active
          ? "border-foreground text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground hover:bg-none"
      } ${className}`}
    >
      {children}
    </Button>
  );
}
