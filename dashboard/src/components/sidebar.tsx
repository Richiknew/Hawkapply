"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Briefcase,
  BarChart3,
  Zap,
  FileText,
  Star,
  Bird,
} from "lucide-react";
import { cn } from "@/lib/utils";

const links = [
  { href: "/jobs", label: "Jobs", icon: Briefcase },
  { href: "/matches", label: "Matches", icon: Star },
  { href: "/pipeline", label: "Pipeline", icon: Zap },
  { href: "/stats", label: "Stats", icon: BarChart3 },
  { href: "/resume", label: "Resume", icon: FileText },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-56 flex-col border-r bg-sidebar px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2">
        <Bird className="h-6 w-6 text-primary" />
        <span className="text-lg font-semibold tracking-tight">HawkApply</span>
      </div>

      <nav className="flex flex-col gap-1">
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname.startsWith(href)
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
