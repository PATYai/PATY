agent() {
    local repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [[ -z "$repo_root" ]]; then
        echo "Error: not in a git repository" >&2
        return 1
    fi

    local agent_id=${1:-$(date +%s | sha256sum | head -c 8)}
    local branch="agent/$agent_id"
    local worktree_dir="${repo_root}/../.worktrees/${repo_root##*/}/$agent_id"

    mkdir -p "$(dirname "$worktree_dir")"

    # Create worktree with new branch from current HEAD
    git worktree add -b "$branch" "$worktree_dir" HEAD || return 1

    echo "Agent $agent_id ready at $worktree_dir"

    # Run claude in the worktree
    (cd "$worktree_dir" && claude)

    # Prompt for cleanup
    read -p "Remove worktree? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git worktree remove "$worktree_dir"
        git branch -D "$branch"
        echo "Cleaned up agent $agent_id"
    else
        echo "Worktree preserved at $worktree_dir (branch: $branch)"
    fi
}
