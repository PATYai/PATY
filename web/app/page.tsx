"use client";

import Link from "next/link";
import { useAuth } from "@clerk/nextjs";

export default function Home() {
  const { isSignedIn } = useAuth();

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-white dark:bg-black px-6">
      <main className="flex max-w-2xl flex-col items-center gap-8 text-center">
        <h1 className="text-5xl font-bold tracking-tight text-black dark:text-white">
          PATY
        </h1>
        <p className="text-xl text-zinc-500 dark:text-zinc-400">
          Please And Thank You — Voice AI for outbound calls, controlled via
          ChatGPT and OpenClaw.
        </p>
        <p className="text-base text-zinc-600 dark:text-zinc-400 max-w-lg">
          Make phone calls directly from your AI assistant. Connect PATY to
          Claude Code, Claw, or any MCP-compatible client and start calling with
          a single command.
        </p>
        <div className="flex gap-4">
          {isSignedIn ? (
            <Link
              href="/dashboard"
              className="rounded-full bg-black px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200"
            >
              Go to dashboard
            </Link>
          ) : (
            <>
              <Link
                href="/sign-in"
                className="rounded-full bg-black px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200"
              >
                Sign in
              </Link>
              <Link
                href="/sign-up"
                className="rounded-full border border-zinc-200 px-6 py-3 text-sm font-medium text-black transition-colors hover:bg-zinc-50 dark:border-zinc-700 dark:text-white dark:hover:bg-zinc-900"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
