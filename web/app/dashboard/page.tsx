"use client";

import { useAuth, useUser, SignOutButton } from "@clerk/nextjs";
import { useState } from "react";
import { redirect } from "next/navigation";

const MCP_SERVER_URL =
  process.env.NEXT_PUBLIC_MCP_SERVER_URL || "https://paty-stage-mcp.fly.dev";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <button
      onClick={handleCopy}
      className="rounded px-3 py-1 text-xs font-medium bg-zinc-100 hover:bg-zinc-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 transition-colors"
    >
      {copied ? "Copied!" : label}
    </button>
  );
}

function CodeBlock({
  code,
  label,
}: {
  code: string;
  label: string;
}) {
  return (
    <div className="relative rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900">
      <div className="flex items-center justify-between px-4 py-2 border-b border-zinc-200 dark:border-zinc-700">
        <span className="text-xs text-zinc-500 font-mono">{label}</span>
        <CopyButton text={code} label="Copy" />
      </div>
      <pre className="overflow-x-auto p-4 text-sm font-mono text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap break-all">
        {code}
      </pre>
    </div>
  );
}

export default function DashboardPage() {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const [token, setToken] = useState<string | null>(null);
  const [loadingToken, setLoadingToken] = useState(false);

  if (isLoaded && !isSignedIn) {
    redirect("/sign-in");
  }

  async function handleCopyToken() {
    setLoadingToken(true);
    try {
      const t = await getToken();
      setToken(t);
      if (t) {
        await navigator.clipboard.writeText(t);
      }
    } finally {
      setLoadingToken(false);
    }
  }

  const claudeCodeCommand = `claude mcp add paty-control \\
  --transport http \\
  --header "Authorization: Bearer YOUR_TOKEN" \\
  "${MCP_SERVER_URL}/mcp"`;

  const clawConfig = JSON.stringify(
    {
      mcpServers: {
        "paty-control": {
          url: `${MCP_SERVER_URL}/mcp`,
          headers: {
            Authorization: "Bearer YOUR_TOKEN",
          },
        },
      },
    },
    null,
    2
  );

  const genericConfig = JSON.stringify(
    {
      mcpServers: {
        "paty-control": {
          transport: "http",
          url: `${MCP_SERVER_URL}/mcp`,
          headers: {
            Authorization: "Bearer YOUR_TOKEN",
          },
        },
      },
    },
    null,
    2
  );

  return (
    <div className="min-h-screen bg-white dark:bg-black">
      <nav className="border-b border-zinc-200 dark:border-zinc-800 px-6 py-4 flex items-center justify-between">
        <span className="font-semibold text-black dark:text-white">PATY</span>
        <div className="flex items-center gap-4">
          <span className="text-sm text-zinc-500">
            {user?.primaryEmailAddress?.emailAddress}
          </span>
          <SignOutButton>
            <button className="text-sm text-zinc-500 hover:text-black dark:hover:text-white transition-colors">
              Sign out
            </button>
          </SignOutButton>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-12 flex flex-col gap-10">
        <div>
          <h1 className="text-3xl font-bold text-black dark:text-white mb-2">
            Welcome{user?.firstName ? `, ${user.firstName}` : ""}
          </h1>
          <p className="text-zinc-500">
            Connect PATY to your MCP client to make voice calls from your AI
            assistant.
          </p>
        </div>

        {/* API Token */}
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-black dark:text-white">
            Your API Token
          </h2>
          <p className="text-sm text-zinc-500">
            Your personal Clerk session token authenticates you with the PATY
            MCP server. Replace{" "}
            <code className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 rounded">
              YOUR_TOKEN
            </code>{" "}
            in the configs below with this token.
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={handleCopyToken}
              disabled={loadingToken}
              className="rounded-full bg-black px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-zinc-800 dark:bg-white dark:text-black dark:hover:bg-zinc-200 disabled:opacity-50"
            >
              {loadingToken ? "Fetching…" : "Copy session token"}
            </button>
            {token && (
              <span className="text-xs text-green-600 dark:text-green-400">
                Copied to clipboard!
              </span>
            )}
          </div>
          <p className="text-xs text-zinc-400">
            Note: Session tokens expire after 1 hour. Re-copy as needed.
          </p>
        </section>

        {/* Claude Code */}
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-black dark:text-white">
            Connect to Claude Code
          </h2>
          <p className="text-sm text-zinc-500">
            Run this command in your terminal (replace{" "}
            <code className="font-mono text-xs bg-zinc-100 dark:bg-zinc-800 px-1 py-0.5 rounded">
              YOUR_TOKEN
            </code>
            ):
          </p>
          <CodeBlock code={claudeCodeCommand} label="Terminal" />
          <p className="text-sm text-zinc-500">
            After connecting, you can ask Claude to{" "}
            <em>&ldquo;call +1 555 123 4567&rdquo;</em> and PATY will handle the rest.
          </p>
        </section>

        {/* Claw */}
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-black dark:text-white">
            Connect to Claw
          </h2>
          <p className="text-sm text-zinc-500">
            Add the following to your Claw MCP server configuration:
          </p>
          <CodeBlock code={clawConfig} label="claw-config.json" />
        </section>

        {/* Generic MCP */}
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-black dark:text-white">
            Generic MCP Client
          </h2>
          <p className="text-sm text-zinc-500">
            For any MCP-compatible client, use this configuration:
          </p>
          <CodeBlock code={genericConfig} label="mcp-config.json" />
        </section>

        {/* Available Tools */}
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold text-black dark:text-white">
            Available Tools
          </h2>
          <div className="rounded-lg border border-zinc-200 dark:border-zinc-700 divide-y divide-zinc-200 dark:divide-zinc-700">
            {[
              {
                name: "make_call",
                desc: "Initiate an outbound voice call to a phone number",
              },
              { name: "end_call", desc: "End an active call" },
              { name: "list_rooms", desc: "List all active calls" },
              {
                name: "get_call_status",
                desc: "Get the status of a specific call",
              },
            ].map(({ name, desc }) => (
              <div key={name} className="flex items-start gap-4 px-4 py-3">
                <code className="text-sm font-mono text-black dark:text-white shrink-0">
                  {name}
                </code>
                <span className="text-sm text-zinc-500">{desc}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
